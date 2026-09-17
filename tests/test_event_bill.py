"""
tests/test_event_bill.py — an event is a special customer with its own bill.

Decided with Wachira, 17 Sep 2026:
  - An event's food and drink are planned ahead (dish × plates) by a manager.
  - Before the day the system checks every dish against stock — including what
    other upcoming events have already planned — and writes the manager a buy
    list for whatever is short.
  - The plan goes out as real orders on the event's own bill, so the kitchen,
    bar, stock deduction and theft checks all see it like any other sale.
  - A manager may discount a plate. The discount is RECORDED (menu price,
    discount, reason, who), never typed in as a lower price, and above the
    owner's ceiling only the owner may give it.
  - Only a manager takes the event's money.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from tests.helpers import make_venue


def H(token):
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def event_type_id(client, manager_token):
    return client.post("/event-types", headers=H(manager_token),
                       json={"name": "Wedding"}).get_json()["id"]


def _event(client, token, type_id, days=7, guests=100, venue_fee="50000", title="Otieno Wedding"):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    rv = client.post("/events", headers=H(token), json={
        "title": title, "event_type_id": type_id,
        "venue_id": make_venue(capacity=500, base_price=venue_fee),
        "starts_at_utc": start.isoformat(),
        "ends_at_utc": (start + timedelta(hours=6)).isoformat(),
        "expected_guests": guests, "idempotency_key": str(uuid.uuid4()),
    })
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


@pytest.fixture
def event_id(client, manager_token, event_type_id):
    return _event(client, manager_token, event_type_id)


@pytest.fixture
def rice(app):
    """Rice in kg, with 10 kg in the store."""
    return _stocked_item("Rice", "kg", "10")


@pytest.fixture
def pilau(app, rice):
    """Pilau: KSh 800 a plate, 0.2 kg of rice each. Head chef's price and recipe."""
    from app.extensions import db
    from app.models.menu_item import MenuItem, PrepStation, StockTracking
    from app.models.recipe_line import RecipeLine
    from app.models.department import Department
    dept = db.session.query(Department).filter_by(name="Kitchen").first()
    mi = MenuItem(name="Pilau", price=Decimal("800"), category="Food",
                  prep_station=PrepStation.KITCHEN.value, department_id=dept.id,
                  stock_tracking=StockTracking.RECIPE.value)
    db.session.add(mi); db.session.flush()
    db.session.add(RecipeLine(menu_item_id=mi.id, inventory_item_id=rice,
                              quantity=Decimal("0.2"), unit="kg"))
    db.session.commit()
    return mi.id


@pytest.fixture
def soda(app):
    """A bottle of soda sold DIRECT: KSh 100, 30 in the store."""
    from app.extensions import db
    from app.models.menu_item import MenuItem, PrepStation, StockTracking
    from app.models.department import Department
    item = _stocked_item("Soda bottle", "bottle", "30")
    dept = db.session.query(Department).filter_by(name="Bar").first()
    mi = MenuItem(name="Soda", price=Decimal("100"), category="Soft Drinks",
                  prep_station=PrepStation.BAR.value, department_id=dept.id,
                  stock_tracking=StockTracking.DIRECT.value, inventory_item_id=item)
    db.session.add(mi); db.session.commit()
    return mi.id


def _stocked_item(name, unit, qty):
    from app.extensions import db
    from app.models.inventory_item import InventoryItem
    from app.models.department import Department
    from app.models.stock_movement import StockMovement, MovementReason
    from app.models.user import User
    dept = db.session.query(Department).filter_by(name="Kitchen").first()
    item = InventoryItem(name=name, unit=unit, department_id=dept.id, cost_per_unit=Decimal("100"))
    db.session.add(item); db.session.flush()
    owner = db.session.query(User).filter_by(username="owner1").first()
    db.session.add(StockMovement(item_id=item.id, change_amount=Decimal(qty),
                                 reason=MovementReason.PURCHASE.value, actor_id=owner.id,
                                 idempotency_key=f"seed-{uuid.uuid4()}"))
    db.session.commit()
    return item.id


def _set_discount_ceiling(client, owner_token, percent):
    rv = client.patch("/admin/settings", headers=H(owner_token),
                      json={"event_discount_max_percent": percent})
    assert rv.status_code == 200, rv.get_json()


def _plan(client, token, event_id, menu_item_id, plates, **extra):
    return client.post(f"/events/{event_id}/menu", headers=H(token),
                       json={"menu_item_id": menu_item_id, "quantity": plates, **extra})


