"""
judge/engine.py — Layer 2: the silent variance brain.

NOW ACTIVE — POS payments feed _get_sales_revenue().

Two jobs:
  run_weekly(period_start, period_end)  → ratio analysis per item
  run_daily(date)                        → watch-list items, spoilage spikes

Both write JudgeAlerts if anomalies found. Both no-op if no payment data.
Tolerances are kept WIDE at launch — better silent than crying wolf.
"""
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import func
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason, CONSUMPTION_REASONS
from app.models.judge_baseline import JudgeBaseline
from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
from app.models.audit_log import AuditLog
from app.services.judge_alerts import fire_alert_if_absent


def _get_sales_revenue(period_start: datetime, period_end: datetime) -> Decimal | None:
    """
    Returns total payment revenue for the period. None if no payments exist.
    This one change wakes Layer 2 — no other judge code changes needed.
    Per-department revenue splits can be added later without changing this interface.
    """
    from app.models.payment import Payment
    result = db.session.query(func.sum(Payment.amount)).filter(
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc <= period_end,
    ).scalar()
    if result is None:
        return None
    rev = Decimal(str(result))
    return rev if rev > Decimal("0") else None


def _get_period_consumption(item_id: str, period_start: datetime, period_end: datetime) -> Decimal:
    """Sum of all consumption movements for an item in the period."""
    raw = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.reason.in_([r.value for r in CONSUMPTION_REASONS]),
        StockMovement.timestamp_utc > period_start,
        StockMovement.timestamp_utc <= period_end,
    ).scalar()
    return abs(Decimal(str(raw))) if raw is not None else Decimal("0")


def _get_spoilage(item_id: str, period_start: datetime, period_end: datetime) -> Decimal:
    raw = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.reason == MovementReason.SPOILAGE.value,
        StockMovement.timestamp_utc > period_start,
        StockMovement.timestamp_utc <= period_end,
    ).scalar()
    return abs(Decimal(str(raw))) if raw is not None else Decimal("0")


def _fire_alert(item_id: str | None, alert_type: str, severity: AlertSeverity,
                description: str, period_start: datetime, period_end: datetime):
    """
    Idempotent alert creation — skips if an OPEN alert of this type for this
    item already exists for this period. Returns (alert, created) tuple.
    """
    # Use item name from description as the dedup key (item name is always present)
    description_key = description.split(":")[0]  # e.g. "Watch Beer" from "Watch Beer: spoilage..."
    alert, created = fire_alert_if_absent(
        alert_type=alert_type,
        description_key=description_key,
        item_id=item_id,
        severity=severity.value,
        description=description,
        period_start=period_start,
        period_end=period_end,
    )
    return alert


def _run_cost_variance(period_start: datetime, period_end: datetime) -> int:
    """
    Per-ingredient cost variance: expected spend (qty_served × recipe × cost_per_unit)
    vs actual consumption movements × cost_per_unit. Default threshold 15%.
    """
    from app.models.recipe_line import RecipeLine
    from app.models.order_item import OrderItem, OrderItemStatus
    from app.models.menu_item import MenuItem

    COST_VARIANCE_THRESHOLD = Decimal("15")
    HIGH_THRESHOLD = Decimal("25")

    ingredients = db.session.query(InventoryItem).filter_by(
        is_active=True, is_staff_food=False
    ).all()

    alerts_fired = 0
    for ing in ingredients:
        if ing.cost_per_unit is None:
            continue

        recipe_lines = db.session.query(RecipeLine).filter_by(
            inventory_item_id=ing.id, is_active=True
        ).all()
        if not recipe_lines:
            continue

        expected_qty = Decimal("0")
        for rl in recipe_lines:
            served_qty = db.session.query(func.sum(OrderItem.quantity)).filter(
                OrderItem.menu_item_id == rl.menu_item_id,
                OrderItem.status == OrderItemStatus.SERVED.value,
                OrderItem.served_at >= period_start,
                OrderItem.served_at <= period_end,
            ).scalar()
            if served_qty:
                expected_qty += Decimal(str(served_qty)) * rl.quantity

        if expected_qty == Decimal("0"):
            continue

        actual_qty = _get_period_consumption(ing.id, period_start, period_end)
        if actual_qty == Decimal("0"):
            continue

        expected_cost = expected_qty * Decimal(str(ing.cost_per_unit))
        actual_cost = actual_qty * Decimal(str(ing.cost_per_unit))

        if expected_cost == Decimal("0"):
            continue

        deviation_pct = abs(actual_cost - expected_cost) / expected_cost * 100
        if deviation_pct <= COST_VARIANCE_THRESHOLD:
            continue

        direction = "overspent" if actual_cost > expected_cost else "underspent"
        severity = AlertSeverity.HIGH if deviation_pct > HIGH_THRESHOLD else AlertSeverity.MEDIUM
        desc = (
            f"{ing.name} ingredients {direction} by {deviation_pct:.0f}% this week. "
            f"Expected KSh {expected_cost:,.0f}, actual KSh {actual_cost:,.0f}."
        )
        _fire_alert(ing.id, "COST_VARIANCE", severity, desc, period_start, period_end)
        alerts_fired += 1

    return alerts_fired


