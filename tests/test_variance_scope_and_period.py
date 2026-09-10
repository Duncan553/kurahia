"""
Two things the variance report got wrong, both found by opening the screen.

1. It defaulted a MANAGER to their own department. Every other inventory read
   treats a manager as covering the whole property — GET /inventory/items lists
   all forty lines for them, and counts.py lets them count any department — but
   variance alone narrowed to actor.department_id. Waterfront's manager sits in
   "Management", which holds one active stock line, so he opened the
   theft-detection screen and saw 1 item out of 40, with nothing saying so.

   Nobody below MANAGER_LEVEL can reach this endpoint at all, so that default
   only ever narrowed the person it was written for.

2. A bare date was read as a UTC calendar day. A day at this resort runs 06:00
   EAT to 06:00 EAT (app/services/business_day.py, which attendance, finance,
   receipts and the dashboards already use). A stock count taken at 00:50 EAT
   was reported as "not yet counted" for the day it was taken in.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.department import Department
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.stock_count import StockCount
from app.services.business_day import business_day_bounds

PW = "TestPass1!"


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_department_items(app):
    """One stock line in the manager's own department, one somewhere else."""
    mgmt = Department(name="Management")
    db.session.add(mgmt)
    db.session.flush()

    kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
    own = InventoryItem(name="Manager Clipboard", unit="piece", department_id=mgmt.id)
    other = InventoryItem(name="Kitchen Flour", unit="kg", department_id=kitchen.id)
    db.session.add_all([own, other])
    db.session.commit()

    # put the manager in Management, the way the real one is
    from app.models.user import User
    mgr = db.session.query(User).filter_by(username="manager1").first()
    mgr.department_id = mgmt.id
    db.session.commit()
    return own.id, other.id


def _counted_item(bought: str, counted: str, when: datetime, dept_name="Kitchen"):
    """A line bought and then counted at a given instant."""
    dept = db.session.query(Department).filter_by(name=dept_name).first()
    item = InventoryItem(name=f"Traced {uuid.uuid4().hex[:4]}", unit="kg",
                         department_id=dept.id)
    db.session.add(item)
    db.session.flush()
    from app.models.user import User
    actor = db.session.query(User).filter_by(username="manager1").first()
    db.session.add(StockMovement(
        item_id=item.id, change_amount=bought, reason=MovementReason.PURCHASE.value,
        actor_id=actor.id, idempotency_key=str(uuid.uuid4()),
        timestamp_utc=when - timedelta(hours=1),
    ))
    db.session.add(StockCount(
        item_id=item.id, counted_amount=counted, timestamp_utc=when,
        actor_id=actor.id, count_type="DAILY", idempotency_key=str(uuid.uuid4()),
    ))
    db.session.commit()
    return item.id


class TestVarianceCoversTheWholeProperty:

    def test_manager_sees_every_department_by_default(
            self, client, manager_token, two_department_items):
        own_id, other_id = two_department_items
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        rv = client.get(f"/inventory/variance?from={today}&to={today}",
                        headers=_hdr(manager_token))
        assert rv.status_code == 200, rv.get_json()
        ids = {i["item_id"] for i in rv.get_json()["items"]}

        assert own_id in ids, "his own department, obviously"
        assert other_id in ids, "and the kitchen, which is the point of the screen"

    def test_a_named_department_still_narrows_it(
            self, client, manager_token, two_department_items, app):
        """`dept` is how a screen asks for one department deliberately."""
        own_id, other_id = two_department_items
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        rv = client.get(
            f"/inventory/variance?dept={kitchen.id}&from={today}&to={today}",
            headers=_hdr(manager_token))
        ids = {i["item_id"] for i in rv.get_json()["items"]}

        assert other_id in ids
        assert own_id not in ids

    def test_below_manager_cannot_run_it_at_all(self, client, waiter_token):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rv = client.get(f"/inventory/variance?from={today}&to={today}",
                        headers=_hdr(waiter_token))
        assert rv.status_code == 403