# ── The menu ──────────────────────────────────────────────────────────────────

class TestTheManagerPlansTheMenu:

    def test_a_manager_plans_dishes_and_plates(self, client, manager_token, event_id, pilau):
        rv = _plan(client, manager_token, event_id, pilau, 40)
        assert rv.status_code == 201, rv.get_json()
        line = rv.get_json()
        assert line["menu_price"] == "800.00"
        assert line["discount_per_unit"] == "0.00"
        assert line["charged_per_unit"] == "800.00"
        assert line["line_total"] == "32000.00"

    def test_staff_cannot_plan_an_events_menu(self, client, waiter_token, event_id, pilau):
        assert _plan(client, waiter_token, event_id, pilau, 40).status_code == 403

    def test_a_dish_nobody_has_classified_cannot_be_planned(
            self, client, manager_token, event_id):
        from app.extensions import db
        from app.models.menu_item import MenuItem, PrepStation
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        mi = MenuItem(name="Mystery Stew", price=Decimal("500"), prep_station=PrepStation.KITCHEN.value,
                      department_id=dept.id)  # UNTRACKED by default
        db.session.add(mi); db.session.commit()
        rv = _plan(client, manager_token, event_id, mi.id, 10)
        assert rv.status_code == 400
        assert "Mystery Stew" in rv.get_json()["error"]

    def test_plates_must_be_a_positive_number(self, client, manager_token, event_id, pilau):
        for bad in (0, -5, "lots"):
            rv = _plan(client, manager_token, event_id, pilau, bad)
            assert rv.status_code == 400, bad

    def test_the_menu_shows_the_totals(self, client, manager_token, owner_token, event_id, pilau, soda):
        _set_discount_ceiling(client, owner_token, 20)
        _plan(client, manager_token, event_id, pilau, 40, discount_per_unit="100",
              discount_reason="Package deal")
        _plan(client, manager_token, event_id, soda, 50)
        menu = client.get(f"/events/{event_id}/menu", headers=H(manager_token)).get_json()
        assert menu["totals"] == {
            "menu_value": "37000.00",   # 40×800 + 50×100
            "discount":   "4000.00",    # 40×100
            "to_charge":  "33000.00",
        }

    def test_a_removed_line_stops_counting(self, client, manager_token, event_id, pilau):
        line = _plan(client, manager_token, event_id, pilau, 40).get_json()
        rv = client.post(f"/events/{event_id}/menu/{line['id']}/remove", headers=H(manager_token))
        assert rv.status_code == 200
        menu = client.get(f"/events/{event_id}/menu", headers=H(manager_token)).get_json()
        assert menu["lines"] == [] and menu["totals"]["to_charge"] == "0.00"


# ── Discounts ─────────────────────────────────────────────────────────────────

class TestDiscountsAreRecordedNotHidden:

    def test_with_no_ceiling_set_a_manager_cannot_discount(
            self, client, manager_token, event_id, pilau):
        """Same rule as budgets: nothing is delegated until the owner delegates it."""
        rv = _plan(client, manager_token, event_id, pilau, 40,
                   discount_per_unit="50", discount_reason="Regular client")
        assert rv.status_code == 403
        assert "owner" in rv.get_json()["error"].lower()

    def test_a_manager_discounts_within_the_owners_ceiling(
            self, client, manager_token, owner_token, event_id, pilau):
        _set_discount_ceiling(client, owner_token, 15)
        rv = _plan(client, manager_token, event_id, pilau, 40,
                   discount_per_unit="120", discount_reason="Package deal")   # exactly 15%
        assert rv.status_code == 201, rv.get_json()
        line = rv.get_json()
        assert line["charged_per_unit"] == "680.00"
        assert line["discount_reason"] == "Package deal"
        assert line["discount_by"] == "manager1"

    def test_above_the_ceiling_only_the_owner_may_discount(
            self, client, manager_token, owner_token, event_id, pilau):
        _set_discount_ceiling(client, owner_token, 15)
        rv = _plan(client, manager_token, event_id, pilau, 40,
                   discount_per_unit="200", discount_reason="Big client")    # 25%
        assert rv.status_code == 403
        assert "15%" in rv.get_json()["error"]
        rv = _plan(client, owner_token, event_id, pilau, 40,
                   discount_per_unit="200", discount_reason="Big client")
        assert rv.status_code == 201

    def test_a_discount_needs_a_reason(self, client, manager_token, owner_token, event_id, pilau):
        _set_discount_ceiling(client, owner_token, 50)
        rv = _plan(client, manager_token, event_id, pilau, 40, discount_per_unit="100")
        assert rv.status_code == 400
        assert "reason" in rv.get_json()["error"].lower()

    def test_a_discount_cannot_exceed_the_price(self, client, owner_token, event_id, pilau):
        rv = _plan(client, owner_token, event_id, pilau, 40,
                   discount_per_unit="900", discount_reason="Free")
        assert rv.status_code == 400

    def test_changing_a_discount_is_checked_the_same_way(
            self, client, manager_token, owner_token, event_id, pilau):
        _set_discount_ceiling(client, owner_token, 15)
        line = _plan(client, manager_token, event_id, pilau, 40).get_json()
        rv = client.patch(f"/events/{event_id}/menu/{line['id']}", headers=H(manager_token),
                          json={"discount_per_unit": "400", "discount_reason": "Friend"})
        assert rv.status_code == 403
        rv = client.patch(f"/events/{event_id}/menu/{line['id']}", headers=H(manager_token),
                          json={"quantity": 60})
        assert rv.status_code == 200 and rv.get_json()["line_total"] == "48000.00"

    def test_the_owner_ceiling_is_an_owner_setting(self, client, manager_token):
        rv = client.patch("/admin/settings", headers=H(manager_token),
                          json={"event_discount_max_percent": 90})
        assert rv.status_code == 403