def _run_budget_exceeded() -> int:
    """Fire BUDGET_EXCEEDED alert for any department over 100% of its monthly budget."""
    from app.models.budget import Budget
    from app.models.department import Department

    from app.services.finance import get_budget_spend

    now = datetime.now(timezone.utc)
    period = f"{now.year}-{now.month:02d}"

    # The window get_budget_spend sums over: this calendar month so far.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = now

    budgets = db.session.query(Budget).filter_by(is_active=True).all()
    alerts_fired = 0

    for b in budgets:
        if not b.amount or Decimal(str(b.amount)) <= 0:
            continue
        if b.period != period:
            continue

        budget_amt = Decimal(str(b.amount))

        # Spend is DERIVED from the purchase ledger (invariant 2), never stored.
        # This used to read `b.spent` behind a `hasattr(b, 'spent')` guard — but
        # Budget has no `spent` column, so the guard was always False, `spent`
        # was always 0, the `spent <= budget_amt` check below always continued,
        # and this alert had never fired once since it was written.
        spent = get_budget_spend(b.department_id, month_start, month_end)

        if spent <= budget_amt:
            continue

        dept = db.session.get(Department, b.department_id)
        dept_name = dept.name if dept else "Unknown"
        pct = (spent / budget_amt * 100).quantize(Decimal("1"))

        _fire_alert(
            item_id=None,
            alert_type="BUDGET_EXCEEDED",
            severity=AlertSeverity.HIGH if spent > budget_amt * Decimal("1.2") else AlertSeverity.MEDIUM,
            description=f"{dept_name} department has spent {pct}% of its monthly budget "
                        f"(KSh {spent:,.0f} of KSh {budget_amt:,.0f}).",
            period_start=month_start,
            period_end=month_end,
        )
        alerts_fired += 1

    return alerts_fired


def run_weekly(period_start: datetime, period_end: datetime) -> int:
    """
    Weekly judge analysis:
    1. Ratio analysis — consumption vs revenue (dormant if no payment data)
    2. Cost variance — expected vs actual ingredient spend (runs if orders exist)
    """
    alerts_fired = 0

    # 1. Ratio analysis — requires payment data
    revenue = _get_sales_revenue(period_start, period_end)
    baselines = db.session.query(JudgeBaseline).filter_by(
        business_driver="restaurant_revenue", is_active=True
    ).all()

    if revenue and revenue > Decimal("0"):
        for baseline in baselines:
            item = db.session.get(InventoryItem, baseline.item_id)
            if not item or not item.is_active or item.is_staff_food:
                continue

            consumption = _get_period_consumption(item.id, period_start, period_end)
            if consumption == Decimal("0"):
                continue

            expected = baseline.expected_ratio * (revenue / Decimal("10000"))
            deviation_pct = abs(consumption - expected) / expected * 100

            if deviation_pct > baseline.tolerance_percent:
                severity = (
                    AlertSeverity.HIGH   if deviation_pct > baseline.tolerance_percent * 2
                    else AlertSeverity.MEDIUM
                )
                desc = (
                    f"{item.name}: consumed {consumption}{item.unit}, "
                    f"expected ~{expected:.2f}{item.unit} "
                    f"({deviation_pct:.1f}% deviation vs {baseline.tolerance_percent}% tolerance)"
                )
                _fire_alert(item.id, "RATIO", severity, desc, period_start, period_end)
                alerts_fired += 1

    # Cost variance analysis: expected vs actual ingredient spend
    alerts_fired += _run_cost_variance(period_start, period_end)

    # Budget exceeded: any department over 100% budget for current month
    alerts_fired += _run_budget_exceeded()

    if alerts_fired:
        db.session.flush()
        AuditLog.log(actor="judge", action="judge.weekly_run",
                     details=f"{alerts_fired} alerts fired")
        db.session.commit()

    return alerts_fired


