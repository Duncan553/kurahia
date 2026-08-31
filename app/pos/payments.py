"""
pos/payments.py — Record payments against a tab.
POST /tabs/:id/payments — idempotent, append-only
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user, require_clocked_in
from app.extensions import db
from app.models.tab import Tab, TabStatus
from app.models.payment import Payment, PaymentMethod
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.tab import get_tab_balance

payments_bp = Blueprint("payments", __name__, url_prefix="/tabs")


@payments_bp.post("/<tab_id>/payments")
@require_active_user
@require_clocked_in
def record_payment(tab_id):
    actor = db.session.get(User, get_jwt_identity())
    tab   = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404
    if tab.status == TabStatus.CLOSED.value:
        return jsonify({"error": "This tab is already closed. No further payments can be recorded."}), 400

    data     = request.get_json(silent=True) or {}
    raw_amt  = data.get("amount")
    method   = (data.get("method") or "").upper()
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    if not method or method not in PaymentMethod.__members__:
        return jsonify({"error": f"Payment method must be one of {list(PaymentMethod.__members__)}."}), 400
    if raw_amt is None:
        return jsonify({"error": "amount is required."}), 400
    try:
        amount = Decimal(str(raw_amt))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "amount must be a valid number."}), 400
    if not amount.is_finite() or amount <= 0:
        return jsonify({"error": "Payment amount must be a positive number."}), 400

    # M-Pesa: capture code but do NOT verify (reconciliation is Chunk 5)
    mpesa_code = data.get("mpesa_code") if method == PaymentMethod.MPESA.value else None
    card_ref   = data.get("card_ref")   if method == PaymentMethod.CARD.value  else None
    # Payment.bank_ref existed as a column but was never read here, so a bank
    # transfer's reference was silently dropped — and that reference is the only
    # thing /finance/bank/reconcile has to match a payment against a statement
    # line. Captured on the same terms as the other two.
    bank_ref   = data.get("bank_ref")   if method == PaymentMethod.BANK_TRANSFER.value else None

    # Idempotency — silent duplicate suppression
    existing = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True, "amount": str(existing.amount)}), 200

    with db.session.begin_nested():
        payment = Payment(
            tab_id=tab_id,
            amount=amount,
            method=method,
            mpesa_code=mpesa_code,
            card_ref=card_ref,
            bank_ref=bank_ref,
            received_by_id=actor.id,
            idempotency_key=idem_key,
        )
        db.session.add(payment)

    AuditLog.log(
        actor=actor.username, action="payment.record",
        target=tab_id, details=f"method={method} amount={amount}",
    )
    db.session.commit()

    balance = get_tab_balance(tab_id)
    # GET /tabs/:id's payments[] entries use "id"/"created_at"/"received_by" —
    # kept "payment_id" here too (additive) since nothing currently reads it,
    # but the two shapes for "a payment" shouldn't disagree on field names.
    return jsonify({
        "id":            payment.id,
        "payment_id":    payment.id,
        "amount":        str(amount),
        "method":        method,
        "tab_balance":   str(balance),
        "mpesa_code":    mpesa_code,
        "created_at":    payment.created_at_utc.isoformat(),
        "received_by":   actor.username,
    }), 201
