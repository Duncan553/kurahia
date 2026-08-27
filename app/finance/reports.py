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
    get_budget_spend, get_staff_pending_cash,
)

reports_bp = Blueprint("finance_reports", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


# ── Daily revenue history ────────────────────────────────────────────────────

@reports_bp.get("/revenue-history")
@require_active_user
def revenue_history():
    """
    GET /finance/revenue-history?days=7
    Owner-only. Returns per-day Payment sums for the last N days (max 90).
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can view revenue history."}), 403

    try:
        days = min(int(request.args.get("days", 7)), 90)
        if days < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "days must be a positive integer (max 90)."}), 400

    now = datetime.now(timezone.utc)
    result = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        raw = db.session.query(func.sum(Payment.amount)).filter(
            Payment.created_at_utc >= day_start,
            Payment.created_at_utc <  day_end,
        ).scalar()
        result.append({
            "date":    day_start.strftime("%Y-%m-%d"),
            "revenue": str(Decimal(str(raw)) if raw is not None else Decimal("0")),
        })
    return jsonify(result), 200


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
    # `recon_diff` only covers reconciliations that have actually happened — it
    # reads 0.00 even when most of today's cash hasn't been reconciled yet.

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

    # The real outstanding gap: how much cash is sitting with staff right now,
    # unreconciled — not `cash_total_collected - total_handed_in`, which mixed
    # two different time scopes (cash collected THIS period vs. reconciliations
    # that closed THIS period, which can sweep up older pending cash from a
    # prior period) and could go negative once a stale multi-day balance got
    # reconciled in one go. Summing each pending staff member's true current
    # pending total is scope-correct and never negative.
    unreconciled_amount = sum(get_staff_pending_cash(sid)[0] for sid in pending_staff_ids)

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
            "unreconciled_amount": str(unreconciled_amount),
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

    # ── Expenses + profit for the month ───────────────────────────────────
    # Purchases: resort-wide, not scoped to a department (unlike
    # get_budget_spend, which is one department at a time for the budget
    # rows above) — this is the actual total stock spend for the period.
    from app.models.purchase import Purchase
    raw_purchases = db.session.query(func.sum(Purchase.actual_cost)).filter(
        Purchase.timestamp_added >= month_start,
        Purchase.timestamp_added < month_end,
    ).scalar()
    purchase_expenses = Decimal(str(raw_purchases)) if raw_purchases is not None else Decimal("0")

    # Payroll: reuses the same calculation PayrollDraftScreen shows per
    # employee (app/services/payroll.py) — net_pay is None for anyone with
    # no wage_rate set on their profile yet, which counts as 0 here (an
    # honest reflection of real data, not a bug: payroll can't estimate a
    # cost nobody has recorded).
    from app.services.payroll import calculate_payroll
    payroll_rows = calculate_payroll(month_start, month_end)
    payroll_cost = sum(
        (Decimal(r["net_pay"]) for r in payroll_rows if r.get("net_pay") is not None),
        Decimal("0"),
    )

    total_expenses = purchase_expenses + payroll_cost
    profit_month    = revenue_month - total_expenses

    return jsonify({
        "period": period_str,
        "revenue": {
            "today": str(revenue_today),
            "week":  str(revenue_week),
            "month": str(revenue_month),
        },
        "expenses": {
            "purchases": str(purchase_expenses),
            "payroll":   str(payroll_cost),
            "total":     str(total_expenses),
        },
        "profit_month":         str(profit_month),
        "budgets":              budget_rows,
        "open_shortfalls":      open_shortfalls,
        "no_receipt_purchases": no_receipt_purchases,
        "judge_alerts_open":    open_alerts,
    }), 200


# ── Payroll ──────────────────────────────────────────────────────────────────

@reports_bp.get("/payroll")
@require_active_user
def payroll():
    """
    GET /finance/payroll?period=YYYY-MM
    Manager+ access. Returns calculated wages for all active employees:
    hours worked, gross pay, staff-meal deductions, and net pay.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    period_str = request.args.get("period")
    if not period_str:
        return jsonify({"error": "period query parameter required (YYYY-MM)."}), 400

    try:
        period_start, period_end = parse_month_bounds(period_str)
    except (ValueError, AttributeError):
        return jsonify({"error": "Invalid period. Use YYYY-MM."}), 400

    from app.services.payroll import calculate_payroll
    rows = calculate_payroll(period_start, period_end)

    return jsonify({
        "period":       period_str,
        "period_start": period_start.strftime("%Y-%m-%d"),
        "period_end":   (period_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "employees":    rows,
    }), 200


@reports_bp.get("/vat-summary")
@require_active_user
def vat_summary():
    """VAT totals for a period — the figures an accountant needs to file.

    This is deliberately a BRIDGE, not an eTIMS integration. Filing is handled
    by someone else; what the system owes them is an accurate, reproducible
    statement of what was sold and how much tax it contained.

    Every figure is DERIVED from the charge ledger (invariant 2), so running the
    same period twice always gives the same answer, and it can never disagree
    with the receipts — the receipts are built from the same rows.

    Prices are VAT-INCLUSIVE, so gross is what guests actually paid and the tax
    sits inside it: tax = gross x rate / (1 + rate).
    """
    from collections import defaultdict
    from decimal import Decimal
    from datetime import datetime, timezone
    from app.models.charge import Charge

    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    def _day(param, end=False):
        raw = (request.args.get(param) or "").strip()
        if not raw:
            return None
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return "bad"
        return d.replace(hour=23, minute=59, second=59) if end else d

    start, end = _day("from"), _day("to", end=True)
    if start == "bad" or end == "bad":
        return jsonify({"error": "from and to must be YYYY-MM-DD."}), 400

    q = db.session.query(Charge)
    if start:
        q = q.filter(Charge.created_at >= start)
    if end:
        q = q.filter(Charge.created_at <= end)

    # Grouped by the rate that applied AT THE TIME, not today's — a period
    # spanning a rate change must report both, which is exactly why the rate is
    # snapshotted per charge.
    by_rate = defaultdict(lambda: {"gross": Decimal("0"), "tax": Decimal("0"),
                                   "net": Decimal("0"), "charges": 0})
    untracked = {"gross": Decimal("0"), "charges": 0}

    for c in q.all():
        if c.tax_rate_snapshot is None:
            # Predates VAT tracking. Reported separately rather than assumed to
            # be zero-rated — quietly folding it into the totals would hand the
            # accountant a number the resort cannot stand behind.
            untracked["gross"] += Decimal(str(c.amount))
            untracked["charges"] += 1
            continue
        key = str(c.tax_rate_snapshot)
        bucket = by_rate[key]
        bucket["gross"] += Decimal(str(c.amount))
        bucket["tax"] += c.tax_amount
        bucket["net"] += c.net_amount
        bucket["charges"] += 1

    return jsonify({
        "from": request.args.get("from"),
        "to": request.args.get("to"),
        "pricing": "VAT-INCLUSIVE — gross is what the guest paid",
        "by_rate": [{
            "rate_percent": rate,
            "charges": b["charges"],
            "gross": str(b["gross"]),
            "net": str(b["net"]),
            "tax": str(b["tax"]),
        } for rate, b in sorted(by_rate.items())],
        "totals": {
            "gross": str(sum((b["gross"] for b in by_rate.values()), Decimal("0"))),
            "net":   str(sum((b["net"] for b in by_rate.values()), Decimal("0"))),
            "tax":   str(sum((b["tax"] for b in by_rate.values()), Decimal("0"))),
        },
        "untracked": {
            "charges": untracked["charges"],
            "gross": str(untracked["gross"]),
            "note": "Recorded before VAT tracking existed. Excluded from the "
                    "totals above — confirm the treatment with your accountant.",
        },
    }), 200


@reports_bp.get("/menu-engineering")
@require_active_user
def menu_engineering():
    """Classify every menu item by popularity and contribution margin.

    The Kasavana-Smith matrix (Michigan State, 1980s) — still the standard tool
    for menu profitability. Each item is measured on two axes against the MENU'S
    OWN AVERAGE, not an industry benchmark:

        popular + profitable      STAR       protect it
        popular + unprofitable    PLOWHORSE  fix the cost or nudge the price
        unpopular + profitable    PUZZLE     promote it
        unpopular + unprofitable  DOG        take it off

    The axis is CONTRIBUTION MARGIN in shillings, not food-cost percentage. A
    dish at 20% food cost sounds better than one at 40%, but if the first sells
    for 300 and the second for 1,800 the second puts far more money in the bank.
    Percentage describes a dish; contribution margin describes the business.

    Items with no recipe are NOT classified and are returned separately. Their
    food cost is unknown, so any margin for them would be invented — and an
    invented number here would drive a real decision to delist a dish.
    """
    from collections import defaultdict
    from decimal import Decimal
    from datetime import datetime, timezone
    from sqlalchemy import func
    from app.models.menu_item import MenuItem
    from app.models.order_item import OrderItem, OrderItemStatus
    from app.pos.menu import _compute_menu_item_cost_fields

    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    def _day(param, end=False):
        raw = (request.args.get(param) or "").strip()
        if not raw:
            return None
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return "bad"
        return d.replace(hour=23, minute=59, second=59) if end else d

    start, end = _day("from"), _day("to", end=True)
    if start == "bad" or end == "bad":
        return jsonify({"error": "from and to must be YYYY-MM-DD."}), 400

    # Units actually SERVED — not ordered. A cancelled plate is not a sale, and
    # counting it would make a dish look more popular than it is.
    sold_q = (db.session.query(OrderItem.menu_item_id,
                               func.sum(OrderItem.quantity).label("units"))
              .filter(OrderItem.status == OrderItemStatus.SERVED.value))
    if start:
        sold_q = sold_q.filter(OrderItem.served_at >= start)
    if end:
        sold_q = sold_q.filter(OrderItem.served_at <= end)
    sold = {mid: Decimal(str(u or 0)) for mid, u in sold_q.group_by(OrderItem.menu_item_id).all()}

    classified, unknown_cost = [], []
    for item in db.session.query(MenuItem).filter_by(is_active=True).all():
        econ = _compute_menu_item_cost_fields(item)
        units = sold.get(item.id, Decimal("0"))
        row = {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "prep_station": item.prep_station,
            "stock_tracking": item.stock_tracking,
            "price": str(item.price),
            "units_sold": str(units),
        }
        if econ.get("food_cost") is None:
            row["reason"] = ("No recipe, so the food cost is unknown. Any margin "
                             "shown here would be invented.")
            unknown_cost.append(row)
            continue
        food_cost = Decimal(str(econ["food_cost"]))
        contribution = Decimal(str(item.price)) - food_cost
        row.update({
            "food_cost": str(food_cost),
            "contribution_margin": str(contribution),
            "food_cost_pct": econ.get("food_cost_pct") and str(econ["food_cost_pct"]),
            "total_contribution": str(contribution * units),
        })
        classified.append((row, units, contribution))

    # Thresholds are the menu's OWN averages — the matrix is relative by design,
    # because "profitable" means profitable for THIS menu.
    if classified:
        avg_units = sum((u for _, u, _ in classified), Decimal("0")) / len(classified)
        avg_margin = sum((c for _, _, c in classified), Decimal("0")) / len(classified)
    else:
        avg_units = avg_margin = Decimal("0")

    ACTIONS = {
        "STAR":      "Protect it. Keep quality and availability steady; it anchors the menu.",
        "PLOWHORSE": "Popular but thin. Cut the cost or raise the price a little — people already want it.",
        "PUZZLE":    "Profitable but overlooked. Promote it, move it up the menu, or rename it.",
        "DOG":       "Neither selling nor earning. Take it off unless it exists for a reason.",
    }

    buckets = defaultdict(list)
    for row, units, contribution in classified:
        popular = units >= avg_units
        profitable = contribution >= avg_margin
        kind = ("STAR" if popular and profitable else
                "PLOWHORSE" if popular else
                "PUZZLE" if profitable else "DOG")
        row["classification"] = kind
        row["action"] = ACTIONS[kind]
        buckets[kind].append(row)

    return jsonify({
        "from": request.args.get("from"),
        "to": request.args.get("to"),
        "method": "Kasavana-Smith matrix — popularity vs contribution margin, "
                  "measured against this menu's own averages",
        "thresholds": {
            "avg_units_sold": str(avg_units),
            "avg_contribution_margin": str(avg_margin),
        },
        "items": {k: sorted(v, key=lambda r: Decimal(r["total_contribution"]), reverse=True)
                  for k, v in buckets.items()},
        "counts": {k: len(v) for k, v in buckets.items()},
        "unclassified": {
            "count": len(unknown_cost),
            "items": unknown_cost,
            "note": "These have no recipe, so their profitability cannot be "
                    "measured. Classifying them on a guessed cost would drive a "
                    "real decision to keep or delist a dish.",
        },
    }), 200
