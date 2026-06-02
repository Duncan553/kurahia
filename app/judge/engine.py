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


def run_weekly(period_start: datetime, period_end: datetime) -> int:
    """
    Compute consumption-to-revenue ratios for all active non-staff-food items.
    Returns the number of alerts fired. Zero if no sales data (dormant state).
    """
    revenue = _get_sales_revenue(period_start, period_end)
    if revenue is None or revenue == Decimal("0"):
        # No sales data yet — stay dormant, generate zero alerts
        return 0

    baselines = db.session.query(JudgeBaseline).filter_by(
        business_driver="restaurant_revenue", is_active=True
    ).all()

    alerts_fired = 0
    for baseline in baselines:
        item = db.session.get(InventoryItem, baseline.item_id)
        if not item or not item.is_active or item.is_staff_food:
            continue

        consumption = _get_period_consumption(item.id, period_start, period_end)
        if consumption == Decimal("0"):
            continue

        # Expected consumption based on the baseline ratio and actual revenue
        # ratio is "units consumed per driver_unit of revenue"
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

    if alerts_fired:
        db.session.commit()
        AuditLog.log(actor="judge", action="judge.weekly_run",
                     details=f"{alerts_fired} alerts fired")
        db.session.commit()

    return alerts_fired


def run_daily(date: datetime) -> int:
    """
    Daily job: watch-list items + spoilage spike detection.
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

    if alerts_fired:
        db.session.commit()
        AuditLog.log(actor="judge", action="judge.daily_run",
                     details=f"{alerts_fired} alerts fired")
        db.session.commit()

    return alerts_fired
