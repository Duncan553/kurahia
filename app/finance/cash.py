"""
finance/cash.py — Per-staff cash reconciliation.

GET  /finance/cash/pending?staff_id=X   → unreconciled CASH payments + total
POST /finance/cash/reconcile            → cashier records actual cash handed in

Expected = derived SUM; actual = entered by cashier.
Difference flagged. Repeated shortfalls by same person → JudgeAlert.
"""
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.utils.money import parse_amount, parse_quantity
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus, cash_recon_payments
from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
from app.models.audit_log import AuditLog
from app.services.finance import get_staff_pending_cash, count_staff_shortfalls
from app.services.judge_alerts import fire_alert_if_absent

cash_bp = Blueprint("finance_cash", __name__, url_prefix="/finance")

MANAGER_LEVEL   = 5
SHORTFALL_LIMIT = 3   # consecutive SHORTs before alerting owner


@cash_bp.get("/cash/pending")
@require_active_user
def pending_cash():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to view cash reconciliation."}), 403

    staff_id = request.args.get("staff_id")
    if not staff_id:
        return jsonify({"error": "staff_id query parameter is required."}), 400

    staff = db.session.get(User, staff_id)
    if not staff:
        return jsonify({"error": "Staff member not found."}), 404

    total, payments = get_staff_pending_cash(staff_id)
    # CashReconScreen's staff picker shows EmployeeProfile.full_name ("Joyce Wambua");
    # this used to send back the raw username ("joyce.wambua") instead, so the
    # confirm screen headlined a different-looking name right under the picker.
    profile = db.session.query(EmployeeProfile).filter_by(user_id=staff_id).first()
    return jsonify({
        "staff_id":       staff_id,
        "staff_name":     profile.full_name if profile else staff.username,
        "expected_total": str(total),
        "payment_count":  len(payments),
        "payments": [
            {
                "payment_id": p.id,
                "amount":     str(p.amount),
                "tab_id":     p.tab_id,
                "created_at": p.created_at_utc.isoformat(),
            }
            for p in payments
        ],
    }), 200


@cash_bp.post("/cash/reconcile")
@require_active_user
def reconcile_cash():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to reconcile cash."}), 403

    data     = request.get_json(silent=True) or {}
    staff_id = data.get("staff_id")
    raw_amt  = data.get("actual_amount")
    notes    = (data.get("notes") or "").strip() or None
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    if not staff_id:
        return jsonify({"error": "staff_id is required."}), 400
    staff = db.session.get(User, staff_id)
    if not staff:
        return jsonify({"error": "Staff member not found."}), 404
    # A cash count of zero is a real answer — the drawer was empty — so zero is
    # allowed here where a payment of zero is not.
    actual, err = parse_amount(raw_amt, "actual_amount", allow_zero=True)
    if err:
        return jsonify({"error": err}), 400

    # Idempotency
    existing = db.session.query(CashReconciliation).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    # Snapshot the pending payments at this exact moment
    expected, pending_payments = get_staff_pending_cash(staff_id)

    difference = actual - expected
    if difference == Decimal("0"):
        status = ReconciliationStatus.BALANCED.value
    elif difference < Decimal("0"):
        status = ReconciliationStatus.SHORT.value
    else:
        status = ReconciliationStatus.OVER.value

    now = datetime.now(timezone.utc)

    with db.session.begin_nested():
        recon = CashReconciliation(
            staff_id=staff_id,
            reconciled_by_id=actor.id,
            expected_amount=expected,
            actual_amount=actual,
            difference=difference,
            period_start_utc=pending_payments[0].created_at_utc if pending_payments else now,
            period_end_utc=now,
            status=status,
            notes=notes,
            idempotency_key=idem_key,
        )
        db.session.add(recon)
        db.session.flush()

        # Link all swept payments to this reconciliation
        for p in pending_payments:
            db.session.execute(
                cash_recon_payments.insert().values(recon_id=recon.id, payment_id=p.id)
            )

    db.session.commit()
    AuditLog.log(
        actor=actor.username,
        action="finance.cash.reconcile",
        target=staff_id,
        details=f"expected={expected} actual={actual} diff={difference} status={status}",
    )

    # Repeated shortfalls → owner alert (idempotent: skip if OPEN alert for this staff exists)
    if status == ReconciliationStatus.SHORT.value:
        n_shorts = count_staff_shortfalls(staff_id, last_n=SHORTFALL_LIMIT)
        if n_shorts >= SHORTFALL_LIMIT:
            fire_alert_if_absent(
                alert_type="CASH_SHORTFALL_PATTERN",
                description_key=staff.username,
                item_id=None,
                severity=AlertSeverity.HIGH.value,
                description=(
                    f"{staff.username} has {n_shorts} consecutive cash shortfalls. "
                    f"Latest: expected {expected}, got {actual} (diff {difference})."
                ),
                period_start=recon.period_start_utc,
                period_end=recon.period_end_utc,
            )

    db.session.commit()

    return jsonify({
        "id":              recon.id,
        "staff_id":        staff_id,
        "expected_amount": str(expected),
        "actual_amount":   str(actual),
        "difference":      str(difference),
        "status":          status,
        "payments_swept":  len(pending_payments),
    }), 201
