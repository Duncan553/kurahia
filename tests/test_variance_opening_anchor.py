"""
Opening is what was on the shelf when the period began.

It was anchored on the most recent StockCount at or before the period, falling
back to ZERO when none existed — which says the shelf was empty. Tilapia
Fillet carried 7.95kg in from earlier purchases with no count behind it, so
expected_closing came out NEGATIVE and the screen built to catch stock going
missing reported "+7.2500 kg, 2900%, flagged" on an item where nothing was
wrong.

A count is still the better anchor where one exists. Where none does, the
honest number is what the LEDGER says was carried in — which is exactly zero
for a line created inside the period, so a brand-new item still measures
correctly.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.stock_count import StockCount
from app.services.variance import compute_variance


@pytest.fixture
def item(app):
    from app.models.department import Department
    from app.models.user import User
    with app.app_context():
        dept = db.session.query(Department).filter_by(name="Kitchen").one()
        who = db.session.query(User).filter_by(username="manager1").one()
        it = InventoryItem(name="Anchor Test Fish", unit="kg", department_id=dept.id)
        db.session.add(it); db.session.flush()
        db.session.add(StockMovement(
            item_id=it.id, change_amount=Decimal("8"),
            reason=MovementReason.PURCHASE.value, actor_id=who.id,
            idempotency_key=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc) - timedelta(days=10)))
        db.session.commit()
        return it.id, who.id


def _window():
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=12), now + timedelta(hours=1)


def _count(item_id, who, amount, at):
    db.session.add(StockCount(item_id=item_id, counted_amount=Decimal(amount),
                              actor_id=who, timestamp_utc=at,
                              count_type="FULL",
                              idempotency_key=str(uuid.uuid4())))
    db.session.commit()


class TestOpeningAnchor:
    def test_stock_carried_in_is_not_a_surplus(self, app, item):
        """The exact shape that produced the 2900% false flag: 8kg bought ten
        days ago, never counted, counted today at 8. Nothing is wrong."""
        item_id, who = item
        start, end = _window()
        with app.app_context():
            _count(item_id, who, "8", end - timedelta(hours=1))   # closing only
            v = compute_variance(item_id, start, end)
            assert v["opening"] == Decimal("8"), "ledger carried 8kg in"
            assert v["variance"] == Decimal("0")
            assert v["flagged"] is False

    def test_a_line_created_inside_the_period_still_opens_at_zero(self, app):
        """Falling back to the ledger must not break the genuine zero case."""
        from app.models.department import Department
        from app.models.user import User
        start, end = _window()
        with app.app_context():
            dept = db.session.query(Department).filter_by(name="Kitchen").one()
            who = db.session.query(User).filter_by(username="manager1").one()
            it = InventoryItem(name="Brand New Line", unit="kg", department_id=dept.id)
            db.session.add(it); db.session.flush()
            db.session.add(StockMovement(
                item_id=it.id, change_amount=Decimal("20"),
                reason=MovementReason.PURCHASE.value, actor_id=who.id,
                idempotency_key=str(uuid.uuid4()),
                timestamp_utc=start + timedelta(hours=1)))   # INSIDE the window
            db.session.commit()
            _count(it.id, who.id, "16", end - timedelta(minutes=5))
            v = compute_variance(it.id, start, end)
            assert v["opening"] == Decimal("0"), "nothing was on the shelf before"
            assert v["variance"] == Decimal("-4"), "bought 20, counted 16"

    def test_with_both_anchors_it_computes(self, app, item):
        item_id, who = item
        start, end = _window()
        with app.app_context():
            _count(item_id, who, "8", start - timedelta(minutes=5))   # opening
            _count(item_id, who, "8", end - timedelta(hours=1))       # closing
            v = compute_variance(item_id, start, end)
            assert v.get("no_opening_count") is None
            assert v["opening"] == Decimal("8")
            # Nothing moved in the window, so nothing is missing.
            assert v["variance"] == Decimal("0")
            assert v["flagged"] is False

    def test_a_real_shortfall_still_flags(self, app, item):
        """Closing the false-positive must not close the true one."""
        item_id, who = item
        start, end = _window()
        with app.app_context():
            _count(item_id, who, "8", start - timedelta(minutes=5))
            _count(item_id, who, "5", end - timedelta(hours=1))   # 3kg gone, unexplained
            v = compute_variance(item_id, start, end)
            assert v["variance"] == Decimal("-3")
            assert v["flagged"] is True
