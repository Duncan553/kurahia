"""
test_scenarios_management.py — ADVERSARIAL scenarios for MANAGEMENT OPERATIONS.

Domain: inventory & stock, purchases & suppliers, menu & recipes, equipment,
housekeeping, events, incidents, lost & found, bookable resources, staff accounts.

Every test is written from the endpoint source, not from documentation. Tests
whose name starts with `test_HOLE_` PIN CURRENT (WRONG-LOOKING) BEHAVIOUR — they
pass today and will fail the moment the hole is closed, which is exactly what we
want from a regression pin. Each carries a docstring saying what SHOULD happen.
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.inventory_item import InventoryItem
from app.models.menu_item import MenuItem, PrepStation, StockTracking
from app.models.stock_movement import StockMovement, MovementReason
from app.models.user import User
from app.services.stock import get_current_stock


# ── helpers ───────────────────────────────────────────────────────────────────

def H(token):
    return {"Authorization": f"Bearer {token}"}


def _dept_id(name):
    return db.session.query(Department).filter_by(name=name).first().id


def _user_id(username):
    return db.session.query(User).filter_by(username=username).first().id


def _mk_item(name, dept="General", **kw):
    """Insert an InventoryItem directly (catalogue setup, not the thing under test)."""
    it = InventoryItem(name=name, unit=kw.pop("unit", "kg"),
                       department_id=_dept_id(dept),
                       reorder_level=kw.pop("reorder_level", "0"), **kw)
    db.session.add(it)
    db.session.commit()
    return it.id


def _stock(item_id, qty, actor="owner1"):
    """Put stock on the shelf via the append-only ledger — the only legal way."""
    db.session.add(StockMovement(
        item_id=item_id, change_amount=Decimal(str(qty)),
        reason=MovementReason.PURCHASE.value, actor_id=_user_id(actor),
        idempotency_key=f"seed-{uuid.uuid4()}",
    ))
    db.session.commit()


@pytest.fixture
def item_id(app):
    """Active General-dept item with 20 units on the shelf."""
    iid = _mk_item("Cooking Oil", unit="litre", reorder_level="5")
    _stock(iid, 20)
    return iid


# ══════════════════════════════════════════════════════════════════════════════
# 1. PURCHASES — the receipt rule, the numbers, and who may record one
# ══════════════════════════════════════════════════════════════════════════════

def test_purchase_good_path_moves_stock_and_sets_cost(client, manager_token, item_id):
    rv = client.post("/inventory/purchases", headers=H(manager_token), json={
        "item_id": item_id, "quantity": "10", "actual_cost": "1000",
        "receipt_photo_path": "/uploads/r1.jpg",
    })
    assert rv.status_code == 201, rv.get_json()
    assert get_current_stock(item_id) == Decimal("30")
    item = db.session.get(InventoryItem, item_id)
    assert Decimal(str(item.cost_per_unit)) == Decimal("100")
    assert db.session.query(AuditLog).filter_by(action="inventory.purchase").count() == 1


def test_purchase_without_receipt_is_refused(client, manager_token, item_id):
    rv = client.post("/inventory/purchases", headers=H(manager_token), json={
        "item_id": item_id, "quantity": "10", "actual_cost": "1000",
    })
    assert rv.status_code == 400
    assert "receipt" in rv.get_json()["error"].lower()
    assert get_current_stock(item_id) == Decimal("20")   # nothing moved


def test_purchase_weighted_average_cost_after_two_buys(client, manager_token, app):
    """20 @ 100/u then 20 @ 200/u on an empty shelf → 150/u, not 200/u."""
    iid = _mk_item("Rice")
    for cost in ("2000", "4000"):
        rv = client.post("/inventory/purchases", headers=H(manager_token), json={
            "item_id": iid, "quantity": "20", "actual_cost": cost,
            "receipt_photo_path": "/uploads/r.jpg",
        })
        assert rv.status_code == 201, rv.get_json()
    item = db.session.get(InventoryItem, iid)
    assert Decimal(str(item.cost_per_unit)) == Decimal("150")
    assert get_current_stock(iid) == Decimal("40")


def test_purchase_negative_quantity_and_cost_refused(client, manager_token, item_id):
    base = {"item_id": item_id, "receipt_photo_path": "/uploads/r.jpg"}
    r1 = client.post("/inventory/purchases", headers=H(manager_token),
                     json={**base, "quantity": "-5", "actual_cost": "100"})
    r2 = client.post("/inventory/purchases", headers=H(manager_token),
                     json={**base, "quantity": "5", "actual_cost": "-100"})
    r3 = client.post("/inventory/purchases", headers=H(manager_token),
                     json={**base, "quantity": "abc", "actual_cost": "100"})
    assert (r1.status_code, r2.status_code, r3.status_code) == (400, 400, 400)
    assert get_current_stock(item_id) == Decimal("20")


def test_purchase_by_waiter_is_refused(client, waiter_token, item_id):
    rv = client.post("/inventory/purchases", headers=H(waiter_token), json={
        "item_id": item_id, "quantity": "10", "actual_cost": "100",
        "receipt_photo_path": "/uploads/r.jpg",
    })
    assert rv.status_code == 403
    assert get_current_stock(item_id) == Decimal("20")


def test_purchase_into_disabled_item_is_refused(client, manager_token, item_id):
    assert client.post(f"/inventory/items/{item_id}/disable",
                       headers=H(manager_token)).status_code == 200
    rv = client.post("/inventory/purchases", headers=H(manager_token), json={
        "item_id": item_id, "quantity": "10", "actual_cost": "100",
        "receipt_photo_path": "/uploads/r.jpg",
    })
    assert rv.status_code == 404
    assert get_current_stock(item_id) == Decimal("20")


def test_purchase_replay_of_idempotency_key_writes_stock_once(client, manager_token, item_id):
    body = {"item_id": item_id, "quantity": "10", "actual_cost": "1000",
            "receipt_photo_path": "/uploads/r.jpg", "idempotency_key": "buy-1"}
    assert client.post("/inventory/purchases", headers=H(manager_token), json=body).status_code == 201
    again = client.post("/inventory/purchases", headers=H(manager_token), json=body)
    assert again.status_code == 200 and again.get_json()["duplicate"] is True
    assert get_current_stock(item_id) == Decimal("30")


# ══════════════════════════════════════════════════════════════════════════════
# 2. PURCHASE REQUESTS — the approval chain
# ══════════════════════════════════════════════════════════════════════════════

def test_request_lifecycle_pending_proposed_approved(client, manager_token, owner_token, item_id):
    rv = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "50"})
    assert rv.status_code == 201 and rv.get_json()["status"] == "PENDING"
    pr = rv.get_json()["id"]

    rv = client.post(f"/inventory/purchase-requests/{pr}/propose",
                     headers=H(manager_token), json={"estimated_cost": "5000"})
    assert rv.status_code == 200 and rv.get_json()["status"] == "PROPOSED"

    rv = client.post(f"/inventory/purchase-requests/{pr}/approve",
                     headers=H(owner_token), json={"action": "approve"})
    assert rv.status_code == 200 and rv.get_json()["status"] == "APPROVED"


def test_manager_cannot_approve_a_request(client, manager_token, item_id):
    pr = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "5"}).get_json()["id"]
    rv = client.post(f"/inventory/purchase-requests/{pr}/approve", headers=H(manager_token))
    assert rv.status_code == 403
    assert "owner" in rv.get_json()["error"].lower()


def test_owner_cannot_approve_own_request(client, owner_token, item_id):
    pr = client.post("/inventory/purchase-requests", headers=H(owner_token),
                     json={"item_id": item_id, "quantity": "5"}).get_json()["id"]
    rv = client.post(f"/inventory/purchase-requests/{pr}/approve", headers=H(owner_token))
    assert rv.status_code == 403
    assert "your own" in rv.get_json()["error"].lower()


def test_request_cannot_be_approved_twice(client, manager_token, owner_token, item_id):
    pr = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "5"}).get_json()["id"]
    assert client.post(f"/inventory/purchase-requests/{pr}/approve",
                       headers=H(owner_token)).status_code == 200
    rv = client.post(f"/inventory/purchase-requests/{pr}/approve", headers=H(owner_token))
    assert rv.status_code == 400
    assert "already" in rv.get_json()["error"].lower()


def test_submit_only_works_on_a_draft(client, manager_token, item_id):
    """A PENDING request cannot be re-submitted — states are not skippable."""
    pr = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "5"}).get_json()["id"]
    rv = client.post(f"/inventory/purchase-requests/{pr}/submit", headers=H(manager_token))
    assert rv.status_code == 400 and "DRAFT" in rv.get_json()["error"]


def test_request_for_disabled_item_refused_and_negative_quantity_refused(
        client, manager_token, item_id):
    client.post(f"/inventory/items/{item_id}/disable", headers=H(manager_token))
    r1 = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "5"})
    r2 = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_description": "sugar", "quantity": "-5"})
    assert (r1.status_code, r2.status_code) == (404, 400)


def test_staff_cannot_touch_purchase_requests(client, waiter_token, item_id):
    assert client.get("/inventory/purchase-requests", headers=H(waiter_token)).status_code == 403
    assert client.post("/inventory/purchase-requests", headers=H(waiter_token),
                       json={"item_id": item_id, "quantity": "1"}).status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 3. STOCK LEDGER — can it go negative? who may write to it?
# ══════════════════════════════════════════════════════════════════════════════

def test_spoilage_beyond_stock_is_refused(client, manager_token, item_id):
    rv = client.post("/inventory/movements/spoilage", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "21"})
    assert rv.status_code == 400
    assert "insufficient" in rv.get_json()["error"].lower()
    assert get_current_stock(item_id) == Decimal("20")


def test_spoilage_good_path_and_ledger_sums(client, manager_token, item_id):
    assert client.post("/inventory/movements/spoilage", headers=H(manager_token),
                       json={"item_id": item_id, "quantity": "3"}).status_code == 201
    assert get_current_stock(item_id) == Decimal("17")
    summary = client.get(f"/inventory/movements/summary?item_id={item_id}",
                         headers=H(manager_token)).get_json()
    assert Decimal(summary["totals"]["net"]) == Decimal("17")
    by = {r["reason"]: r for r in summary["by_reason"]}
    assert Decimal(by["SPOILAGE"]["out"]) == Decimal("3")


def test_staff_meal_only_draws_staff_food(client, manager_token, item_id, app):
    rv = client.post("/inventory/movements/staff-meal", headers=H(manager_token),
                     json={"item_id": item_id, "quantity": "1"})
    assert rv.status_code == 400 and "staff-food" in rv.get_json()["error"]

    sid = _mk_item("Staff Beans", is_staff_food=True)
    _stock(sid, 10)
    assert client.post("/inventory/movements/staff-meal", headers=H(manager_token),
                       json={"item_id": sid, "quantity": "2"}).status_code == 201
    assert get_current_stock(sid) == Decimal("8")


def test_staff_meal_is_open_to_level_1_staff(client, waiter_token, app):
    """Documented behaviour: staff-meal has NO manager gate (movements.py:121-157).
    Any clocked-in staffer may write off staff food. Spoilage and sent-back DO
    gate on manager — this asymmetry is deliberate per the endpoint comment."""
    sid = _mk_item("Staff Ugali", is_staff_food=True)
    _stock(sid, 10)
    rv = client.post("/inventory/movements/staff-meal", headers=H(waiter_token),
                     json={"item_id": sid, "quantity": "1"})
    assert rv.status_code == 201
    assert get_current_stock(sid) == Decimal("9")


def test_movement_idempotency_key_replay_does_not_double_deduct(client, manager_token, item_id):
    body = {"item_id": item_id, "quantity": "5", "idempotency_key": "spoil-1"}
    assert client.post("/inventory/movements/spoilage", headers=H(manager_token),
                       json=body).status_code == 201
    assert client.post("/inventory/movements/spoilage", headers=H(manager_token),
                       json=body).status_code == 201
    assert get_current_stock(item_id) == Decimal("15")


def test_staff_cannot_read_the_movement_ledger(client, waiter_token, item_id):
    assert client.get(f"/inventory/movements?item_id={item_id}",
                      headers=H(waiter_token)).status_code == 403
    assert client.get(f"/inventory/movements/summary?item_id={item_id}",
                      headers=H(waiter_token)).status_code == 403


def test_bad_reason_filter_on_ledger_gets_plain_english_400(client, manager_token, item_id):
    rv = client.get("/inventory/movements?reason=THEFT", headers=H(manager_token))
    assert rv.status_code == 400 and "reason must be one of" in rv.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════════
# 4. STOCK COUNTS + variance
# ══════════════════════════════════════════════════════════════════════════════

def test_count_reconciles_derived_stock(client, manager_token, item_id):
    rv = client.post("/inventory/counts", headers=H(manager_token),
                     json={"item_id": item_id, "counted_amount": "18"})
    assert rv.status_code == 201
    body = rv.get_json()
    assert Decimal(body["prior_stock"]) == Decimal("20")
    assert Decimal(body["adjustment"]) == Decimal("-2")
    assert get_current_stock(item_id) == Decimal("18")


def test_count_rejects_negative_and_staff_and_foreign_department(
        client, manager_token, waiter_token, item_id, app):
    r1 = client.post("/inventory/counts", headers=H(manager_token),
                     json={"item_id": item_id, "counted_amount": "-1"})
    assert r1.status_code == 400

    r2 = client.post("/inventory/counts", headers=H(waiter_token),
                     json={"item_id": item_id, "counted_amount": "1"})
    assert r2.status_code == 403

    kitchen_item = _mk_item("Kitchen Salt", dept="Kitchen")
    r3 = client.post("/inventory/counts", headers=H(manager_token),
                     json={"item_id": kitchen_item, "counted_amount": "1"})
    assert r3.status_code == 403        # manager1 sits in General
    assert "your own department" in r3.get_json()["error"]


def test_count_on_disabled_item_refused(client, manager_token, item_id):
    client.post(f"/inventory/items/{item_id}/disable", headers=H(manager_token))
    rv = client.post("/inventory/counts", headers=H(manager_token),
                     json={"item_id": item_id, "counted_amount": "5"})
    assert rv.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 5. INVENTORY CATALOGUE — duplicates, disable-not-delete, who may author
# ══════════════════════════════════════════════════════════════════════════════

def test_duplicate_item_name_in_same_department_refused_but_allowed_across(
        client, manager_token, general_dept_id, app):
    body = {"name": "Tomatoes", "unit": "kg", "department_id": general_dept_id}
    assert client.post("/inventory/items", headers=H(manager_token), json=body).status_code == 201
    dup = client.post("/inventory/items", headers=H(manager_token), json=body)
    assert dup.status_code == 409

    other = client.post("/inventory/items", headers=H(manager_token),
                        json={**body, "department_id": _dept_id("Kitchen")})
    assert other.status_code == 201


def test_head_chef_may_author_ingredients_but_waiter_may_not(
        client, chef_token, waiter_token, general_dept_id):
    body = {"name": "Basil", "unit": "bunch", "department_id": general_dept_id}
    assert client.post("/inventory/items", headers=H(chef_token), json=body).status_code == 201
    rv = client.post("/inventory/items", headers=H(waiter_token),
                     json={**body, "name": "Thyme"})
    assert rv.status_code == 403


def test_disabled_item_disappears_from_the_list_but_is_not_deleted(
        client, manager_token, item_id):
    client.post(f"/inventory/items/{item_id}/disable", headers=H(manager_token))
    names = [i["id"] for i in client.get("/inventory/items", headers=H(manager_token)).get_json()]
    assert item_id not in names
    with_disabled = client.get("/inventory/items?include_disabled=true",
                               headers=H(manager_token)).get_json()
    assert item_id in [i["id"] for i in with_disabled]
    assert db.session.get(InventoryItem, item_id) is not None   # row still there


def test_item_creation_rejects_bad_reorder_level_and_missing_department(
        client, manager_token, general_dept_id):
    r1 = client.post("/inventory/items", headers=H(manager_token),
                     json={"name": "X", "unit": "kg", "department_id": general_dept_id,
                           "reorder_level": "not-a-number"})
    r2 = client.post("/inventory/items", headers=H(manager_token),
                     json={"name": "Y", "unit": "kg", "department_id": "nope"})
    assert (r1.status_code, r2.status_code) == (400, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 6. MENU + RECIPES
# ══════════════════════════════════════════════════════════════════════════════

def _mk_menu(client, token, dept_id, **kw):
    body = {"name": kw.pop("name", "Dish"), "price": kw.pop("price", "500"),
            "department_id": dept_id, "prep_station": kw.pop("prep_station", "KITCHEN"), **kw}
    return client.post("/menu/items", headers=H(token), json=body)


def test_head_chef_cannot_author_alcohol_or_flip_a_dish_to_alcoholic(
        client, chef_token, manager_token, general_dept_id):
    """Regression pin on an ALREADY-FIXED rule."""
    rv = _mk_menu(client, chef_token, general_dept_id,
                  name="Gin Tonic", prep_station="BAR", is_alcoholic=True)
    assert rv.status_code == 403

    dish = _mk_menu(client, chef_token, general_dept_id, name="Ugali").get_json()["id"]
    flip = client.patch(f"/menu/items/{dish}", headers=H(chef_token),
                        json={"is_alcoholic": True})
    assert flip.status_code == 403
    assert db.session.get(MenuItem, dish).is_alcoholic is False


def test_head_chef_cannot_reclassify_a_service_into_the_kitchen(
        client, chef_token, service_item_id):
    rv = client.patch(f"/menu/items/{service_item_id}", headers=H(chef_token),
                      json={"prep_station": "KITCHEN"})
    assert rv.status_code == 403


def test_station_scoping_and_unknown_station_message(client, waiter_token):
    """Regression pin on an ALREADY-FIXED rule."""
    rows = client.get("/menu/items?station=KITCHEN,BAR", headers=H(waiter_token)).get_json()
    assert {r["prep_station"] for r in rows} <= {"KITCHEN", "BAR"}
    assert "Pool Access" not in [r["name"] for r in rows]

    bad = client.get("/menu/items?station=SPA", headers=H(waiter_token))
    assert bad.status_code == 400 and "is not a station" in bad.get_json()["error"]


def test_duplicate_menu_name_in_department_refused_and_negative_price_refused(
        client, manager_token, general_dept_id):
    assert _mk_menu(client, manager_token, general_dept_id, name="Chips").status_code == 201
    assert _mk_menu(client, manager_token, general_dept_id, name="Chips").status_code == 409
    assert _mk_menu(client, manager_token, general_dept_id,
                    name="Free Lunch", price="-1").status_code == 400


def test_recipe_good_path_deducts_stock_with_pack_conversion(
        client, chef_token, manager_token, kitchen_token, waiter_token,
        general_dept_id, app):
    """750ml bottle, 50ml per drink, 2 drinks → 0.1333 bottles off the shelf."""
    gin = _mk_item("Gin", unit="bottle", pack_size="750", pack_unit="ml")
    _stock(gin, 10)
    drink = _mk_menu(client, chef_token, general_dept_id,
                     name="Fresh Juice", prep_station="BAR").get_json()["id"]
    rv = client.post(f"/menu/items/{drink}/recipe", headers=H(chef_token),
                     json={"lines": [{"inventory_item_id": gin, "quantity": "50"}]})
    assert rv.status_code == 201
    assert db.session.get(MenuItem, drink).stock_tracking == StockTracking.RECIPE.value

    order = client.post("/orders", headers=H(waiter_token),
                        json={"items": [{"menu_item_id": drink, "quantity": 2}]})
    assert order.status_code == 201, order.get_json()
    oid = order.get_json()["id"]
    assert client.post(f"/orders/{oid}/send", headers=H(waiter_token)).status_code == 200

    oi = db.session.query(MenuItem).first() and None  # noqa: keep session hot
    from app.models.order_item import OrderItem
    oi_id = db.session.query(OrderItem).filter_by(menu_item_id=drink).first().id
    assert client.post(f"/order-items/{oi_id}/receive", headers=H(manager_token)).status_code == 200
    assert client.post(f"/order-items/{oi_id}/ready", headers=H(manager_token)).status_code == 200

    # Numeric(12, 4) on the column, so compare at the stored precision.
    expected = (Decimal("10") - (Decimal("50") / Decimal("750")) * 2).quantize(Decimal("0.0001"))
    assert get_current_stock(gin) == expected


def test_recipe_rejects_disabled_missing_zero_and_negative_lines(
        client, chef_token, manager_token, general_dept_id, app):
    dish = _mk_menu(client, chef_token, general_dept_id, name="Stew").get_json()["id"]
    dead = _mk_item("Dead Ingredient")
    client.post(f"/inventory/items/{dead}/disable", headers=H(manager_token))

    r_disabled = client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                             json={"lines": [{"inventory_item_id": dead, "quantity": "1"}]})
    r_missing = client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                            json={"lines": [{"inventory_item_id": "ghost", "quantity": "1"}]})
    live = _mk_item("Live Ingredient")
    r_zero = client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                         json={"lines": [{"inventory_item_id": live, "quantity": "0"}]})
    r_neg = client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                        json={"lines": [{"inventory_item_id": live, "quantity": "-3"}]})
    assert r_disabled.status_code == 404
    assert r_missing.status_code == 404
    assert r_zero.status_code == 400 and "positive" in r_zero.get_json()["error"]
    assert r_neg.status_code == 400
    assert client.get(f"/menu/items/{dish}/recipe", headers=H(chef_token)).get_json() == []


def test_clearing_a_recipe_hands_the_item_back_to_untracked(
        client, chef_token, general_dept_id, app):
    live = _mk_item("Flour")
    dish = _mk_menu(client, chef_token, general_dept_id, name="Chapati").get_json()["id"]
    client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                json={"lines": [{"inventory_item_id": live, "quantity": "1"}]})
    assert db.session.get(MenuItem, dish).stock_tracking == StockTracking.RECIPE.value
    client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token), json={"lines": []})
    assert db.session.get(MenuItem, dish).stock_tracking == StockTracking.UNTRACKED.value


def test_direct_tracking_requires_an_inventory_item(client, manager_token, food_item_id):
    rv = client.patch(f"/menu/items/{food_item_id}", headers=H(manager_token),
                      json={"stock_tracking": "DIRECT"})
    assert rv.status_code == 400 and "inventory_item_id" in rv.get_json()["error"]

    bad = client.patch(f"/menu/items/{food_item_id}", headers=H(manager_token),
                       json={"stock_tracking": "MAGIC"})
    assert bad.status_code == 400


def test_untracked_item_cannot_be_re_enabled(client, manager_token, food_item_id):
    """The stated rule: UNTRACKED is the one state an item may not go live in."""
    client.post(f"/menu/items/{food_item_id}/disable", headers=H(manager_token))
    rv = client.post(f"/menu/items/{food_item_id}/enable", headers=H(manager_token))
    assert rv.status_code == 400
    assert "no stock tracking set" in rv.get_json()["error"]


def test_disabled_menu_item_cannot_be_ordered(client, manager_token, waiter_token, food_item_id):
    client.post(f"/menu/items/{food_item_id}/disable", headers=H(manager_token))
    rv = client.post("/orders", headers=H(waiter_token),
                     json={"items": [{"menu_item_id": food_item_id, "quantity": 1}]})
    assert rv.status_code == 400 and "disabled" in rv.get_json()["error"]


def test_recipe_item_is_refused_at_order_time_when_ingredient_is_short(
        client, chef_token, waiter_token, general_dept_id, app):
    beef = _mk_item("Beef")
    _stock(beef, 1)
    dish = _mk_menu(client, chef_token, general_dept_id, name="Beef Stew").get_json()["id"]
    client.post(f"/menu/items/{dish}/recipe", headers=H(chef_token),
                json={"lines": [{"inventory_item_id": beef, "quantity": "1"}]})
    rv = client.post("/orders", headers=H(waiter_token),
                     json={"items": [{"menu_item_id": dish, "quantity": 5}]})
    assert rv.status_code == 409 and "sold out" in rv.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════════
# 7. SUPPLIERS
# ══════════════════════════════════════════════════════════════════════════════

def test_supplier_crud_disable_not_delete(client, manager_token, waiter_token):
    rv = client.post("/suppliers", headers=H(manager_token), json={"name": "Mama Mboga"})
    assert rv.status_code == 201
    sid = rv.get_json()["id"]

    assert client.post("/suppliers", headers=H(manager_token),
                       json={"name": "mama mboga"}).status_code == 409   # case-insensitive
    assert client.get("/suppliers", headers=H(waiter_token)).status_code == 403

    assert client.post(f"/suppliers/{sid}/disable", headers=H(manager_token)).status_code == 200
    assert [s["id"] for s in client.get("/suppliers", headers=H(manager_token)).get_json()] == []
    assert sid in [s["id"] for s in client.get("/suppliers?include_disabled=true",
                                               headers=H(manager_token)).get_json()]


def test_disabled_supplier_cannot_be_edited_and_has_no_enable_route(client, manager_token):
    """Disable is one-way here: there is no POST /suppliers/<id>/enable, and PATCH
    refuses a disabled row. A mis-click needs DB surgery to undo."""
    sid = client.post("/suppliers", headers=H(manager_token),
                      json={"name": "Coast Fish"}).get_json()["id"]
    client.post(f"/suppliers/{sid}/disable", headers=H(manager_token))
    assert client.patch(f"/suppliers/{sid}", headers=H(manager_token),
                        json={"phone": "0700"}).status_code == 404
    assert client.post(f"/suppliers/{sid}/enable", headers=H(manager_token)).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 8. EQUIPMENT + SAFETY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def jetski_id(client, manager_token):
    return client.post("/equipment", headers=H(manager_token),
                       json={"name": "Jetski 1", "equipment_type": "jetski"}).get_json()["id"]


def test_safety_check_requires_every_template_item(client, waiter_token, jetski_id):
    template = client.get("/equipment/checklist-templates/jetski",
                          headers=H(waiter_token)).get_json()["items"]
    partial = {k: {"checked": True} for k in template[:3]}
    rv = client.post(f"/equipment/{jetski_id}/safety-check", headers=H(waiter_token),
                     json={"check_items": partial})
    assert rv.status_code == 400
    assert set(rv.get_json()["unchecked_items"]) == set(template[3:])

    lying = {k: {"checked": True} for k in template}
    lying[template[0]] = {"checked": False}
    rv = client.post(f"/equipment/{jetski_id}/safety-check", headers=H(waiter_token),
                     json={"check_items": lying})
    assert rv.status_code == 400 and template[0] in rv.get_json()["unchecked_items"]

    full = {k: {"checked": True} for k in template}
    assert client.post(f"/equipment/{jetski_id}/safety-check", headers=H(waiter_token),
                       json={"check_items": full}).status_code == 201


def test_only_manager_creates_equipment_and_logs_maintenance(client, waiter_token, jetski_id):
    assert client.post("/equipment", headers=H(waiter_token),
                       json={"name": "X", "equipment_type": "bicycle"}).status_code == 403
    assert client.post(f"/equipment/{jetski_id}/maintenance", headers=H(waiter_token),
                       json={"notes": "oil"}).status_code == 403


def test_maintenance_updates_service_date_and_rejects_bad_input(
        client, manager_token, jetski_id):
    rv = client.post(f"/equipment/{jetski_id}/maintenance", headers=H(manager_token),
                     json={"notes": "serviced", "cost": "1500"})
    assert rv.status_code == 201
    row = client.get("/equipment", headers=H(manager_token)).get_json()[0]
    assert row["last_service_utc"] is not None and row["is_due_service"] is False

    bad_cost = client.post(f"/equipment/{jetski_id}/maintenance", headers=H(manager_token),
                           json={"cost": "free"})
    bad_date = client.post(f"/equipment/{jetski_id}/maintenance", headers=H(manager_token),
                           json={"performed_at_utc": "yesterday"})
    assert (bad_cost.status_code, bad_date.status_code) == (400, 400)


# ══════════════════════════════════════════════════════════════════════════════
# 9. HOUSEKEEPING lifecycle
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def villa_and_cleaning(app, client, manager_token):
    """A villa resource + a DIRTY cleaning record, plus a housekeeper account."""
    from app.models.bookable_resource import BookableResource
    from app.models.cleaning_status import CleaningStatus, CleaningStatusEnum
    from app.models.role import Role

    res = BookableResource(name="Villa 1", resource_type="VILLA", base_price="1000")
    hk_dept = Department(name="Housekeeping")
    db.session.add_all([res, hk_dept])
    db.session.flush()
    staff_role = db.session.query(Role).filter_by(name="staff").first()
    hk = User(username="hk1", role_id=staff_role.id, department_id=hk_dept.id)
    hk.set_password("HkPass1!")
    cs = CleaningStatus(resource_id=res.id, status=CleaningStatusEnum.DIRTY.value)
    db.session.add_all([hk, cs])
    db.session.commit()
    token = client.post("/auth/login",
                        json={"username": "hk1", "password": "HkPass1!"}).get_json()["access_token"]
    return {"cleaning_id": cs.id, "hk_token": token, "hk_user_id": hk.id}


def test_housekeeping_full_lifecycle(client, manager_token, villa_and_cleaning):
    cid = villa_and_cleaning["cleaning_id"]
    hk = villa_and_cleaning["hk_token"]

    assert client.post("/housekeeping/assign", headers=H(manager_token),
                       json={"cleaning_id": cid,
                             "housekeeper_id": villa_and_cleaning["hk_user_id"]}).status_code == 200
    assert client.post(f"/housekeeping/{cid}/start", headers=H(hk)).status_code == 200
    assert client.post(f"/housekeeping/{cid}/complete", headers=H(hk)).status_code == 200
    rv = client.post(f"/housekeeping/{cid}/inspect", headers=H(manager_token))
    assert rv.status_code == 200 and rv.get_json()["status"] == "INSPECTED"


def test_housekeeping_states_cannot_be_skipped(client, manager_token, villa_and_cleaning):
    cid = villa_and_cleaning["cleaning_id"]
    rv = client.post(f"/housekeeping/{cid}/complete", headers=H(manager_token))
    assert rv.status_code == 400 and "Cannot move from DIRTY to CLEAN" in rv.get_json()["error"]
    rv = client.post(f"/housekeeping/{cid}/inspect", headers=H(manager_token))
    assert rv.status_code == 400


def test_housekeeping_role_boundaries(client, waiter_token, villa_and_cleaning):
    cid = villa_and_cleaning["cleaning_id"]
    assert client.get("/housekeeping/status", headers=H(waiter_token)).status_code == 403
    assert client.post("/housekeeping/assign", headers=H(waiter_token),
                       json={"cleaning_id": cid, "housekeeper_id": "x"}).status_code == 403
    assert client.post(f"/housekeeping/{cid}/start", headers=H(waiter_token)).status_code == 403
    assert client.post(f"/housekeeping/{cid}/inspect", headers=H(waiter_token)).status_code == 403
    assert client.post(f"/housekeeping/{cid}/flag", headers=H(waiter_token),
                       json={"reason": "broken tap"}).status_code == 403


def test_flag_requires_a_reason(client, manager_token, villa_and_cleaning):
    cid = villa_and_cleaning["cleaning_id"]
    assert client.post(f"/housekeeping/{cid}/flag", headers=H(manager_token),
                       json={}).status_code == 400
    rv = client.post(f"/housekeeping/{cid}/flag", headers=H(manager_token),
                     json={"reason": "shower leaking"})
    assert rv.status_code == 200 and rv.get_json()["is_flagged"] is True


def test_HOLE_manager_may_assign_anyone_as_a_housekeeper(client, manager_token,
                                                          villa_and_cleaning, app):
    """SHOULD: a cleaning task can only be assigned to housekeeping staff.
    IS: /housekeeping/assign accepts ANY active user id — the head chef can be
    put on villa cleaning, and then only they or a manager can complete it."""
    chef_id = _user_id("chef1")
    rv = client.post("/housekeeping/assign", headers=H(manager_token),
                     json={"cleaning_id": villa_and_cleaning["cleaning_id"],
                           "housekeeper_id": chef_id})
    assert rv.status_code == 200
    assert rv.get_json()["assigned_to"] == "chef1"


# ══════════════════════════════════════════════════════════════════════════════
# 10. EVENTS + inventory allocation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def event_id(client, manager_token):
    from datetime import datetime, timezone, timedelta
    tid = client.post("/event-types", headers=H(manager_token),
                      json={"name": "Wedding"}).get_json()["id"]
    start = datetime.now(timezone.utc) + timedelta(days=7)
    return client.post("/events", headers=H(manager_token), json={
        "title": "Otieno Wedding", "event_type_id": tid,
        "starts_at_utc": start.isoformat(),
        "ends_at_utc": (start + timedelta(hours=6)).isoformat(),
        "expected_guests": 200,
    }).get_json()["id"]


def test_event_allocation_issue_and_return_moves_stock(client, manager_token,
                                                       event_id, item_id):
    alloc = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                        json={"inventory_item_id": item_id, "allocated_quantity": "10"})
    assert alloc.status_code == 201
    aid = alloc.get_json()["id"]

    assert client.post(f"/events/{event_id}/inventory/{aid}/issue",
                       headers=H(manager_token)).status_code == 200
    assert get_current_stock(item_id) == Decimal("10")

    rv = client.post(f"/events/{event_id}/inventory/{aid}/return", headers=H(manager_token),
                     json={"return_quantity": "4"})
    assert rv.status_code == 200
    assert get_current_stock(item_id) == Decimal("14")


def test_event_issue_beyond_stock_is_refused(client, manager_token, event_id, item_id):
    aid = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                      json={"inventory_item_id": item_id,
                            "allocated_quantity": "999"}).get_json()["id"]
    rv = client.post(f"/events/{event_id}/inventory/{aid}/issue", headers=H(manager_token))
    assert rv.status_code == 400 and "Insufficient stock" in rv.get_json()["error"]
    assert get_current_stock(item_id) == Decimal("20")


def test_event_allocation_states_cannot_be_skipped(client, manager_token, event_id, item_id):
    aid = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                      json={"inventory_item_id": item_id,
                            "allocated_quantity": "5"}).get_json()["id"]
    early = client.post(f"/events/{event_id}/inventory/{aid}/return", headers=H(manager_token))
    assert early.status_code == 400 and "Cannot move allocation from PLANNED" in early.get_json()["error"]

    client.post(f"/events/{event_id}/inventory/{aid}/issue", headers=H(manager_token))
    client.post(f"/events/{event_id}/inventory/{aid}/return", headers=H(manager_token),
                json={"return_quantity": "5"})
    twice = client.post(f"/events/{event_id}/inventory/{aid}/return", headers=H(manager_token),
                        json={"return_quantity": "5"})
    assert twice.status_code == 400


def test_event_allocation_rejects_disabled_item_and_bad_quantity(
        client, manager_token, event_id, item_id):
    r_bad = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                        json={"inventory_item_id": item_id, "allocated_quantity": "0"})
    assert r_bad.status_code == 400
    client.post(f"/inventory/items/{item_id}/disable", headers=H(manager_token))
    r_dead = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                         json={"inventory_item_id": item_id, "allocated_quantity": "1"})
    assert r_dead.status_code == 404


def test_event_lifecycle_and_illegal_transitions(client, manager_token, waiter_token, event_id):
    assert client.post(f"/events/{event_id}/complete",
                       headers=H(manager_token)).status_code == 400   # PLANNED -> COMPLETED
    assert client.post(f"/events/{event_id}/confirm", headers=H(manager_token)).status_code == 200
    assert client.post(f"/events/{event_id}/start", headers=H(manager_token)).status_code == 200
    assert client.post(f"/events/{event_id}/complete", headers=H(manager_token)).status_code == 200
    dead = client.post(f"/events/{event_id}/cancel", headers=H(manager_token))
    assert dead.status_code == 400 and "Cannot move event from COMPLETED" in dead.get_json()["error"]

    assert client.post(f"/events/{event_id}/cancel", headers=H(waiter_token)).status_code == 403


def test_staff_cannot_allocate_or_read_event_inventory(client, waiter_token, event_id, item_id):
    assert client.post(f"/events/{event_id}/inventory/allocate", headers=H(waiter_token),
                       json={"inventory_item_id": item_id,
                             "allocated_quantity": "1"}).status_code == 403
    assert client.get(f"/events/{event_id}/inventory", headers=H(waiter_token)).status_code == 403


def test_assignment_of_inactive_employee_refused(client, manager_token, event_id, app):
    rv = client.post(f"/events/{event_id}/assignments", headers=H(manager_token),
                     json={"employee_id": "ghost", "role_on_event": "server"})
    assert rv.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 11. INCIDENTS + LOST & FOUND
# ══════════════════════════════════════════════════════════════════════════════

def test_incident_good_path_and_role_split(client, waiter_token, manager_token):
    rv = client.post("/incidents", headers=H(waiter_token), json={
        "description": "Guest slipped by the pool", "location": "Pool deck",
        "severity": "MEDIUM", "idempotency_key": "inc-1",
    })
    assert rv.status_code == 201, rv.get_json()
    iid = rv.get_json()["id"]

    dup = client.post("/incidents", headers=H(waiter_token), json={
        "description": "x", "location": "y", "severity": "LOW",
        "idempotency_key": "inc-1",
    })
    assert dup.status_code == 200 and dup.get_json()["duplicate"] is True

    assert client.get("/incidents", headers=H(waiter_token)).status_code == 403
    assert client.patch(f"/incidents/{iid}/action", headers=H(waiter_token)).status_code == 403
    done = client.patch(f"/incidents/{iid}/action", headers=H(manager_token))
    assert done.status_code == 200 and done.get_json()["actioned"] is True


def test_incident_rejects_missing_fields_and_bad_severity(client, waiter_token):
    base = {"description": "d", "location": "l", "severity": "LOW", "idempotency_key": "k"}
    for missing in ("description", "location", "idempotency_key"):
        body = {**base, missing: ""}
        assert client.post("/incidents", headers=H(waiter_token), json=body).status_code == 400
    assert client.post("/incidents", headers=H(waiter_token),
                       json={**base, "severity": "APOCALYPTIC"}).status_code == 400


def test_lost_found_staff_logs_manager_claims(client, waiter_token, manager_token):
    rv = client.post("/lost-found", headers=H(waiter_token),
                     json={"description": "Blue wallet", "found_location": "Villa 3"})
    assert rv.status_code == 201
    lid = rv.get_json()["id"]

    assert client.get("/lost-found", headers=H(waiter_token)).status_code == 403
    assert client.patch(f"/lost-found/{lid}", headers=H(waiter_token),
                        json={"status": "CLAIMED"}).status_code == 403

    no_name = client.patch(f"/lost-found/{lid}", headers=H(manager_token),
                           json={"status": "CLAIMED"})
    assert no_name.status_code == 400 and "claimed_by_name" in no_name.get_json()["error"]

    ok = client.patch(f"/lost-found/{lid}", headers=H(manager_token),
                      json={"status": "CLAIMED", "claimed_by_name": "J. Mwangi"})
    assert ok.status_code == 200 and ok.get_json()["claimed_at"] is not None

    assert client.patch(f"/lost-found/{lid}", headers=H(manager_token),
                        json={"status": "VAPORISED"}).status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 12. BOOKABLE RESOURCES
# ══════════════════════════════════════════════════════════════════════════════

def test_resource_pricing_is_owner_only_and_disable_is_reversible(
        client, manager_token, owner_token, waiter_token):
    rv = client.post("/bookable-resources", headers=H(manager_token),
                     json={"name": "Villa 9", "resource_type": "VILLA", "base_price": "8000"})
    assert rv.status_code == 201
    rid = rv.get_json()["id"]

    assert client.patch(f"/bookable-resources/{rid}", headers=H(manager_token),
                        json={"base_price": "1"}).status_code == 403
    assert client.patch(f"/bookable-resources/{rid}", headers=H(owner_token),
                        json={"base_price": "9000"}).status_code == 200

    assert client.post("/bookable-resources", headers=H(waiter_token),
                       json={"name": "X", "resource_type": "VILLA"}).status_code == 403
    assert client.post(f"/bookable-resources/{rid}/disable",
                       headers=H(manager_token)).status_code == 200
    assert client.post(f"/bookable-resources/{rid}/enable",
                       headers=H(manager_token)).status_code == 200


def test_resource_rejects_unknown_type(client, manager_token):
    rv = client.post("/bookable-resources", headers=H(manager_token),
                     json={"name": "Hot air balloon", "resource_type": "BALLOON"})
    assert rv.status_code == 400 and "resource_type must be one of" in rv.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════════
# 13. STAFF ACCOUNTS — hierarchy
# ══════════════════════════════════════════════════════════════════════════════

def test_account_hierarchy_cannot_be_climbed(client, manager_token, app):
    from app.models.role import Role
    owner_role = db.session.query(Role).filter_by(name="owner").first().id
    mgr_role   = db.session.query(Role).filter_by(name="manager").first().id
    staff_role = db.session.query(Role).filter_by(name="staff").first().id

    assert client.post("/auth/users", headers=H(manager_token),
                       json={"username": "sneaky", "role_id": owner_role}).status_code == 403
    assert client.post("/auth/users", headers=H(manager_token),
                       json={"username": "peer", "role_id": mgr_role}).status_code == 403
    rv = client.post("/auth/users", headers=H(manager_token),
                     json={"username": "newstaff", "role_id": staff_role})
    assert rv.status_code == 201

    new_id = rv.get_json()["id"]
    assert client.patch(f"/auth/users/{new_id}", headers=H(manager_token),
                        json={"role_id": owner_role}).status_code == 403
    assert client.patch(f"/auth/users/{_user_id('owner1')}", headers=H(manager_token),
                        json={"username": "pwned"}).status_code == 403


def test_meta_only_offers_roles_below_the_actor(client, manager_token):
    roles = client.get("/auth/users/meta", headers=H(manager_token)).get_json()["roles"]
    assert all(r["level"] < 5 for r in roles)
    assert "owner" not in [r["name"] for r in roles]


# ══════════════════════════════════════════════════════════════════════════════
# 14. HOLES — these pin behaviour that looks wrong. Each says what SHOULD happen.
# ══════════════════════════════════════════════════════════════════════════════

def test_HOLE_a_brand_new_untracked_menu_item_is_live_and_sellable(
        client, manager_token, waiter_token, general_dept_id, app):
    """SHOULD: an UNTRACKED item may not go live (pos/menu.py:291-309 says so, and
    /enable enforces it).
    IS: POST /menu/items creates the row with is_active=True (model default) and
    stock_tracking=UNTRACKED (model default) — the untracked check is on /enable
    ONLY, and a freshly created item never passes through /enable. So the block
    is trivially bypassed: create it and sell it. Order creation only checks
    is_active (pos/orders.py:115)."""
    mid = _mk_menu(client, manager_token, general_dept_id, name="Mystery Platter").get_json()["id"]
    row = db.session.get(MenuItem, mid)
    assert row.is_active is True
    assert row.stock_tracking == StockTracking.UNTRACKED.value

    rv = client.post("/orders", headers=H(waiter_token),
                     json={"items": [{"menu_item_id": mid, "quantity": 1}]})
    assert rv.status_code == 201        # sold, and nothing will ever move stock


def test_HOLE_direct_sale_drives_stock_negative(
        client, manager_token, waiter_token, general_dept_id, app):
    """SHOULD: a sale cannot deduct stock that is not there — spoilage, staff-meal,
    sent-back and event-issue all route through check_sufficient_stock
    (services/stock.py:27).
    IS: services/consumption.py:_consume_direct (line 30) writes the negative
    movement with NO floor check, and the order-time 'sold out' pre-check in
    pos/orders.py:121-131 only walks RECIPE lines — DIRECT items are not
    pre-checked at all. Result: stock goes negative out of a POS sale."""
    beer = _mk_item("Tusker Crate", unit="bottle")      # zero stock on the shelf
    mid = _mk_menu(client, manager_token, general_dept_id,
                   name="Tusker Bottle", prep_station="BAR").get_json()["id"]
    link = client.patch(f"/menu/items/{mid}", headers=H(manager_token),
                        json={"inventory_item_id": beer})
    assert link.status_code == 200
    assert db.session.get(MenuItem, mid).stock_tracking == StockTracking.DIRECT.value

    oid = client.post("/orders", headers=H(waiter_token),
                      json={"items": [{"menu_item_id": mid, "quantity": 5}]}).get_json()["id"]
    client.post(f"/orders/{oid}/send", headers=H(waiter_token))
    from app.models.order_item import OrderItem
    oi_id = db.session.query(OrderItem).filter_by(menu_item_id=mid).first().id
    client.post(f"/order-items/{oi_id}/receive", headers=H(manager_token))
    assert client.post(f"/order-items/{oi_id}/ready", headers=H(manager_token)).status_code == 200

    assert get_current_stock(beer) == Decimal("-5")


def test_HOLE_event_return_can_exceed_what_was_issued(client, manager_token,
                                                       event_id, item_id):
    """SHOULD: you cannot return more than you took — return_quantity must be
    capped at the issued/allocated amount.
    IS: events/core.py:520-527 validates only 'positive number', and
    services/events.py:return_allocation writes change_amount=+return_qty
    unconditionally. Issue 10, return 1000 → 990 units of stock invented, under
    reason EVENT_ALLOCATION, which is deliberately EXCLUDED from the judge's
    consumption ratios (models/stock_movement.py:29-31). Silent inflation."""
    aid = client.post(f"/events/{event_id}/inventory/allocate", headers=H(manager_token),
                      json={"inventory_item_id": item_id,
                            "allocated_quantity": "10"}).get_json()["id"]
    client.post(f"/events/{event_id}/inventory/{aid}/issue", headers=H(manager_token))
    assert get_current_stock(item_id) == Decimal("10")

    rv = client.post(f"/events/{event_id}/inventory/{aid}/return", headers=H(manager_token),
                     json={"return_quantity": "1000"})
    assert rv.status_code == 200
    assert get_current_stock(item_id) == Decimal("1010")


def test_HOLE_head_chef_can_disable_alcohol_and_services(
        client, chef_token, manager_token, general_dept_id, service_item_id):
    """SHOULD: the chef owns the food and the juices; alcohol and services belong
    to the manager (pos/menu.py:51-78) — and PATCH/POST correctly enforce that.
    IS: disable_menu_item and enable_menu_item call _require_manager(actor) with
    NO station and NO is_alcoholic (pos/menu.py:278, 316), so the head chef —
    who cannot create, price or edit a beer — can pull every beer and every spa
    service off the menu."""
    gin = _mk_menu(client, manager_token, general_dept_id, name="Gin Tonic",
                   prep_station="BAR", is_alcoholic=True).get_json()["id"]
    assert client.patch(f"/menu/items/{gin}", headers=H(chef_token),
                        json={"price": "1"}).status_code == 403      # cannot edit
    assert client.post(f"/menu/items/{gin}/disable",
                       headers=H(chef_token)).status_code == 200     # but CAN pull it
    assert client.post(f"/menu/items/{service_item_id}/disable",
                       headers=H(chef_token)).status_code == 200
    assert db.session.get(MenuItem, gin).is_active is False


def test_HOLE_menu_price_edit_with_garbage_500s(client, manager_token, food_item_id):
    """SHOULD: 'price must be a number.' with a 400 — exactly what POST /menu/items
    returns (pos/menu.py:158-161), and what invariant 5 requires of every error.
    IS: PATCH /menu/items/<id> calls Decimal(str(data['price'])) bare
    (pos/menu.py:215) with no InvalidOperation guard → unhandled exception."""
    with pytest.raises(Exception):
        client.patch(f"/menu/items/{food_item_id}", headers=H(manager_token),
                     json={"price": "one thousand"})


def test_HOLE_incident_list_limit_is_not_validated(client, manager_token):
    """SHOULD: 'limit must be a whole number.' 400 — the movement ledger does
    exactly that (inventory/movements.py:249-253).
    IS: incidents/core.py:92 does int(request.args.get('limit', 50)) bare."""
    with pytest.raises(Exception):
        client.get("/incidents?limit=lots", headers=H(manager_token))


def test_HOLE_negative_resource_price_500s_on_the_db_constraint(client, manager_token):
    """SHOULD: 400 'base_price cannot be negative' — the app validates the TYPE
    (bookings/resources.py:37-40) but never the SIGN.
    IS: the DB CHECK ck_resource_price_nonneg catches it and the IntegrityError
    escapes as a 500 with no plain-English message. Defense in depth worked;
    the error contract did not."""
    with pytest.raises(Exception):
        client.post("/bookable-resources", headers=H(manager_token),
                    json={"name": "Upside-down Villa", "resource_type": "VILLA",
                          "base_price": "-5000"})


def test_HOLE_safety_check_with_a_non_object_item_500s(client, waiter_token, jetski_id):
    """SHOULD: 400 — the 'unknown equipment type' branch already handles a
    non-dict value correctly (equipment/core.py:209-210).
    IS: the TEMPLATE branch calls check_items[k].get('checked') (line 196)
    assuming every value is a dict. A tablet sending {"item": true} 500s."""
    template = client.get("/equipment/checklist-templates/jetski",
                          headers=H(waiter_token)).get_json()["items"]
    payload = {k: True for k in template}      # booleans, not {"checked": true}
    with pytest.raises(Exception):
        client.post(f"/equipment/{jetski_id}/safety-check", headers=H(waiter_token),
                    json={"check_items": payload})


def test_HOLE_equipment_disable_is_one_way(client, manager_token, jetski_id):
    """SHOULD: 'disable, never delete' (invariant 6) pairs with an enable route —
    inventory items, menu items, bookable resources, departments and roles all
    have one.
    IS: app/equipment/core.py has NO enable endpoint, and PATCH refuses a
    disabled row (line 93). A mis-clicked disable removes the jetski from the
    system permanently, including its safety-check path."""
    assert client.post(f"/equipment/{jetski_id}/disable",
                       headers=H(manager_token)).status_code == 200
    assert client.post(f"/equipment/{jetski_id}/enable",
                       headers=H(manager_token)).status_code == 404      # no such route
    assert client.patch(f"/equipment/{jetski_id}", headers=H(manager_token),
                        json={"is_active": True}).status_code == 404
    assert client.post(f"/equipment/{jetski_id}/safety-check", headers=H(manager_token),
                       json={"check_items": {"a": {"checked": True}}}).status_code == 404


def test_HOLE_event_expected_guests_is_not_validated(client, manager_token):
    """SHOULD: 400 'expected_guests must be a whole number / must be positive'.
    IS: events/core.py:166 does int(data.get('expected_guests', 1)) bare, and
    line 194 the same on edit — 'many' raises ValueError. A negative IS caught,
    but only by the DB CHECK ck_event_guests_pos, which escapes as an
    IntegrityError, not a plain-English 400. Both are unhandled exceptions."""
    from datetime import datetime, timezone, timedelta
    tid = client.post("/event-types", headers=H(manager_token),
                      json={"name": "Conference"}).get_json()["id"]
    start = datetime.now(timezone.utc) + timedelta(days=3)
    body = {"title": "T", "event_type_id": tid,
            "starts_at_utc": start.isoformat(),
            "ends_at_utc": (start + timedelta(hours=2)).isoformat()}

    with pytest.raises(ValueError):
        client.post("/events", headers=H(manager_token),
                    json={**body, "expected_guests": "many"})

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        client.post("/events", headers=H(manager_token),
                    json={**body, "expected_guests": -50, "title": "T2"})
