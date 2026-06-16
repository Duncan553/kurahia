"""
trust.py — Trust-tier computation for inventory counting.

Each inventory item is evaluated at request time (never stored) and assigned one of:

  MUST_COUNT     — full physical count required
  QUICK_VERIFY   — spot-check: count a sample, confirm it looks right
  AUTO_CONFIRMED — system trusts the running total; no physical count needed

Criteria (evaluated in order):

  MUST_COUNT if ANY of:
    1. is_watch_list = True
    2. Item was created < 4 weeks ago (created_at is recent or NULL treated as recent)
    3. Active CountDemotion within last 4 weeks (previous spot-check showed variance)
    4. COUNT StockMovement exists in last 4 weeks (variance found in any recent count)
    5. Open JudgeAlert for this item created in the last 7 days

  QUICK_VERIFY if ALL of:
    - Fewer than 5 movements in last 30 days
    - No COUNT movement in last 4 weeks (no known variance)

  AUTO_CONFIRMED otherwise (active, stable, no flags)
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.count_demotion import CountDemotion
from app.models.judge_alert import JudgeAlert, AlertStatus

MUST_COUNT     = "MUST_COUNT"
QUICK_VERIFY   = "QUICK_VERIFY"
AUTO_CONFIRMED = "AUTO_CONFIRMED"

# How long a demotion or "new item" flag stays active
DEMOTION_WINDOW = timedelta(weeks=4)
NEW_ITEM_WINDOW = timedelta(weeks=4)
JUDGE_WINDOW    = timedelta(weeks=1)
MOVEMENT_WINDOW = timedelta(days=30)


def compute_trust_tier(item: InventoryItem) -> tuple[str, str]:
    """
    Return (tier, reason) for a single item.
    'reason' is a short machine-readable string for frontend display.
    Must be called inside an active app context with a live DB session.
    """
    now = datetime.now(timezone.utc)

    # ── Criterion 1: watch list ───────────────────────────────────────────────
    if item.is_watch_list:
        return MUST_COUNT, "watch_list"

    # ── Criterion 2: new item (created_at within 4 weeks, or no created_at) ──
    # SQLite strips tzinfo on load; normalise to UTC before comparing in Python.
    created = item.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if created is None or created >= now - NEW_ITEM_WINDOW:
        return MUST_COUNT, "new_item"

    # ── Criterion 3: active demotion from a failed spot-check ────────────────
    active_demotion = db.session.query(CountDemotion).filter(
        CountDemotion.item_id == item.id,
        CountDemotion.demoted_at >= now - DEMOTION_WINDOW,
    ).first()
    if active_demotion:
        return MUST_COUNT, "prior_variance"

    # ── Criterion 4: any COUNT movement in last 4 weeks = variance was found ─
    # (reconciliation movement only exists when adjustment != 0)
    recent_variance = db.session.query(StockMovement).filter(
        StockMovement.item_id == item.id,
        StockMovement.reason == MovementReason.COUNT.value,
        StockMovement.timestamp_utc >= now - DEMOTION_WINDOW,
    ).first()
    if recent_variance:
        return MUST_COUNT, "recent_variance"

    # ── Criterion 5: open judge alert in last 7 days ──────────────────────────
    judge_flag = db.session.query(JudgeAlert).filter(
        JudgeAlert.item_id == item.id,
        JudgeAlert.created_at >= now - JUDGE_WINDOW,
        JudgeAlert.status == AlertStatus.OPEN.value,
    ).first()
    if judge_flag:
        return MUST_COUNT, "judge_flagged"

    # ── QUICK_VERIFY: low activity + clean history ────────────────────────────
    movement_count = db.session.query(StockMovement).filter(
        StockMovement.item_id == item.id,
        StockMovement.timestamp_utc >= now - MOVEMENT_WINDOW,
    ).count()
    if movement_count < 5:
        return QUICK_VERIFY, "low_activity"

    # ── AUTO_CONFIRMED: stable, active, trusted ───────────────────────────────
    return AUTO_CONFIRMED, "stable"