# ── Stock check and buy list ──────────────────────────────────────────────────

class TestTheSystemChecksStockBeforeTheDay:

    def test_enough_stock_reads_ready(self, client, manager_token, event_id, pilau):
        _plan(client, manager_token, event_id, pilau, 40)     # 8 kg of 10
        stock = client.get(f"/events/{event_id}/menu", headers=H(manager_token)).get_json()["stock"]
        assert stock["ready"] is True
        rice = stock["items"][0]
        assert (rice["name"], rice["needed"], rice["in_store"], rice["short"]) == \
               ("Rice", "8.0000", "10.0000", "0.0000")

    def test_too_little_stock_names_what_is_short(self, client, manager_token, event_id, pilau, soda):
        _plan(client, manager_token, event_id, pilau, 100)    # 20 kg of 10
        _plan(client, manager_token, event_id, soda, 20)      # 20 of 30 — fine
        stock = client.get(f"/events/{event_id}/menu", headers=H(manager_token)).get_json()["stock"]
        assert stock["ready"] is False
        short = {i["name"]: i["short"] for i in stock["items"] if Decimal(i["short"]) > 0}
        assert short == {"Rice": "10.0000"}

    def test_another_event_planned_first_uses_the_same_store(
            self, client, manager_token, event_type_id, pilau):
        """Each event alone looks covered; together they are not."""
        earlier = _event(client, manager_token, event_type_id, days=3, title="Thursday Meeting")
        later = _event(client, manager_token, event_type_id, days=6, title="Saturday Wedding")
        _plan(client, manager_token, earlier, pilau, 30)      # 6 kg
        _plan(client, manager_token, later, pilau, 30)        # 6 kg — only 4 left after Thursday
        stock = client.get(f"/events/{later}/menu", headers=H(manager_token)).get_json()["stock"]
        rice = stock["items"][0]
        assert rice["planned_by_earlier_events"] == "6.0000"
        assert rice["short"] == "2.0000"
        assert client.get(f"/events/{earlier}/menu",
                          headers=H(manager_token)).get_json()["stock"]["ready"] is True

    def test_plates_already_on_the_kitchen_board_count_against_the_store(
            self, client, manager_token, event_id, pilau):
        """Found on the live wedding: 90 plates sent (not yet cooked, so no stock
        has moved) and 30 more planned read "covered" — 6 kg needed against
        19.4 kg in the store, ignoring the 18 kg the board had already promised."""
        _plan(client, manager_token, event_id, pilau, 40)                 # 8 kg of 10
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        _plan(client, manager_token, event_id, pilau, 10)                 # 2 more kg
        rice = client.get(f"/events/{event_id}/menu",
                          headers=H(manager_token)).get_json()["stock"]["items"][0]
        assert rice["waiting_on_boards"] == "8.0000"
        assert rice["short"] == "0.0000"                                  # 10 exactly
        _plan(client, manager_token, event_id, pilau, 5)                  # 1 kg over
        stock = client.get(f"/events/{event_id}/menu", headers=H(manager_token)).get_json()["stock"]
        assert stock["ready"] is False and stock["items"][0]["short"] == "1.0000"

    def test_confirming_writes_the_buy_list_once(self, client, manager_token, event_id, pilau):
        from app.extensions import db
        from app.models.purchase_request import PurchaseRequest
        _plan(client, manager_token, event_id, pilau, 100)    # 10 kg short
        assert client.post(f"/events/{event_id}/confirm", headers=H(manager_token)).status_code == 200
        client.post(f"/events/{event_id}/buy-list", headers=H(manager_token))   # asking again
        requests = db.session.query(PurchaseRequest).filter_by(event_id=event_id).all()
        assert len(requests) == 1
        pr = requests[0]
        assert pr.quantity == Decimal("10") and pr.system_generated is True

    def test_the_manager_can_approve_the_events_buy_list_inside_the_budget(
            self, client, manager_token, event_id, pilau, rice):
        """Found reading the approval rule: nobody may approve their own request,
        and the buy list recorded the manager who pressed the button as the
        requester — so with one manager, every event's shopping went to the
        owner and the budget delegation never applied. The list is the
        system's request; the audit log still says which manager wrote it."""
        from app.extensions import db
        from app.models.budget import Budget
        from app.models.department import Department
        from app.models.purchase_request import PurchaseRequest
        from app.models.user import User
        _plan(client, manager_token, event_id, pilau, 100)                # 10 kg short
        client.post(f"/events/{event_id}/buy-list", headers=H(manager_token))
        pr = db.session.query(PurchaseRequest).filter_by(event_id=event_id).one()
        kitchen = db.session.query(Department).filter_by(name="Kitchen").one()
        owner = db.session.query(User).filter_by(username="owner1").one()
        db.session.add(Budget(department_id=kitchen.id, amount=Decimal("50000"),
                              period=datetime.now(timezone.utc).strftime("%Y-%m"), set_by_id=owner.id))
        db.session.commit()
        assert client.post(f"/inventory/purchase-requests/{pr.id}/propose", headers=H(manager_token),
                           json={"estimated_cost": "2500"}).status_code == 200
        rv = client.post(f"/inventory/purchase-requests/{pr.id}/approve", headers=H(manager_token),
                         json={"action": "approve"})
        assert rv.status_code == 200, rv.get_json()
        listed = next(r for r in client.get("/inventory/purchase-requests",
                                            headers=H(manager_token)).get_json() if r["id"] == pr.id)
        assert listed["event"]["title"] == "Otieno Wedding"
        assert (listed["quantity"], listed["requested_by"]) == ("10.0000", "system")

    def test_confirming_tells_the_chef_the_bar_and_the_managers(
            self, client, manager_token, event_id, pilau, soda):
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.user import User
        _plan(client, manager_token, event_id, pilau, 40)
        _plan(client, manager_token, event_id, soda, 50)
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        notes = db.session.query(Notification).filter_by(reference_id=event_id,
                                                         reference_type="event_menu").all()
        by_user = {db.session.get(User, n.recipient_user_id).username: n.body for n in notes}
        assert "40 × Pilau" in by_user["chef1"] and "Soda" not in by_user["chef1"]
        assert "50 × Soda" in by_user["manager1"]

    def test_the_managers_notice_names_what_is_short_even_if_already_requested(
            self, client, manager_token, event_id, pilau):
        """Found in Chrome: the buy list was written before confirming, so confirm
        wrote nothing new — and the notice said "The store covers it." while
        4.6 kg of chicken was still short."""
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.user import User
        _plan(client, manager_token, event_id, pilau, 100)             # 10 kg rice short
        client.post(f"/events/{event_id}/buy-list", headers=H(manager_token))
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        manager = db.session.query(User).filter_by(username="manager1").one()
        body = db.session.query(Notification).filter_by(
            reference_id=event_id, reference_type="event_menu", recipient_user_id=manager.id).one().body
        assert "covers" not in body
        assert "10 kg Rice" in body

    def test_a_menu_changed_after_confirming_tells_the_kitchen_again(
            self, client, manager_token, event_id, pilau):
        """Found in Chrome: 120 plates became 90 after confirming, and the chef's
        only notice still said 120."""
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.user import User
        line = _plan(client, manager_token, event_id, pilau, 40).get_json()
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        client.patch(f"/events/{event_id}/menu/{line['id']}", headers=H(manager_token),
                     json={"quantity": 30})
        chef = db.session.query(User).filter_by(username="chef1").one()
        bodies = [n.body for n in db.session.query(Notification).filter_by(
            reference_id=event_id, reference_type="event_menu", recipient_user_id=chef.id
        ).order_by(Notification.scheduled_for_utc)]
        assert len(bodies) == 2
        assert "40 × Pilau" in bodies[0] and "30 × Pilau" in bodies[1]
        # Saving the same plan again does not repeat itself.
        client.patch(f"/events/{event_id}/menu/{line['id']}", headers=H(manager_token),
                     json={"quantity": 30})
        assert db.session.query(Notification).filter_by(
            reference_id=event_id, reference_type="event_menu", recipient_user_id=chef.id).count() == 2


