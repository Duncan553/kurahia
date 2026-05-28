"""
finance/mpesa.py — M-Pesa & card payment reconciliation.

GET  /finance/mpesa/pending?date=YYYY-MM-DD  → unreconciled M-Pesa payments
POST /finance/mpesa/reconcile                → mark each as MATCHED or FLAGGED
GET  /finance/card/summary?date=YYYY-MM-DD  → card totals for the day

Manual reconciliation now. Daraja API plugs into the same PaymentReconciliation
flow later (auto-match instead of manual entry). No rewrite needed.
"""
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import (
    PaymentReconciliation, PaymentReconciliationStatus
)
from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
from app.models.audit_log import AuditLog
from app.services.finance import parse_date_bounds

mpesa_bp = Blueprint("finance_mpesa", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5


def _pending_by_method(method_val: str, period_start, period_end):
    """Return Payment rows for method that aren't yet MATCHED."""
    reconciled_ids = db.session.query(
        PaymentReconciliation.payment_id
    ).filter(
        PaymentReconciliation.status == PaymentReconciliationStatus.MATCHED.value
    ).scalar_subquery()

    return db.session.query(Payment).filter(
        Payment.method == method_val,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
        ~Payment.id.in_(reconciled_ids),
    ).order_by(Payment.created_at_utc).all()


@mpesa_bp.get("/mpesa/pending")
@jwt_required()
def mpesa_pending():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date query parameter required (YYYY-MM-DD)."}), 400
    try:
        period_start, period_end = parse_date_bounds(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400

    pending = _pending_by_method(PaymentMethod.MPESA.value, period_start, period_end)
    return jsonify({
        "date": date_str,
        "count": len(pending),
        "payments": [
            {
                "payment_id":  p.id,
                "amount":      str(p.amount),
                "mpesa_code":  p.mpesa_code,
                "received_by": p.received_by.username if p.received_by else None,
                "created_at":  p.created_at_utc.isoformat(),
            }
            for p in pending
        ],
    }), 200


@mpesa_bp.post("/mpesa/reconcile")
@jwt_required()
def mpesa_reconcile():
    """
    Body: { "entries": [ {payment_id, action, statement_ref, notes} ] }
    action: "MATCH" or "FLAG"
    Flagged entries → owner JudgeAlert.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data    = request.get_json(silent=True) or {}
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"error": "entries list is required and must not be empty."}), 400

    results = []
    flagged_count = 0

    for entry in entries:
        payment_id    = entry.get("payment_id")
        action        = (entry.get("action") or "").upper()
        statement_ref = entry.get("statement_ref")
        notes         = entry.get("notes")

        if action not in ("MATCH", "FLAG"):
            return jsonify({"error": f"action must be MATCH or FLAG, got '{action}'."}), 400

        payment = db.session.get(Payment, payment_id)
        if not payment:
            return jsonify({"error": f"Payment {payment_id} not found."}), 404
        if payment.method not in (PaymentMethod.MPESA.value, PaymentMethod.CARD.value):
            return jsonify({"error": f"Payment {payment_id} is not M-Pesa or card."}), 400

        # Upsert: create or update the reconciliation row
        recon = db.session.query(PaymentReconciliation).filter_by(
            payment_id=payment_id
        ).first()

        if action == "MATCH":
            new_status = PaymentReconciliationStatus.MATCHED.value
            matched    = True
        else:
            new_status = PaymentReconciliationStatus.FLAGGED.value
            matched    = False
            flagged_count += 1

        if recon:
            recon.status        = new_status
            recon.matched       = matched
            recon.matched_by_id = actor.id
            recon.statement_ref = statement_ref
            recon.notes         = notes
        else:
            recon = PaymentReconciliation(
                payment_id=payment_id,
                method=payment.method,
                matched=matched,
                matched_by_id=actor.id,
                statement_ref=statement_ref,
                status=new_status,
                notes=notes,
            )
            db.session.add(recon)

        results.append({"payment_id": payment_id, "status": new_status})

    db.session.commit()
    AuditLog.log(
        actor=actor.username, action="finance.mpesa.reconcile",
        details=f"matched={len(results)-flagged_count} flagged={flagged_count}",
    )

    # Fire owner alert for each flagged payment
    if flagged_count > 0:
        flagged_pmts = [r["payment_id"] for r in results if r["status"] == PaymentReconciliationStatus.FLAGGED.value]
        alert = JudgeAlert(
            item_id=None,
            alert_type="MPESA_FLAGGED",
            severity=AlertSeverity.HIGH.value,
            description=(
                f"{flagged_count} M-Pesa/card payment(s) flagged as unverified: "
                f"{', '.join(flagged_pmts[:5])}{'...' if flagged_count > 5 else ''}."
            ),
            status=AlertStatus.OPEN.value,
        )
        db.session.add(alert)
        db.session.commit()

    return jsonify({"reconciled": len(results), "flagged": flagged_count, "results": results}), 200


@mpesa_bp.get("/card/summary")
@jwt_required()
def card_summary():
    """Cards self-verify via the bank. This totals them for the day's books."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date query parameter required (YYYY-MM-DD)."}), 400
    try:
        period_start, period_end = parse_date_bounds(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400

    from sqlalchemy import func
    raw = db.session.query(func.sum(Payment.amount)).filter(
        Payment.method == PaymentMethod.CARD.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
    ).scalar()
    total = Decimal(str(raw)) if raw is not None else Decimal("0")

    count = db.session.query(Payment).filter(
        Payment.method == PaymentMethod.CARD.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
    ).count()

    return jsonify({
        "date":         date_str,
        "card_total":   str(total),
        "card_count":   count,
        "note":         "Cards reconcile via bank statement; this total is for your daily books.",
    }), 200
