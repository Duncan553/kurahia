"""
variance.py — Layer 1 variance computation.

Formula (per item, per period):
  opening          = most recent StockCount at or before period_start
  explained        = SUM of EVERY movement in the period except COUNT
  expected_closing = opening + explained

The rule is the whole point: a movement is a written, audited explanation for
stock arriving or leaving, so whatever a movement accounts for is NOT variance.
Only what no movement explains is.

That used to be a list — purchases in, CONSUMPTION_REASONS out — and any reason
missing from the list silently became variance. A delivery corrected from 4 to
96 bottles writes an ADJUSTMENT, which was in neither list, so 92 bottles of
Coca-Cola reported as "on the shelf with no purchase behind it" (KSh 17,620
across the corrections made in one afternoon). An event allocation would have
reported the same way with the sign flipped: 50 kg of beef sent to a wedding,
read as theft.

  purchases        = SUM of PURCHASE movements — reported for the breakdown
  consumption      = ABS(SUM of CONSUMPTION_REASONS) — reported for the breakdown
  other_movements  = everything else except COUNT (adjustments, transfers,
                     event allocations) — also explained, also not variance
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
    # Opening is the stock on the shelf when the period began.
    #
    # A COUNT is the better anchor where one exists — it is a verified number
    # somebody put their name to, not what the system believes. But falling
    # back to ZERO when none exists says the shelf was empty, and that is a
    # different claim entirely. Tilapia Fillet carried 7.95kg in from earlier
    # purchases with no count behind it, so opening read 0, expected_closing
    # came out NEGATIVE (-0.25), and the screen built to catch stock going
    # missing reported "+7.2500 kg, 2900%, flagged" on an item where nothing
    # was wrong.
    #
    # With no count, the honest opening is what the LEDGER says was there:
    # the sum of every movement before the period. That is exactly zero for a
    # line created inside the period (nothing had moved yet), so a brand-new
    # item still measures correctly, and it is 7.95 for Tilapia.
    if opening_count is not None:
        # The count is the anchor, but the count is not necessarily the START.
        # A count on the 10th with the period beginning on the 15th leaves five
        # days of sales in between, and taking the counted number as opening
        # silently drops them — the period then gets CHARGED with consumption
        # that happened before it and the shortfall looks like theft.
        #
        # Found on Tusker Beer: last count 38 on 10 Sept, 3 bottles sold on the
        # 14th, 150 received on the 15th. Expected closing came out 212 against
        # a ledger that said 209, so a 19-bottle count difference was reported
        # as a 22-bottle variance. Replay what moved in between.
        opening = Decimal(str(opening_count.counted_amount))
        # COUNT movements are excluded on purpose. A count writes TWO things: the
        # counted number (the anchor) and an adjustment movement that drags the
        # ledger onto it. The adjustment is part of the anchor, not a change
        # that happened after it — and its timestamp lands a hair LATER than the
        # count row, so a naive "after the count" filter subtracts the same
        # correction twice. Tusker read 32 instead of 35 that way.
        since_count = db.session.query(func.sum(StockMovement.change_amount)).filter(
            StockMovement.item_id == item_id,
            StockMovement.timestamp_utc > opening_count.timestamp_utc,
            StockMovement.timestamp_utc <= period_start,
            StockMovement.reason != MovementReason.COUNT,
        ).scalar()
        if since_count is not None:
            opening += Decimal(str(since_count))
    else:
        carried_in = db.session.query(func.sum(StockMovement.change_amount)).filter(
            StockMovement.item_id == item_id,
            StockMovement.timestamp_utc < period_start,
        ).scalar()
        opening = Decimal(str(carried_in)) if carried_in is not None else Decimal("0")

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

    # Everything else the period wrote down — adjustments, transfers, event
    # allocations. Explained movement, therefore not variance. COUNT is
    # excluded because a count IS the reconciliation; counting it would make
    # every variance zero.
    other_raw = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.reason.notin_(
            [MovementReason.PURCHASE.value, MovementReason.COUNT.value]
            + [r.value for r in CONSUMPTION_REASONS]
        ),
        StockMovement.timestamp_utc > period_start,
        StockMovement.timestamp_utc <= period_end,
    ).scalar()
    other_movements = Decimal(str(other_raw)) if other_raw is not None else Decimal("0")

    expected_closing = opening + purchases - consumption + other_movements

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
        # Rounded to one decimal, and rounded HERE so every reader gets the same
        # number. Unrounded, Decimal division put
        # "3653.5885167464114832535 88517%" on a manager's screen — 25 digits of
        # false precision on a figure whose whole job is to be glanced at.
        variance_pct = (abs(variance) / abs(expected_closing) * 100).quantize(Decimal("0.1"))
    else:
        variance_pct = Decimal("0") if variance == Decimal("0") else Decimal("100")

    # ── What it is worth ────────────────────────────────────────────────────
    #
    # "19 bottles" is a fact. "KSh 2,509" is the decision. The resort paid for
    # that stock, and an owner reading a variance report needs the number in the
    # currency the loss actually happened in — a 3 kg swing on tilapia and a
    # 3 kg swing on sukuma are not the same event.
    #
    # Valued at the item's weighted-average cost, which is what was really paid,
    # not the menu price. None where the item has never been bought, because a
    # cost nobody has ever paid is a guess, and a guessed loss is worse than no
    # figure at all.
    cost = Decimal(str(item.cost_per_unit)) if (item and item.cost_per_unit is not None) else None
    variance_value = (variance * cost) if cost is not None else None

    return {
        "item_id":          item_id,
        "item_name":        item.name if item else "unknown",
        "unit":             item.unit if item else "?",
        "opening":          opening,
        "purchases":        purchases,
        "consumption":      consumption,
        "expected_closing": expected_closing,
        "other_movements": other_movements,
        "actual_closing":   actual_closing,
        "variance":         variance,
        "variance_pct":     variance_pct,
        "flagged":          variance_pct > tolerance,
        "tolerance_pct":    tolerance,
        "cost_per_unit":    cost,
        "variance_value":   variance_value,
    }