# ── The event's bill ──────────────────────────────────────────────────────────

class TestTheEventHasItsOwnBill:

    def _confirmed(self, client, manager_token, event_id):
        rv = client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        assert rv.status_code == 200
        return client.get(f"/events/{event_id}/bill", headers=H(manager_token)).get_json()

    def test_confirming_opens_the_bill_and_charges_the_venue_once(
            self, client, manager_token, event_id):
        bill = self._confirmed(client, manager_token, event_id)
        assert bill["tab_type"] == "EVENT"
        assert bill["charged"] == "50000.00" and bill["owing"] == "50000.00"
        assert bill["lines"] == [{"description": bill["lines"][0]["description"], "amount": "50000.00"}]
        assert bill["lines"][0]["description"].startswith("Venue hire — Lawn")
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))   # double tap
        again = client.get(f"/events/{event_id}/bill", headers=H(manager_token)).get_json()
        assert again["charged"] == "50000.00"

    def test_sending_the_menu_puts_real_orders_on_the_bill_at_the_discounted_price(
            self, client, manager_token, owner_token, event_id, pilau):
        from app.extensions import db
        from app.models.order_item import OrderItem
        _set_discount_ceiling(client, owner_token, 20)
        _plan(client, manager_token, event_id, pilau, 40, discount_per_unit="100",
              discount_reason="Package deal")
        self._confirmed(client, manager_token, event_id)
        rv = client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        assert rv.status_code == 200, rv.get_json()
        bill = client.get(f"/events/{event_id}/bill", headers=H(manager_token)).get_json()
        assert bill["charged"] == "78000.00"     # venue 50,000 + 40 × 700
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        assert oi.status == "PENDING" and oi.prep_station_snapshot == "KITCHEN"   # on the kitchen board
        # Sent once only.
        again = client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        assert again.status_code == 400

    def test_sent_dishes_move_stock_when_the_kitchen_marks_them_ready(
            self, client, manager_token, chef_token, event_type_id, pilau, rice):
        from app.extensions import db
        from app.models.order_item import OrderItem
        from app.services.stock import get_current_stock
        event_id = _event(client, manager_token, event_type_id, days=0)   # the event's own day
        _plan(client, manager_token, event_id, pilau, 40)
        self._confirmed(client, manager_token, event_id)
        client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        assert client.post(f"/order-items/{oi.id}/receive", headers=H(chef_token)).status_code == 200
        assert client.post(f"/order-items/{oi.id}/ready", headers=H(chef_token)).status_code == 200
        assert get_current_stock(rice) == Decimal("2")          # 10 − 40 × 0.2

    def test_a_sent_line_can_no_longer_be_changed(self, client, manager_token, event_id, pilau):
        line = _plan(client, manager_token, event_id, pilau, 10).get_json()
        self._confirmed(client, manager_token, event_id)
        client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        rv = client.patch(f"/events/{event_id}/menu/{line['id']}", headers=H(manager_token),
                          json={"quantity": 99})
        assert rv.status_code == 400

    def test_a_planned_event_cannot_send_to_the_kitchen(self, client, manager_token, event_id, pilau):
        _plan(client, manager_token, event_id, pilau, 10)
        rv = client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        assert rv.status_code == 400
        assert "confirm" in rv.get_json()["error"].lower()

    def test_sending_what_the_store_cannot_cover_is_refused(
            self, client, manager_token, event_id, pilau):
        _plan(client, manager_token, event_id, pilau, 100)   # 20 kg, 10 in store
        self._confirmed(client, manager_token, event_id)
        rv = client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        assert rv.status_code == 409
        assert "Rice" in rv.get_json()["error"]

    def test_sending_more_than_the_board_leaves_in_the_store_is_refused(
            self, client, manager_token, event_id, pilau):
        """The till's sold-out check reads the shelf only. 40 plates on the board
        (8 kg promised) plus 15 more (3 kg) is 11 kg against 10 — refused, and
        the refusal says what to buy."""
        _plan(client, manager_token, event_id, pilau, 40)
        self._confirmed(client, manager_token, event_id)
        client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        _plan(client, manager_token, event_id, pilau, 15)
        rv = client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        assert rv.status_code == 409
        assert "1 kg Rice" in rv.get_json()["error"]

    def test_only_a_manager_takes_the_events_money(
            self, client, manager_token, waiter_token, event_id):
        tab_id = self._confirmed(client, manager_token, event_id)["tab_id"]
        pay = {"method": "CASH", "amount": "20000", "idempotency_key": str(uuid.uuid4())}
        rv = client.post(f"/tabs/{tab_id}/payments", headers=H(waiter_token), json=pay)
        assert rv.status_code == 403
        assert "manager" in rv.get_json()["error"].lower()
        pay["idempotency_key"] = str(uuid.uuid4())
        assert client.post(f"/tabs/{tab_id}/payments", headers=H(manager_token), json=pay).status_code == 201
        bill = client.get(f"/events/{event_id}/bill", headers=H(manager_token)).get_json()
        assert (bill["paid"], bill["owing"]) == ("20000.00", "30000.00")

    def test_staff_not_working_the_event_cannot_charge_its_bill(
            self, client, manager_token, waiter_token, event_id, drink_item_id):
        tab_id = self._confirmed(client, manager_token, event_id)["tab_id"]
        rv = client.post("/orders", headers=H(waiter_token),
                         json={"tab_id": tab_id, "items": [{"menu_item_id": drink_item_id}]})
        assert rv.status_code == 403
        assert "event" in rv.get_json()["error"].lower()

    def test_staff_assigned_to_the_event_can_charge_its_bill(
            self, client, manager_token, waiter_token, event_id, drink_item_id, waiter_profile):
        tab_id = self._confirmed(client, manager_token, event_id)["tab_id"]
        client.post(f"/events/{event_id}/assignments", headers=H(manager_token),
                    json={"employee_id": waiter_profile.id, "job": "SERVICE", "role_on_event": "Bar"})
        rv = client.post("/orders", headers=H(waiter_token),
                         json={"tab_id": tab_id, "items": [{"menu_item_id": drink_item_id}]})
        assert rv.status_code == 201, rv.get_json()

    def test_nobody_opens_an_event_bill_by_hand(self, client, owner_token):
        rv = client.post("/tabs", headers=H(owner_token), json={"tab_type": "EVENT", "reference": "x"})
        assert rv.status_code == 403


