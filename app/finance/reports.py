"""
finance/reports.py — Three-way reconciliation report + period close + dashboard.

GET  /finance/reconciliation?date=YYYY-MM-DD  → receipts + cash + stock in one view
POST /finance/close-period                     → safe count, locks the day
GET  /finance/dashboard?period=YYYY-MM         → owner finance overview
"""
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus
from app.models.period_close import PeriodClose, PeriodCloseStatus
from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
from app.models.audit_log import AuditLog
from app.services.judge_alerts import fire_alert_if_absent
from app.services.finance import (
    parse_date_bounds, parse_month_bounds,
    get_period_revenue_by_method, get_period_cash_reconciled_total,
    get_budget_spend,
)

reports_bp = Blueprint("finance_reports", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


# ── Three-way reconciliation report ──────────────────────────────────────────

@reports_bp.get("/reconciliation")
@require_active_user
def three_way_report():
    """
    Assembles all three corners for a day:
      1. Receipts: what the POS recorded (by method)
      2. Cash:     what staff handed in vs what was collected
      3. Stock:    open judge alerts for the period

    Surfaces any gap with: day, method, and the name attached.
    """
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

    # ── Corner 1: Receipts ────────────────────────────────────────────────
    revenue = get_period_revenue_by_method(period_start, period_end)

    # ── Corner 2: Cash reconciliation ─────────────────────────────────────
    cash_total_collected = revenue.get(PaymentMethod.CASH.value, Decimal("0"))

    # All cash reconciliations within the period
    recons = db.session.query(CashReconciliation).filter(
        CashReconciliation.period_end_utc >= period_start,
        CashReconciliation.period_end_utc < period_end,
    ).all()

    total_expected_recon = sum(Decimal(str(r.expected_amount)) for r in recons)
    total_handed_in      = sum(Decimal(str(r.actual_amount))   for r in recons)
    recon_diff           = total_handed_in - total_expected_recon

    shortfalls = [
        {
            "staff":      r.staff.username if r.staff else r.staff_id,
            "expected":   str(r.expected_amount),
            "actual":     str(r.actual_amount),
            "difference": str(r.difference),
        }
        for r in recons
        if r.status == ReconciliationStatus.SHORT.value
    ]

    # Staff with unreconciled cash in the period
    all_cash_staff = db.session.query(
        Payment.received_by_id
    ).filter(
        Payment.method == PaymentMethod.CASH.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
    ).distinct().all()
    reconciled_staff = {r.staff_id for r in recons}
    pending_staff_ids = [row[0] for row in all_cash_staff
                         if row[0] not in reconciled_staff]
    pending_staff = []
    for sid in pending_staff_ids:
        u = db.session.get(User, sid)
        if u:
            pending_staff.append(u.username)

    # ── Corner 3: Stock / judge ────────────────────────────────────────────
    open_alerts = db.session.query(JudgeAlert).filter(
        JudgeAlert.status == AlertStatus.OPEN.value,
        JudgeAlert.period_end >= period_start,
        JudgeAlert.period_end < period_end,
    ).all()

    # ── Gap analysis ──────────────────────────────────────────────────────
    gaps = []
    if recon_diff < Decimal("0"):
        gaps.append(f"Cash shortfall of KES {abs(recon_diff):,.2f} — "
                    f"staff handed in less than they collected.")
    for s in shortfalls:
        gaps.append(f"  • {s['staff']}: expected {s['expected']}, "
                    f"actual {s['actual']}, diff {s['difference']}")
    if pending_staff:
        gaps.append(f"Unreconciled cash for: {', '.join(pending_staff)}")
    if open_alerts:
        gaps.append(f"{len(open_alerts)} open stock/judge alert(s) for this period.")

    # Is a period close present?
    period_close = db.session.query(PeriodClose).filter(
        PeriodClose.period_start_utc >= period_start,
        PeriodClose.period_start_utc < period_end,
    ).first()

    return jsonify({
        "date": date_str,
        "receipts": {
            "cash":  str(revenue.get(PaymentMethod.CASH.value,  Decimal("0"))),
            "card":  str(revenue.get(PaymentMethod.CARD.value,  Decimal("0"))),
            "mpesa": str(revenue.get(PaymentMethod.MPESA.value, Decimal("0"))),
            "total": str(revenue.get("total", Decimal("0"))),
        },
        "cash_reconciliation": {
            "total_collected":  str(cash_total_collected),
            "total_expected":   str(total_expected_recon),
            "total_handed_in":  str(total_handed_in),
            "difference":       str(recon_diff),
            "shortfalls":       shortfalls,
            "pending_staff":    pending_staff,
        },
        "stock": {
            "open_alerts_count": len(open_alerts),
            "alerts": [
                {"type": a.alert_type, "severity": a.severity,
                 "description": a.description}
                for a in open_alerts[:10]
            ],
        },
        "period_closed":   period_close is not None,
        "balanced":        len(gaps) == 0,
        "gaps":            gaps,
    }), 200


# ── Period close ──────────────────────────────────────────────────────────────

@reports_bp.post("/close-period")
@require_active_user
def close_period():
    """
    Cashier/owner counts the physical safe and closes the day.
    expected = sum(actual_amount from CashReconciliations in period)
    diff = safe_count - expected  (negative = money missing from safe)
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to close a period."}), 403

    data      = request.get_json(silent=True) or {}
    date_str  = data.get("date")
    raw_safe  = data.get("safe_count")
    notes     = (data.get("notes") or "").strip() or None
    idem_key  = data.get("idempotency_key") or str(uuid.uuid4())

    if not date_str:
        return jsonify({"error": "date is required (YYYY-MM-DD)."}), 400
    try:
        period_start, period_end = parse_date_bounds(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400
    if raw_safe is None:
        return jsonify({"error": "safe_count is required."}), 400
    try:
        safe_count = Decimal(str(raw_safe))
    except InvalidOperation:
        return jsonify({"error": "safe_count must be a number."}), 400
    if safe_count < Decimal("0"):
        return jsonify({"error": "safe_count cannot be negative."}), 400

    # Idempotency
    existing = db.session.query(PeriodClose).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    # Alert if period is already closed (non-idempotent re-close)
    already_closed = db.session.query(PeriodClose).filter(
        PeriodClose.period_start_utc >= period_start,
        PeriodClose.period_start_utc < period_end,
    ).first()
    if already_closed:
        if actor.role.level < OWNER_LEVEL:
            return jsonify({
                "error": "This period is already closed. "
                         "Only the owner can close it again (backdating)."
            }), 400
        # Owner re-closing → flag it
        AuditLog.log(actor=actor.username, action="finance.period.reclose",
                     target=date_str, details="Backdated close by owner")

    expected = get_period_cash_reconciled_total(period_start, period_end)
    difference = safe_count - expected

    if difference == Decimal("0"):
        status = PeriodCloseStatus.BALANCED.value
    elif difference < Decimal("0"):
        status = PeriodCloseStatus.SHORT.value
    else:
        status = PeriodCloseStatus.OVER.value

    close = PeriodClose(
        period_start_utc=period_start,
        period_end_utc=period_end,
        closed_by_id=actor.id,
        safe_count=safe_count,
        expected_total_cash=expected,
        difference=difference,
        status=status,
        notes=notes,
        idempotency_key=idem_key,
    )
    db.session.add(close)
    db.session.commit()

    AuditLog.log(
        actor=actor.username, action="finance.period.close",
        target=date_str,
        details=f"safe={safe_count} expected={expected} diff={difference} status={status}",
    )

    # Fire alert if safe count doesn't match (idempotent: skip if OPEN alert for this date exists)
    if status != PeriodCloseStatus.BALANCED.value:
        fire_alert_if_absent(
            alert_type="SAFE_COUNT_MISMATCH",
            description_key=f"Period {date_str}",
            item_id=None,
            severity=AlertSeverity.HIGH.value if status == PeriodCloseStatus.SHORT.value
                     else AlertSeverity.MEDIUM.value,
            description=(
                f"Period {date_str} safe count {safe_count} vs expected {expected} "
                f"(diff {difference}). Status: {status}."
            ),
            period_start=period_start,
            period_end=period_end,
        )

    db.session.commit()

    return jsonify({
        "id":                 close.id,
        "date":               date_str,
        "safe_count":         str(safe_count),
        "expected_total_cash": str(expected),
        "difference":         str(difference),
        "status":             status,
    }), 201


# ── Owner finance dashboard ───────────────────────────────────────────────────

@reports_bp.get("/dashboard")
@require_active_user
def finance_dashboard():
    """
    Owner-only finance overview.
    Revenue today/week/month, spend by dept vs budget, shortfalls, judge alerts.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can view the finance dashboard."}), 403

    from app.models.budget import Budget
    from app.models.department import Department

    period_str = request.args.get("period")
    now = datetime.now(timezone.utc)
    if not period_str:
        period_str = now.strftime("%Y-%m")

    try:
        month_start, month_end = parse_month_bounds(period_str)
    except ValueError:
        return jsonify({"error": "Invalid period. Use YYYY-MM."}), 400

    # Today and this week bounds
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = today_start + timedelta(days=1)
    week_start  = today_start - timedelta(days=today_start.weekday())

    def _rev(start, end):
        raw = db.session.query(func.sum(Payment.amount)).filter(
            Payment.created_at_utc >= start,
            Payment.created_at_utc < end,
        ).scalar()
        return Decimal(str(raw)) if raw is not None else Decimal("0")

    revenue_today = _rev(today_start, today_end)
    revenue_week  = _rev(week_start,  today_end)
    revenue_month = _rev(month_start, month_end)

    # Budget vs spend per department
    budgets = db.session.query(Budget).filter_by(period=period_str, is_active=True).all()
    budget_rows = []
    for b in budgets:
        spent    = get_budget_spend(b.department_id, month_start, month_end)
        bamt     = Decimal(str(b.amount))
        pct_used = float(spent / bamt * 100) if bamt > 0 else 0.0
        dept_name = b.department.name if b.department else b.department_id
        budget_rows.append({
            "department": dept_name,
            "budget":     str(bamt),
            "spent":      str(spent),
            "remaining":  str(bamt - spent),
            "pct_used":   round(pct_used, 1),
            "over_budget": spent > bamt,
        })

    # Open cash shortfalls
    open_shortfalls = db.session.query(CashReconciliation).filter(
        CashReconciliation.status == ReconciliationStatus.SHORT.value,
        CashReconciliation.period_end_utc >= month_start,
        CashReconciliation.period_end_utc < month_end,
    ).count()

    # Open judge alerts
    open_alerts = db.session.query(JudgeAlert).filter_by(
        status=AlertStatus.OPEN.value
    ).count()

    # Purchases without receipt — impossible by model design (NOT NULL constraint)
    # Always 0; included for completeness.
    no_receipt_purchases = 0

    return jsonify({
        "period": period_str,
        "revenue": {
            "today": str(revenue_today),
            "week":  str(revenue_week),
            "month": str(revenue_month),
        },
        "budgets":              budget_rows,
        "open_shortfalls":      open_shortfalls,
        "no_receipt_purchases": no_receipt_purchases,
        "judge_alerts_open":    open_alerts,
    }), 200
