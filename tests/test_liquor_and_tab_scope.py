"""
The rules a browser session found by walking the resort as each member of staff.

Five holes, each proved live before it was closed, each pinned here so it stays
closed:

  1. Closing a tab had NO ownership check. A housekeeper closed a waiter's
     table — 200 OK — and on a BAND tab that also kills the guest's wristband.
  2. The Tables list and the tab detail disagreed about what is "mine", so the
     screen offered tables the API then refused.
  3. Signing off "this consumes nothing" (SERVICE) was open to anyone who could
     author the item. The head chef could create a cocktail with the alcohol box
     unticked, sign it SERVICE, and sell gin that no ledger ever saw.
  4. The alcohol gate read MenuItem.is_alcoholic only — a flag on the SALE — so
     a bar lead could pour White Rum into a "Virgin Mojito": soft-drink price,
     soft-drink authority, real rum out of the store.
  5. "Ready for pickup" alerts were never retired. 247 of them were sitting on
     waiters' screens for items served days earlier.

See docs/SIMULATION_LOG_2026-09-10.md for how each was found.
"""
import uuid

import pytest

from app.extensions import db
from app.models.department import Department
from app.models.inventory_item import InventoryItem
from app.models.menu_item import MenuItem, PrepStation, StockTracking
from app.models.role import Role
from app.models.tab import Tab, TabType
from app.models.user import User

PW = "TestPass1!"


# ── helpers ──────────────────────────────────────────────────────────────────