# ── The owner sees it ─────────────────────────────────────────────────────────

class TestTheOwnerSeesEveryEvent:

    def test_the_owner_sees_value_discount_billed_paid_and_owing(
            self, client, manager_token, owner_token, event_id, pilau):
        _set_discount_ceiling(client, owner_token, 20)
        _plan(client, manager_token, event_id, pilau, 40, discount_per_unit="100",
              discount_reason="Package deal")
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        client.post(f"/events/{event_id}/send", headers=H(manager_token), json={})
        rows = client.get("/dashboard/events", headers=H(owner_token)).get_json()
        row = next(r for r in rows if r["id"] == event_id)
        assert row["venue"]["name"].startswith("Lawn")
        assert (row["menu_value"], row["discount"], row["charged"], row["paid"], row["owing"]) == \
               ("32000.00", "4000.00", "78000.00", "0.00", "78000.00")
        assert row["discount_by"] == ["manager1"]

    def test_a_manager_cannot_open_the_owners_event_view(self, client, manager_token):
        assert client.get("/dashboard/events", headers=H(manager_token)).status_code == 403


# ── The kitchen board ─────────────────────────────────────────────────────────

class TestEventDishesOnTheKitchenBoard:
    """Wachira, after watching a 120-plate wedding sit on the board beside a
    burger: event orders need their own place, must be described properly, and
    nobody may start one before the event's day — cooking takes the stock."""

    def _sent(self, client, manager_token, event_type_id, pilau, days):
        eid = _event(client, manager_token, event_type_id, days=days, guests=120, title="Mwangi Wedding")
        _plan(client, manager_token, eid, pilau, 40)
        client.post(f"/events/{eid}/confirm", headers=H(manager_token))
        client.post(f"/events/{eid}/send", headers=H(manager_token), json={})
        return eid

    def test_the_board_describes_the_event(self, client, manager_token, chef_token, event_type_id, pilau):
        eid = self._sent(client, manager_token, event_type_id, pilau, days=7)
        ticket = next(i for i in client.get("/kitchen/queue", headers=H(chef_token)).get_json()
                      if i["menu_item"] == "Pilau")
        ev = ticket["event"]
        assert (ev["id"], ev["title"], ev["expected_guests"]) == (eid, "Mwangi Wedding", 120)
        assert ev["venue"].startswith("Lawn") and ev["starts_at"]
        assert ev["can_start"] is False and ev["opens_on"]

    def test_an_ordinary_order_carries_no_event(self, client, waiter_token, chef_token, drink_item_id,
                                                food_item_id, manager_token):
        from tests.helpers import open_tab
        tab = open_tab(client, assign_to="waiter1")
        order = client.post("/orders", headers=H(waiter_token),
                            json={"tab_id": tab["id"], "items": [{"menu_item_id": food_item_id}]}).get_json()
        client.post(f"/orders/{order['id']}/send", headers=H(waiter_token))
        tickets = client.get("/kitchen/queue", headers=H(chef_token)).get_json()
        assert tickets and all(i["event"] is None for i in tickets)

    def test_nobody_starts_an_event_dish_before_the_day(
            self, client, manager_token, chef_token, event_type_id, pilau):
        from app.extensions import db
        from app.models.order_item import OrderItem
        self._sent(client, manager_token, event_type_id, pilau, days=7)
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        for who in (chef_token, manager_token):
            rv = client.post(f"/order-items/{oi.id}/receive", headers=H(who))
            assert rv.status_code == 409
            assert "Mwangi Wedding" in rv.get_json()["error"]
        assert db.session.get(OrderItem, oi.id).status == "PENDING"

    def test_on_the_day_the_kitchen_starts_it(self, client, manager_token, chef_token, event_type_id, pilau):
        from app.extensions import db
        from app.models.order_item import OrderItem
        self._sent(client, manager_token, event_type_id, pilau, days=0)
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        assert client.post(f"/order-items/{oi.id}/receive", headers=H(chef_token)).status_code == 200
        ticket = client.get("/kitchen/queue", headers=H(chef_token)).get_json()[0]
        assert ticket["event"]["can_start"] is True


