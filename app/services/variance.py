"""
variance.py — Layer 1 variance computation.

Formula (per item, per period):
  opening          = most recent StockCount at or before period_start
  purchases        = SUM of PURCHASE movements in period
  consumption      = ABS(SUM of SPOILAGE + STAFF_MEAL + SENT_BACK + SALE_PLACEHOLDER in period)
  expected_closing = opening + purchases - consumption
  actual_closing   = most recent StockCount within the period
  variance         = actual_closing - expected_closing

Negative variance → more stock missing than expected (unaccounted loss / theft).
Positive variance → more stock on hand than expected (under-counted consumption).

Returns None if no closing count exists for the period (can't compute without anchor).
"""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import func
from app.extensions import db
from app.models.stock_movement import StockMovement, CONSUMPTION_REASONS, MovementReason
from app.models.stock_count import StockCount
from app.models.inventory_item import InventoryItem


def compute_variance(item_id: str, period_start: datetime, period_end: datetime) -> dict | None:
    """
    Returns a variance dict for one item over [period_start, period_end], or None
    if there is no closing count in the period (can't anchor the calculation).
    """
    # Opening anchor: most recent count at or before period_start
    opening_count = (
        db.session.query(StockCount)
        .filter(StockCount.item_id == item_id, StockCount.timestamp_utc <= period_start)
        .order_by(StockCount.timestamp_utc.desc())
        .first()
    )
    opening = Decimal(str(opening_count.counted_amount)) if opening_count else Decimal("0")

    # Purchases in period (positive movements)
    purchases_raw = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.reason == MovementReason.PURCHASE,
        StockMovement.timestamp_utc > period_start,
        StockMovement.timestamp_utc <= period_end,
    ).scalar()
    purchases = Decimal(str(purchases_raw)) if purchases_raw is not None else Decimal("0")

    # Consumption in period (negative movements for loss reasons)
    consumption_raw = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.reason.in_([r.value for r in CONSUMPTION_REASONS]),
        StockMovement.timestamp_utc > period_start,
        StockMovement.timestamp_utc <= period_end,
    ).scalar()
    # These movements are negative; abs() to get a positive "consumed" number
    consumption = abs(Decimal(str(consumption_raw))) if consumption_raw is not None else Decimal("0")

    expected_closing = opening + purchases - consumption

    # Closing anchor: most recent count strictly within the period
    closing_count = (
        db.session.query(StockCount)
        .filter(
            StockCount.item_id == item_id,
            StockCount.timestamp_utc > period_start,
            StockCount.timestamp_utc <= period_end,
        )
        .order_by(StockCount.timestamp_utc.desc())
        .first()
    )
    if closing_count is None:
        # Can't compute variance without at least one closing count in the period.
        # Caller uses the 'no_closing_count' key to show a plain-English note in the report.
        return None

    actual_closing = Decimal(str(closing_count.counted_amount))
    variance = actual_closing - expected_closing

    # Determine tolerance for this item
    item = db.session.get(InventoryItem, item_id)
    tolerance = item.effective_tolerance() if item else Decimal("5")

    # Flagged if absolute variance exceeds tolerance % of expected closing
    # Guard against zero expected_closing to avoid division by zero
    if expected_closing != Decimal("0"):
        variance_pct = abs(variance) / abs(expected_closing) * 100
    else:
        variance_pct = Decimal("0") if variance == Decimal("0") else Decimal("100")

    return {
        "item_id":          item_id,
        "item_name":        item.name if item else "unknown",
        "unit":             item.unit if item else "?",
        "opening":          opening,
        "purchases":        purchases,
        "consumption":      consumption,
        "expected_closing": expected_closing,
        "actual_closing":   actual_closing,
        "variance":         variance,
        "variance_pct":     variance_pct,
        "flagged":          variance_pct > tolerance,
        "tolerance_pct":    tolerance,
    }