def _check_portion_variance(period_start: datetime, period_end: datetime) -> int:
    """
    Compare EXPECTED ingredient usage (from recipes × orders served) against
    ACTUAL stock movements (SALE/CONSUMPTION reasons) for the same period.
    Flags ingredients where actual usage exceeds expected by >15%.

    Why it matters: consistent over-portioning, unrecorded waste, or theft all
    show up as actual > expected. The kitchen thinks they're using the right
    amount, but stock disappears faster than recipes predict.
    """
    from app.models.recipe_line import RecipeLine
    from app.models.order_item import OrderItem, OrderItemStatus
    from app.models.menu_item import MenuItem

    # Default thresholds — configurable via JudgeBaseline in the future
    MEDIUM_THRESHOLD = Decimal("15")  # percent over expected
    HIGH_THRESHOLD   = Decimal("25")

    # All active ingredients that appear in at least one recipe
    ingredients = db.session.query(InventoryItem).filter_by(
        is_active=True, is_staff_food=False
    ).all()

    alerts_fired = 0
    for ing in ingredients:
        # Get all active recipe lines for this ingredient
        recipe_lines = db.session.query(RecipeLine).filter_by(
            inventory_item_id=ing.id, is_active=True
        ).all()
        if not recipe_lines:
            continue

        # EXPECTED: sum of (order_item.quantity × recipe_line.quantity) for served orders
        expected_qty = Decimal("0")
        for rl in recipe_lines:
            served_qty = db.session.query(func.sum(OrderItem.quantity)).filter(
                OrderItem.menu_item_id == rl.menu_item_id,
                OrderItem.status == OrderItemStatus.SERVED.value,
                OrderItem.served_at >= period_start,
                OrderItem.served_at <= period_end,
            ).scalar()
            if served_qty:
                expected_qty += Decimal(str(served_qty)) * rl.quantity

        if expected_qty == Decimal("0"):
            continue

        # ACTUAL: sum of consumption movements (SALE, SPOILAGE, STAFF_MEAL, etc.)
        actual_qty = _get_period_consumption(ing.id, period_start, period_end)
        if actual_qty == Decimal("0"):
            continue

        # Variance: how much MORE was actually used vs what recipes predicted
        variance_pct = (actual_qty - expected_qty) / expected_qty * 100

        # Only flag OVER-usage (actual > expected). Under-usage is a different signal.
        if variance_pct <= MEDIUM_THRESHOLD:
            continue

        severity = AlertSeverity.HIGH if variance_pct > HIGH_THRESHOLD else AlertSeverity.MEDIUM
        desc = (
            f"{ing.name}: expected {expected_qty:.2f}{ing.unit}, "
            f"actually used {actual_qty:.2f}{ing.unit} "
            f"({variance_pct:.0f}% over). "
            f"Possible over-portioning, waste, or theft."
        )
        _fire_alert(ing.id, "PORTION_VARIANCE", severity, desc, period_start, period_end)
        alerts_fired += 1

    return alerts_fired


def _check_ghost_tickets(period_start: datetime, period_end: datetime) -> int:
    """
    Ghost ticket: food was MADE (reached READY) then CANCELLED — someone ate
    without paying. Grouped by the staff member who cancelled; fires if same
    person cancels ready items more than 2 times in the period.

    The cancel actor is tracked via the audit log (action='order_item.cancel')
    because OrderItem doesn't store cancelled_by_id directly.

    Why it matters: a waiter who repeatedly cancels items after the kitchen
    already prepared them is either stealing food or covering for someone who is.
    """
    from app.models.order_item import OrderItem, OrderItemStatus

    # Step 1: find all order items that were READY then CANCELLED in this period
    ghost_items = db.session.query(OrderItem).filter(
        OrderItem.status == OrderItemStatus.CANCELLED.value,
        OrderItem.ready_at.isnot(None),           # food was prepared
        OrderItem.cancelled_at >= period_start,
        OrderItem.cancelled_at <= period_end,
    ).all()

    if not ghost_items:
        return 0

    # Step 2: look up who cancelled each item from the audit log
    # Audit log entry: action='order_item.cancel', target=order_item.id, actor=username
    staff_counts = {}   # username → count
    staff_item_ids = {}  # username → list of order_item IDs (for the alert description)
    for oi in ghost_items:
        audit_entry = db.session.query(AuditLog).filter(
            AuditLog.action == "order_item.cancel",
            AuditLog.target == oi.id,
        ).first()
        if not audit_entry:
            continue
        username = audit_entry.actor
        staff_counts[username] = staff_counts.get(username, 0) + 1
        staff_item_ids.setdefault(username, []).append(oi.id)

    # Step 3: fire alert for any staff member who cancelled >2 ready items
    GHOST_THRESHOLD = 2
    alerts_fired = 0
    for username, count in staff_counts.items():
        if count <= GHOST_THRESHOLD:
            continue

        desc = (
            f"{username} cancelled {count} items AFTER kitchen marked them ready. "
            f"Food was made but never paid for."
        )
        _fire_alert(
            item_id=None,
            alert_type="GHOST_TICKET",
            severity=AlertSeverity.HIGH,
            description=desc,
            period_start=period_start,
            period_end=period_end,
        )
        alerts_fired += 1

    return alerts_fired