# ── The event crew ────────────────────────────────────────────────────────────

class TestTheEventCrew:
    """The manager decides who handles an event's food, drinks and service, and
    the system tells exactly those people — not whoever pressed a button."""

    def _assign(self, client, manager_token, event_id, profile_id, job, **extra):
        return client.post(f"/events/{event_id}/assignments", headers=H(manager_token),
                           json={"employee_id": profile_id, "job": job, **extra})

    def test_every_crew_member_has_a_job_the_system_understands(
            self, client, manager_token, event_id, waiter_profile):
        rv = client.post(f"/events/{event_id}/assignments", headers=H(manager_token),
                         json={"employee_id": waiter_profile.id, "role_on_event": "Helping out"})
        assert rv.status_code == 400
        assert "kitchen, bar, service or setup" in rv.get_json()["error"].lower()
        rv = self._assign(client, manager_token, event_id, waiter_profile.id, "SERVICE",
                          role_on_event="Head waiter")
        assert rv.status_code == 201
        assert (rv.get_json()["job"], rv.get_json()["role_on_event"]) == ("SERVICE", "Head waiter")
        # No description given: the job is the description.
        rv = self._assign(client, manager_token, event_id, waiter_profile.id, "SETUP")
        assert rv.get_json()["role_on_event"] == "Setup"

    def test_the_kitchen_crew_is_told_the_plates_and_the_bar_crew_the_drinks(
            self, client, manager_token, kitchen_token, event_id, pilau, soda, waiter_profile):
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        cook = db.session.query(User).filter_by(username="kitchen1").one()
        cook_profile = db.session.query(EmployeeProfile).filter_by(user_id=cook.id).one()
        self._assign(client, manager_token, event_id, cook_profile.id, "KITCHEN")
        self._assign(client, manager_token, event_id, waiter_profile.id, "BAR")
        _plan(client, manager_token, event_id, pilau, 40)
        _plan(client, manager_token, event_id, soda, 50)
        client.post(f"/events/{event_id}/confirm", headers=H(manager_token))
        told = lambda username: [n.body for n in db.session.query(Notification).filter_by(
            reference_id=event_id, reference_type="event_menu",
            recipient_user_id=db.session.query(User).filter_by(username=username).one().id)]
        assert any("40 × Pilau" in b for b in told("kitchen1"))
        assert not any("Soda" in b for b in told("kitchen1"))
        assert any("50 × Soda" in b for b in told("waiter1"))

    def test_ready_for_pickup_goes_to_the_service_crew_not_the_sender(
            self, client, manager_token, chef_token, kitchen_token, event_type_id, pilau, waiter_profile):
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.order_item import OrderItem
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        eid = _event(client, manager_token, event_type_id, days=0)
        self._assign(client, manager_token, eid, waiter_profile.id, "SERVICE")
        # A second server: a message key shared per dish would refuse this one.
        second = db.session.query(EmployeeProfile).join(User).filter(User.username == "kitchen1").one()
        self._assign(client, manager_token, eid, second.id, "SERVICE")
        _plan(client, manager_token, eid, pilau, 10)
        client.post(f"/events/{eid}/confirm", headers=H(manager_token))
        client.post(f"/events/{eid}/send", headers=H(manager_token), json={})
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        client.post(f"/order-items/{oi.id}/receive", headers=H(chef_token))
        client.post(f"/order-items/{oi.id}/ready", headers=H(chef_token))
        ready = db.session.query(Notification).filter_by(reference_id=oi.id, reference_type="order_ready").all()
        who = {db.session.get(User, n.recipient_user_id).username for n in ready}
        assert who == {"waiter1", "kitchen1"}
        assert "Otieno Wedding" in ready[0].body

    def test_with_no_service_crew_the_sender_is_still_told(
            self, client, manager_token, chef_token, event_type_id, pilau):
        from app.extensions import db
        from app.models.notification import Notification
        from app.models.order_item import OrderItem
        from app.models.user import User
        eid = _event(client, manager_token, event_type_id, days=0)
        _plan(client, manager_token, eid, pilau, 10)
        client.post(f"/events/{eid}/confirm", headers=H(manager_token))
        client.post(f"/events/{eid}/send", headers=H(manager_token), json={})
        oi = db.session.query(OrderItem).filter_by(menu_item_id=pilau).one()
        client.post(f"/order-items/{oi.id}/receive", headers=H(chef_token))
        client.post(f"/order-items/{oi.id}/ready", headers=H(chef_token))
        ready = db.session.query(Notification).filter_by(reference_id=oi.id, reference_type="order_ready").all()
        assert {db.session.get(User, n.recipient_user_id).username for n in ready} == {"manager1"}