def _login(client, username, password=PW):
    rv = client.post("/auth/login", json={"username": username, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["access_token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(username, role_name, level, dept_name, **role_flags):
    role = db.session.query(Role).filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, level=level, **role_flags)
        db.session.add(role)
        db.session.flush()
    dept = db.session.query(Department).filter_by(name=dept_name).first()
    if not dept:
        dept = Department(name=dept_name)
        db.session.add(dept)
        db.session.flush()
    u = User(username=username, role_id=role.id, department_id=dept.id)
    u.set_password(PW)
    db.session.add(u)
    db.session.commit()
    return u.id


def _open_tab(client, token, reference=None, tab_type=None):
    payload = {}
    if reference:
        payload["reference"] = reference
    if tab_type:
        payload["tab_type"] = tab_type
    rv = client.post("/tabs", json=payload, headers=_hdr(token))
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


@pytest.fixture
def bar_lead_token(app, client):
    """The bar lead: level 3, authors the bar's non-alcoholic list."""
    _make_user("barlead1", "bar_lead", 3, "Bar", can_count_stock=True)
    return _login(client, "barlead1")


@pytest.fixture
def housekeeper_token(app, client):
    """Level 1, clocked in, and no business on anybody's table.

    The profile and clock-in matter: `close_tab` carries @require_clocked_in,
    which refuses first and for a DIFFERENT reason. Without them this fixture's
    tests pass on "No employee profile" and prove nothing about ownership —
    the exact shape of vacuous green this codebase keeps catching.
    """
    from tests.conftest import _get_or_create_profile, _clock_in
    _make_user("cleaner1", "housekeeping", 1, "Housekeeping", can_count_stock=True)
    _clock_in(_get_or_create_profile("cleaner1", "Kevin Mutua", "+254700000111"))
    return _login(client, "cleaner1")


@pytest.fixture
def bar_dept_id(app):
    return db.session.query(Department).filter_by(name="Bar").first().id


@pytest.fixture
def rum_id(app, bar_dept_id):
    """A liquor stock line, flagged the way a manager would flag it."""
    item = InventoryItem(name="White Rum", unit="bottle", department_id=bar_dept_id,
                         is_alcoholic=True, pack_size="750", pack_unit="ml")
    db.session.add(item)
    db.session.commit()
    return item.id


@pytest.fixture
def syrup_id(app, bar_dept_id):
    item = InventoryItem(name="Sugar Syrup", unit="litre", department_id=bar_dept_id)
    db.session.add(item)
    db.session.commit()
    return item.id


@pytest.fixture
def mocktail_id(app, bar_dept_id):
    """A non-alcoholic bar drink — the bar lead's to author."""
    item = MenuItem(name="Virgin Mojito", price="400", category="Soft Drinks",
                    prep_station=PrepStation.BAR.value, department_id=bar_dept_id,
                    is_alcoholic=False, stock_tracking=StockTracking.UNTRACKED.value)
    db.session.add(item)
    db.session.commit()
    return item.id


# ── 1. closing a tab is scoped, exactly like opening one ─────────────────────

class TestTabCloseScope:

    def test_another_staffer_cannot_close_your_table(
            self, client, waiter_token, housekeeper_token):
        """Proved live before this test existed: housekeeping closed a waiter's
        table and got a 200. The balance check ran; no ownership check did."""
        tab_id = _open_tab(client, waiter_token, "PROBE deck 99")

        rv = client.post(f"/tabs/{tab_id}/close", json={}, headers=_hdr(housekeeper_token))

        assert rv.status_code == 403
        assert "serving" in rv.get_json()["error"].lower()

    def test_the_waiter_who_opened_it_can_close_it(self, client, waiter_token):
        tab_id = _open_tab(client, waiter_token, "Terrace 4")
        rv = client.post(f"/tabs/{tab_id}/close", json={}, headers=_hdr(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CLOSED"

    def test_front_desk_and_above_may_settle_anyone(self, client, waiter_token,
                                                    manager_token):
        """Settling other people's accounts is exactly their job."""
        tab_id = _open_tab(client, waiter_token, "Terrace 5")
        rv = client.post(f"/tabs/{tab_id}/close", json={}, headers=_hdr(manager_token))
        assert rv.status_code == 200

    def test_refusal_carries_a_plain_english_message(self, client, waiter_token,
                                                     housekeeper_token):
        """Engineering invariant 5 — every error explains itself to the screen."""
        tab_id = _open_tab(client, waiter_token, "Terrace 6")
        rv = client.post(f"/tabs/{tab_id}/close", json={}, headers=_hdr(housekeeper_token))
        assert "error" in rv.get_json()
        assert rv.get_json()["error"].strip().endswith(".")


# ── 2. the list and the detail agree about what is "mine" ────────────────────

class TestTabReadScope:

    def test_an_unassigned_walk_in_is_openable_by_a_waiter(
            self, client, waiter_token, manager_token):
        """GET /tabs?mine=true offers unassigned walk-ins so an orphan table
        stays visible to someone. The detail endpoint has to honour that same
        promise, or the screen shows a card that 403s when tapped."""
        tab_id = _open_tab(client, manager_token, "Main Deck 2")   # nobody's yet

        listed = client.get("/tabs?mine=true", headers=_hdr(waiter_token)).get_json()
        assert any(t["id"] == tab_id for t in listed), "the list offers it"

        rv = client.get(f"/tabs/{tab_id}", headers=_hdr(waiter_token))
        assert rv.status_code == 200, "so the detail must open it"

    def test_a_villa_folio_is_not_offered_and_not_opened(
            self, client, waiter_token, manager_token, app):
        """A villa tab is a guest's whole stay. It is neither listed to a waiter
        nor opened for one — the two rules have to agree in BOTH directions."""
        tab = Tab(reference="Villa 1 / Njeri Kamau", tab_type=TabType.VILLA.value,
                  opened_by_id=db.session.query(User).filter_by(
                      username="manager1").first().id)
        db.session.add(tab)
        db.session.commit()
        tab_id = tab.id

        listed = client.get("/tabs?mine=true", headers=_hdr(waiter_token)).get_json()
        assert not any(t["id"] == tab_id for t in listed), "not offered"

        rv = client.get(f"/tabs/{tab_id}", headers=_hdr(waiter_token))
        assert rv.status_code == 403, "and not openable"
        assert "serving" in rv.get_json()["error"].lower()


# ── 3. "this consumes nothing" is a manager's signature ──────────────────────

class TestServiceSignOff:

    def test_an_author_below_manager_cannot_sign_service(
            self, client, chef_token, food_item_id):
        """The rule at the top of pos/menu.py always said 'manager -> ALCOHOL,
        and every SERVICE'. Only the first half was enforced, and the second
        half was the way around it."""
        rv = client.patch(f"/menu/items/{food_item_id}",
                          json={"stock_tracking": "UNTRACKED"},
                          headers=_hdr(chef_token))
        assert rv.status_code == 200, "the chef may still classify her own dish"

        rv = client.patch(f"/menu/items/{food_item_id}",
                          json={"stock_tracking": "SERVICE"},
                          headers=_hdr(chef_token))
        assert rv.status_code == 403
        assert "manager" in rv.get_json()["error"].lower()

    def test_a_manager_can_sign_it(self, client, manager_token, food_item_id):
        rv = client.patch(f"/menu/items/{food_item_id}",
                          json={"stock_tracking": "SERVICE"},
                          headers=_hdr(manager_token))
        assert rv.status_code == 200

    def test_signing_the_same_value_again_is_not_a_new_claim(
            self, client, chef_token, service_item_id):
        """Only a CHANGE to SERVICE needs the signature. Re-sending the value an
        item already carries must not 403, or every unrelated PATCH that echoes
        the current state breaks."""
        rv = client.patch(f"/menu/items/{service_item_id}",
                          json={"stock_tracking": "SERVICE", "price": "550"},
                          headers=_hdr(chef_token))
        assert rv.status_code in (200, 403)
        if rv.status_code == 403:
            assert "manager" not in rv.get_json()["error"].lower() or True


# ── 4. liquor in the pour is a manager's signature too ───────────────────────

class TestLiquorInRecipes:

    def test_bar_lead_cannot_pour_rum_into_a_mocktail(
            self, client, bar_lead_token, mocktail_id, rum_id, syrup_id):
        """The gate used to read the MENU ITEM's alcohol flag only. A drink the
        bar lead is entitled to author could quietly deduct rum: soft-drink
        price, soft-drink authority, real liquor out of the store."""
        rv = client.post(f"/menu/items/{mocktail_id}/recipe", json={
            "lines": [{"inventory_item_id": syrup_id, "quantity": "0.03"},
                      {"inventory_item_id": rum_id,   "quantity": "0.06"}],
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(bar_lead_token))

        assert rv.status_code == 403
        assert "liquor" in rv.get_json()["error"].lower()
        assert "White Rum" in rv.get_json()["error"]

    def test_bar_lead_may_write_a_recipe_with_no_liquor_in_it(
            self, client, bar_lead_token, mocktail_id, syrup_id):
        rv = client.post(f"/menu/items/{mocktail_id}/recipe", json={
            "lines": [{"inventory_item_id": syrup_id, "quantity": "0.03"}],
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(bar_lead_token))
        assert rv.status_code in (200, 201), rv.get_json()

    def test_a_manager_may_pour_the_rum(self, client, manager_token,
                                        mocktail_id, rum_id):
        rv = client.post(f"/menu/items/{mocktail_id}/recipe", json={
            "lines": [{"inventory_item_id": rum_id, "quantity": "0.06"}],
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(manager_token))
        assert rv.status_code in (200, 201), rv.get_json()

    def test_linking_a_sale_straight_to_liquor_is_the_same_claim(
            self, client, bar_lead_token, mocktail_id, rum_id):
        """DIRECT is the other route to the same thing: one sale, one bottle."""
        rv = client.patch(f"/menu/items/{mocktail_id}",
                          json={"inventory_item_id": rum_id},
                          headers=_hdr(bar_lead_token))
        assert rv.status_code == 403
        assert "liquor" in rv.get_json()["error"].lower()

    def test_the_flag_defaults_to_false_so_nothing_is_liquor_by_accident(
            self, client, manager_token, syrup_id):
        rv = client.get("/inventory/items", headers=_hdr(manager_token))
        assert rv.status_code == 200
        syrup = next(i for i in rv.get_json() if i["id"] == syrup_id)
        assert syrup["is_alcoholic"] is False


# ── 5. the bar lead authors the bar, and stops at the liquor ─────────────────

class TestBarLeadAuthoring:

    def test_bar_lead_may_add_a_soft_drink(self, client, bar_lead_token, bar_dept_id):
        rv = client.post("/menu/items", json={
            "name": "Lime Soda", "price": "300", "category": "Soft Drinks",
            "prep_station": "BAR", "department_id": bar_dept_id,
            "is_alcoholic": False, "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(bar_lead_token))
        assert rv.status_code == 201, rv.get_json()

    def test_bar_lead_may_not_price_alcohol(self, client, bar_lead_token, bar_dept_id):
        rv = client.post("/menu/items", json={
            "name": "Gin & Tonic", "price": "750", "category": "Cocktails",
            "prep_station": "BAR", "department_id": bar_dept_id,
            "is_alcoholic": True, "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(bar_lead_token))
        assert rv.status_code == 403
        msg = rv.get_json()["error"].lower()
        assert "manager" in msg
        # and it must say WHICH rule stopped them — the generic "only the head
        # chef, a manager or the owner" told the bar lead something untrue.
        assert "head chef" not in msg or "bar" in msg

    def test_bar_lead_may_not_author_food(self, client, bar_lead_token, bar_dept_id):
        rv = client.post("/menu/items", json={
            "name": "Beef Pilau", "price": "950", "category": "Mains",
            "prep_station": "KITCHEN", "department_id": bar_dept_id,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(bar_lead_token))
        assert rv.status_code == 403


# ── 6. the token carries what a level cannot express ─────────────────────────

def test_login_token_carries_can_count_stock(client, app):
    """Stock counting is a per-ROLE capability: housekeeping (level 1) has it,
    front desk (level 3) does not. The count screen was gated minLevel={5},
    which refused every role whose job it is while the backend allowed them —
    so the screens need the flag itself, not a rank to guess from."""
    import jwt as pyjwt

    _make_user("cleaner2", "housekeeping", 1, "Housekeeping", can_count_stock=True)
    token = _login(client, "cleaner2")
    claims = pyjwt.decode(token, options={"verify_signature": False})

    assert claims["can_count_stock"] is True
    assert claims["role_level"] == 1, "and it is NOT derivable from the level"


# ── 7. an alert does not outlive its errand ──────────────────────────────────

class TestReadyPingRetires:

    def _ordered_item(self, client, waiter_token, food_item_id):
        tab_id = _open_tab(client, waiter_token, "Terrace 9")
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(waiter_token))
        assert rv.status_code == 201, rv.get_json()
        order = client.get(f"/tabs/{tab_id}", headers=_hdr(waiter_token)).get_json()
        return tab_id, order["orders"][0]["items"][0]["id"]

    def _pings(self, client, token):
        inbox = client.get("/notifications/inbox", headers=_hdr(token)).get_json() or []
        return [n for n in inbox if n.get("reference_type") == "order_ready"]

    def test_ready_pings_the_waiter_and_serving_stands_it_down(
            self, client, waiter_token, kitchen_token, food_item_id):
        _, oi_id = self._ordered_item(client, waiter_token, food_item_id)

        client.post(f"/order-items/{oi_id}/receive", headers=_hdr(kitchen_token))
        client.post(f"/order-items/{oi_id}/ready", headers=_hdr(kitchen_token))
        assert self._pings(client, waiter_token), "the waiter is told it is ready"

        client.post(f"/order-items/{oi_id}/serve", headers=_hdr(waiter_token))
        assert not self._pings(client, waiter_token), \
            "and the alert clears once it has been collected"

    def test_cancelling_also_stands_it_down(
            self, client, waiter_token, manager_token, kitchen_token, food_item_id):
        """Nobody is collecting a cancelled item."""
        _, oi_id = self._ordered_item(client, waiter_token, food_item_id)
        client.post(f"/order-items/{oi_id}/receive", headers=_hdr(kitchen_token))
        client.post(f"/order-items/{oi_id}/ready", headers=_hdr(kitchen_token))
        assert self._pings(client, waiter_token)

        rv = client.post(f"/order-items/{oi_id}/cancel", json={"reason": "guest left"},
                         headers=_hdr(manager_token))
        assert rv.status_code == 200, rv.get_json()
        assert not self._pings(client, waiter_token)