def _check_borrowed_accounts(period_start: datetime, period_end: datetime) -> int:
    """A manager reset a subordinate's password, and that account then traded.

    THE HOLE THIS WATCHES. A manager may reset any subordinate's password —
    they have to, people forget them. But the API accepts password login, and a
    PIN only guards the station's login SCREEN, not the endpoints under it. So
    a manager who resets a waiter's password can sign in as that waiter, sell,
    take cash, and every charge lands on the waiter's name.

    It cannot be forbidden without breaking real password resets, so it is
    watched instead. A reset is ordinary. A reset followed within hours by that
    account taking money is a pattern worth a human looking at — which is
    exactly what this engine is for.

    This does NOT accuse anyone. It says: these two things happened close
    together, go and check. The reset is on the hash-chained audit log and
    cannot be removed after the fact.
    """
    from app.models.payment import Payment
    from app.models.user import User

    resets = db.session.query(AuditLog).filter(
        AuditLog.action == "user.password_reset",
        AuditLog.timestamp >= period_start,
        AuditLog.timestamp < period_end,
    ).all()

    fired = 0
    for reset in resets:
        target_username = reset.target
        if not target_username or target_username == reset.actor:
            continue   # resetting your own password is not this pattern

        target = db.session.query(User).filter_by(username=target_username).first()
        if not target:
            continue

        # Money taken ON that account AFTER the reset, inside the period.
        took = db.session.query(Payment).filter(
            Payment.received_by_id == target.id,
            Payment.created_at_utc >= reset.timestamp,
            Payment.created_at_utc < period_end,
        ).all()
        if not took:
            continue

        total = sum((p.amount for p in took), Decimal("0"))
        desc = (f"{target_username}: password reset by {reset.actor}, then "
                f"{len(took)} payment(s) totalling {total} were taken on that "
                f"account. Confirm {target_username} was the person working.")
        _fire_alert(None, "BORROWED_ACCOUNT", AlertSeverity.HIGH,
                    desc, period_start, period_end)
        fired += 1

    return fired


def run_daily(date: datetime) -> int:
    """
    Daily job: watch-list items + spoilage spike + portion variance + ghost tickets.
    Watch-list items flagged if spoilage exceeds their tighter tolerance.
    """
    from datetime import timedelta
    period_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end   = period_start + timedelta(days=1)

    watch_items = db.session.query(InventoryItem).filter_by(
        is_watch_list=True, is_active=True, is_staff_food=False
    ).all()

    alerts_fired = 0
    for item in watch_items:
        spoilage = _get_spoilage(item.id, period_start, period_end)
        if spoilage == Decimal("0"):
            continue

        # Spoilage spike: if spoilage exceeds 10% of daily typical usage, flag it
        # Placeholder threshold — will be calibrated once we have real usage data
        SPIKE_THRESHOLD = Decimal("10")  # units — conservative placeholder
        if spoilage > SPIKE_THRESHOLD:
            desc = f"{item.name}: spoilage of {spoilage}{item.unit} today exceeds spike threshold"
            _fire_alert(item.id, "SPOILAGE_SPIKE", AlertSeverity.MEDIUM, desc, period_start, period_end)
            alerts_fired += 1

    # Portion variance: expected vs actual ingredient usage
    alerts_fired += _check_portion_variance(period_start, period_end)

    # Ghost tickets: food made then cancelled — possible theft
    alerts_fired += _check_ghost_tickets(period_start, period_end)

    # Borrowed accounts: password reset, then that account took money
    alerts_fired += _check_borrowed_accounts(period_start, period_end)

    if alerts_fired:
        db.session.flush()
        AuditLog.log(actor="judge", action="judge.daily_run",
                     details=f"{alerts_fired} alerts fired")
        db.session.commit()

    return alerts_fired