# ── Coming up, on the kitchen's Events tab ────────────────────────────────────

class TestTheKitchenSeesEventsComingUp:
    """One tablet, two tabs: Orders and Events. The Events tab shows what each
    upcoming event will need from THIS station, days before anything is sent."""

    def test_planned_plates_show_days_ahead_for_the_right_station(
            self, client, manager_token, chef_token, kitchen_token, event_type_id, pilau, soda):
        from app.extensions import db
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        eid = _event(client, manager_token, event_type_id, days=5, guests=120, title="Mwangi Wedding")
        cook = db.session.query(EmployeeProfile).join(User).filter(User.username == "kitchen1").one()
        client.post(f"/events/{eid}/assignments", headers=H(manager_token),
                    json={"employee_id": cook.id, "job": "KITCHEN"})
        _plan(client, manager_token, eid, pilau, 40)
        _plan(client, manager_token, eid, soda, 50)
        client.post(f"/events/{eid}/confirm", headers=H(manager_token))
        rows = client.get("/events/prep?station=KITCHEN", headers=H(chef_token)).get_json()
        row = next(r for r in rows if r["event"]["id"] == eid)
        assert (row["event"]["title"], row["event"]["expected_guests"], row["event"]["can_start"]) == \
               ("Mwangi Wedding", 120, False)
        assert row["crew"] == ["Test Kitchen"]
        assert row["planned"] == [{"name": "Pilau", "plates": "40"}]      # the bar's Soda is not here

    def test_a_planned_event_not_yet_confirmed_is_not_shown(
            self, client, manager_token, chef_token, event_id, pilau):
        _plan(client, manager_token, event_id, pilau, 40)
        assert client.get("/events/prep?station=KITCHEN", headers=H(chef_token)).get_json() == []

    def test_only_that_station_or_a_manager_may_look(self, client, waiter_token, manager_token):
        assert client.get("/events/prep?station=KITCHEN", headers=H(waiter_token)).status_code == 403
        assert client.get("/events/prep?station=KITCHEN", headers=H(manager_token)).status_code == 200
        assert client.get("/events/prep?station=SPA", headers=H(manager_token)).status_code == 400
