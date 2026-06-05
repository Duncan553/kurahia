"""
finance/bank.py — Manual bank transfer reconciliation.

GET  /finance/bank/pending?date=YYYY-MM-DD  → unreconciled BANK_TRANSFER payments
POST /finance/bank/reconcile                → mark each MATCHED or FLAGGED

Mirrors the pattern in finance/mpesa.py. Bank transfers use the bank_ref field
(not card_ref). The SMS forwarder socket in bank_transfer.py auto-writes these
rows when activated — the manual flow is the day-one fallback.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import (
    PaymentReconciliation, PaymentReconciliationStatus
)
from app.models.audit_log import AuditLog
from app.services.finance import parse_date_bounds
from app.services.judge_alerts import fire_alert_if_absent
from app.models.judge_alert import AlertSeverity

bank_bp = Blueprint("finance_bank", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5


def _pending_bank_transfers(period_start, period_end):
    """BANK_TRANSFER payments not yet MATCHED in the given date range."""
    reconciled_ids = db.session.query(
        PaymentReconciliation.payment_id
    ).filter(
        PaymentReconciliation.status == PaymentReconciliationStatus.MATCHED.value
    ).scalar_subquery()

    return db.session.query(Payment).filter(
        Payment.method == PaymentMethod.BANK_TRANSFER.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
        ~Payment.id.in_(reconciled_ids),
    ).order_by(Payment.created_at_utc).all()


@bank_bp.get("/bank/pending")
@require_active_user
def bank_pending():
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

    pending = _pending_bank_transfers(period_start, period_end)
    return jsonify({
        "date": date_str,
        "count": len(pending),
        "payments": [
            {
                "payment_id":  p.id,
                "amount":      str(p.amount),
                "bank_ref":    p.bank_ref,
                "description": p.description,
                "received_by": p.received_by.username if p.received_by else None,
                "created_at":  p.created_at_utc.isoformat(),
            }
            for p in pending
        ],
    }), 200


@bank_bp.post("/bank/reconcile")
@require_active_user
def bank_reconcile():
    """
    Body: { "entries": [ {payment_id, action, statement_ref, notes} ] }
    action: "MATCH" or "FLAG"
    Flagged entries fire a BANK_FLAGGED JudgeAlert (idempotent).
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data    = request.get_json(silent=True) or {}
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"error": "entries list is required and must not be empty."}), 400

    results      = []
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
        if payment.method != PaymentMethod.BANK_TRANSFER.value:
            return jsonify({"error": f"Payment {payment_id} is not a bank transfer."}), 400

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
                method=PaymentMethod.BANK_TRANSFER.value,
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
        actor=actor.username, action="finance.bank.reconcile",
        details=f"matched={len(results)-flagged_count} flagged={flagged_count}",
    )

    if flagged_count > 0:
        flagged_ids = [r["payment_id"] for r in results if r["status"] == PaymentReconciliationStatus.FLAGGED.value]
        fire_alert_if_absent(
            alert_type="BANK_FLAGGED",
            description_key="flagged as unverified",
            item_id=None,
            severity=AlertSeverity.HIGH.value,
            description=(
                f"{flagged_count} bank transfer(s) flagged as unverified: "
                f"{', '.join(flagged_ids[:5])}{'...' if flagged_count > 5 else ''}."
            ),
        )
        db.session.commit()

    return jsonify({"reconciled": len(results), "flagged": flagged_count, "results": results}), 200