class TestVarianceUsesTheBusinessDay:

    def test_a_count_just_after_midnight_lands_in_the_right_day(
            self, client, manager_token, app):
        """00:50 EAT is BEFORE the 06:00 cutoff, so it belongs to the previous
        business day — not to the UTC calendar day it happens to fall in."""
        # 2026-09-10 21:50 UTC == 2026-09-11 00:50 EAT
        when = datetime(2026, 9, 10, 21, 50, tzinfo=timezone.utc)
        item_id = _counted_item("20", "16", when)

        rv = client.get("/inventory/variance?from=2026-09-10&to=2026-09-10",
                        headers=_hdr(manager_token))
        row = next(i for i in rv.get_json()["items"] if i["item_id"] == item_id)
        assert not row.get("no_closing_count"), \
            "the count belongs to the business day that was running when it happened"
        assert row["actual_closing"] == "16.0000"

    def test_the_bounds_are_the_ones_the_rest_of_the_system_uses(self, app):
        """conftest pins the business day to UTC/00:00 so the suite is
        deterministic, so this test states Waterfront's REAL configuration
        first — 06:00 Africa/Nairobi — and checks the bounds that follow from
        it. Asserting 03:00 UTC against the harness's own override would just
        be testing the harness."""
        from app.models.system_setting import SystemSetting
        db.session.get(SystemSetting, "business_day_start_hour").value = "6"
        db.session.get(SystemSetting, "business_day_timezone").value = "Africa/Nairobi"
        db.session.commit()

        start, end = business_day_bounds("2026-09-10")
        assert start.hour == 3, "06:00 EAT is 03:00 UTC"
        assert (end - start) == timedelta(hours=24)
        # and the instant that started all this — 00:50 EAT on the 11th — falls
        # inside the business day of the 10th, which is the whole point.
        assert start <= datetime(2026, 9, 10, 21, 50, tzinfo=timezone.utc) < end

    def test_a_full_timestamp_is_still_honoured_exactly(
            self, client, manager_token, app):
        """A caller that wants a precise window keeps one."""
        when = datetime(2026, 9, 10, 21, 50, tzinfo=timezone.utc)
        item_id = _counted_item("20", "16", when)

        rv = client.get(
            "/inventory/variance?from=2026-09-10T00:00:00&to=2026-09-10T23:59:59",
            headers=_hdr(manager_token))
        assert rv.status_code == 200
        row = next(i for i in rv.get_json()["items"] if i["item_id"] == item_id)
        assert not row.get("no_closing_count")


class TestTheVarianceNumbersThemselves:

    def test_expected_is_opening_plus_purchases_minus_consumption(
            self, client, manager_token, app):
        when = datetime.now(timezone.utc) - timedelta(minutes=5)
        item_id = _counted_item("20", "16", when)
        day_str = when.strftime("%Y-%m-%d")

        rv = client.get(f"/inventory/variance?from={day_str}&to={day_str}",
                        headers=_hdr(manager_token))
        rows = [i for i in rv.get_json()["items"] if i["item_id"] == item_id]
        if not rows or rows[0].get("no_closing_count"):
            pytest.skip("count fell outside this business day; covered above")
        row = rows[0]

        from decimal import Decimal
        opening = Decimal(row["opening"])
        purchases = Decimal(row["purchases"])
        consumption = Decimal(row["consumption"])
        assert opening + purchases - consumption == Decimal(row["expected_closing"])
        assert Decimal(row["actual_closing"]) - Decimal(row["expected_closing"]) \
            == Decimal(row["variance"])

    def test_the_percentage_is_a_magnitude_and_the_sign_lives_on_variance(
            self, client, manager_token, app):
        """This is why the screen must not read direction off variance_pct: a
        shortage and a surplus of the same size give the SAME percentage. The
        count screen printed '+' whenever variance_pct > 0 — which is always —
        so 4 kg missing displayed as '+20.0% variance'."""
        when = datetime.now(timezone.utc) - timedelta(minutes=5)
        short_id = _counted_item("20", "16", when)     # 4 short
        over_id = _counted_item("20", "24", when)      # 4 over
        day_str = when.strftime("%Y-%m-%d")

        rv = client.get(f"/inventory/variance?from={day_str}&to={day_str}",
                        headers=_hdr(manager_token))
        rows = {i["item_id"]: i for i in rv.get_json()["items"]}
        if rows[short_id].get("no_closing_count"):
            pytest.skip("counts fell outside this business day; covered above")

        assert rows[short_id]["variance_pct"] == rows[over_id]["variance_pct"]
        assert float(rows[short_id]["variance"]) < 0
        assert float(rows[over_id]["variance"]) > 0
