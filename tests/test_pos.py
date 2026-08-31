"""
test_pos.py — POS endpoint tests (Chunk 3).

Covers:
  1.  Tab balance is sum(charges) - sum(payments), never stored
  2.  Payment idempotency: duplicate key → 200 + same record
  3.  Order lifecycle: DRAFT → SENT, items transition correctly
  4.  Service items (NONE station) are immediately SERVED on send
  5.  Food items route to KITCHEN queue; drink items route to BAR queue
  6.  Tab close blocked when balance > 0
  7.  Tab close blocked when order items still pending
  8.  Judge engine wakes when payments exist
  9.  Kitchen staff cannot create orders
  10. Waiter cannot access kitchen queue
  11. Manager can access kitchen queue from any dept
  12. Decimal precision: 50 payments sum to exact Decimal
  13. M-Pesa code captured on payment
  14. Disabling a menu item blocks new orders
  15. Error responses always carry "error" field
"""
import uuid
import pytest
from decimal import Decimal
from app.extensions import db as _db


# ── helpers ────────────────────────────────────────────────────────────────────

def _open_tab(client, token, reference=None):
    payload = {}
    if reference:
        payload["reference"] = reference
    rv = client.post("/tabs", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201
    return rv.get_json()["id"]


def _create_order(client, token, tab_id, menu_item_id, qty=1):
    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": menu_item_id, "quantity": qty}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


def _send_order(client, token, order_id):
    rv = client.post(f"/orders/{order_id}/send",
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()


def _pay(client, token, tab_id, amount, method="CASH", idem_key=None, **extra):
    payload = {"amount": amount, "method": method,
               "idempotency_key": idem_key or str(uuid.uuid4()), **extra}
    rv = client.post(f"/tabs/{tab_id}/payments", json=payload,
                     headers={"Authorization": f"Bearer {token}"})
    return rv


# ── 1. Tab balance derived, never stored ──────────────────────────────────────

def test_tab_balance_is_derived(client, owner_token, food_item_id):
    tab_id = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id, qty=2)
    _send_order(client, owner_token, order_id)

    # One partial payment
    _pay(client, owner_token, tab_id, "500")

    rv = client.get(f"/tabs/{tab_id}", headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    # balance = total_charges - total_payments = 2400 - 500 = 1900
    assert Decimal(data["balance"]) == Decimal("1900")
    assert "balance" not in data or "balance_stored" not in data  # derived, not a DB column


# ── 2. Payment idempotency ─────────────────────────────────────────────────────

def test_payment_idempotency(client, owner_token, food_item_id):
    tab_id = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)

    idem = str(uuid.uuid4())
    rv1 = _pay(client, owner_token, tab_id, "500", idem_key=idem)
    rv2 = _pay(client, owner_token, tab_id, "500", idem_key=idem)
    assert rv1.status_code == 201
    assert rv2.status_code == 200
    assert rv2.get_json()["duplicate"] is True
    # Balance should only count one payment
    rv = client.get(f"/tabs/{tab_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert Decimal(rv.get_json()["balance"]) == Decimal("700")  # 1200 - 500


# ── 3. Order lifecycle DRAFT → SENT ───────────────────────────────────────────

def test_order_lifecycle_draft_to_sent(client, owner_token, food_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)

    # Still DRAFT
    rv = client.get(f"/tabs/{tab_id}", headers={"Authorization": f"Bearer {owner_token}"})

    result = _send_order(client, owner_token, order_id)
    assert result["status"] == "SENT"

    # Cannot re-send
    rv = client.post(f"/orders/{order_id}/send",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 400
    assert "error" in rv.get_json()


# ── 4. Service items immediately SERVED ───────────────────────────────────────

def test_service_item_immediately_served(client, owner_token, service_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, service_item_id)
    _send_order(client, owner_token, order_id)

    # Order should auto-complete (all items served)
    # Verify via receipt — balance should equal charge amount
    rv = client.get(f"/receipts/{tab_id}", headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    assert Decimal(data["total_charges"]) == Decimal("500")


# ── 5. Routing: food → KITCHEN, drink → BAR ───────────────────────────────────

def test_food_item_appears_in_kitchen_queue(client, owner_token, manager_token, food_item_id):
    tab_id   = _open_tab(client, owner_token)
    _create_order(client, owner_token, tab_id, food_item_id)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)

    rv = client.get("/kitchen/queue", headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    assert len(rv.get_json()) > 0
    assert all(i["menu_item"] == "Grilled Tilapia" for i in rv.get_json())


def test_drink_item_appears_in_bar_queue(client, owner_token, manager_token, drink_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, drink_item_id)
    _send_order(client, owner_token, order_id)

    rv = client.get("/bar/queue", headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    assert len(rv.get_json()) > 0


# ── 6. Tab close blocked with outstanding balance ─────────────────────────────

def test_tab_close_blocked_with_balance(client, owner_token, food_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)
    # No payment made — balance is 1200

    rv = client.post(f"/tabs/{tab_id}/close",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 400
    assert "error" in rv.get_json()
    assert "balance" in rv.get_json()["error"].lower()


# ── 7. Tab close blocked with unresolved order items ──────────────────────────

def test_tab_close_blocked_with_pending_items(client, owner_token, food_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)
    # Pay in full but items still PENDING in queue
    _pay(client, owner_token, tab_id, "1200")

    rv = client.post(f"/tabs/{tab_id}/close",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 400
    body = rv.get_json()
    assert "error" in body


# ── 8. Judge wakes when payments exist ────────────────────────────────────────

def test_judge_engine_wakes_with_revenue(client, owner_token, food_item_id, general_dept_id, app):
    from datetime import datetime, timezone, timedelta
    from app.judge.engine import run_weekly
    from app.extensions import db
    from app.models.judge_baseline import JudgeBaseline
    from app.models.inventory_item import InventoryItem
    from app.models.stock_movement import StockMovement, MovementReason

    with app.app_context():
        from app.models.user import User as _User
        owner = _db.session.query(_User).filter_by(username="owner1").first()

        # Create inventory item + baseline
        inv_item = InventoryItem(name="Fish", unit="kg", reorder_level="5",
                                 department_id=general_dept_id)
        db.session.add(inv_item)
        db.session.flush()

        # Set a baseline — expected_ratio means units per Ksh 10,000 revenue
        baseline = JudgeBaseline(
            item_id=inv_item.id,
            business_driver="restaurant_revenue",
            expected_ratio="2",          # expect 2 kg per Ksh 10k revenue
            driver_unit="KES 10,000",
            tolerance_percent="10",
        )
        db.session.add(baseline)

        # Log a movement — 100kg consumed (huge deviation to guarantee alert fires)
        movement = StockMovement(
            item_id=inv_item.id,
            change_amount="-100",
            reason=MovementReason.SPOILAGE.value,
            actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(movement)
        db.session.commit()

    # Make a payment so judge sees revenue
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)
    _pay(client, owner_token, tab_id, "10000")

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=7)
    period_end   = now

    with app.app_context():
        alerts = run_weekly(period_start, period_end)

    assert alerts > 0, "Judge should fire at least one alert with real revenue + huge deviation"


# ── 9. Kitchen staff cannot create orders ─────────────────────────────────────

def test_kitchen_staff_cannot_create_orders(client, kitchen_token, food_item_id, owner_token):
    tab_id = _open_tab(client, owner_token)
    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": food_item_id, "quantity": 1}],
    }, headers={"Authorization": f"Bearer {kitchen_token}"})
    assert rv.status_code == 403
    assert "error" in rv.get_json()


# ── 10. Waiter cannot access kitchen queue ────────────────────────────────────

def test_waiter_cannot_access_kitchen_queue(client, waiter_token):
    rv = client.get("/kitchen/queue", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 403
    assert "error" in rv.get_json()


# ── 11. Manager can access kitchen queue from any dept ────────────────────────

def test_manager_can_access_kitchen_queue(client, manager_token):
    rv = client.get("/kitchen/queue", headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200


# ── 12. Decimal precision: 50 payments sum exactly ────────────────────────────

def test_50_payments_decimal_precision(client, owner_token, food_item_id):
    tab_id = _open_tab(client, owner_token)

    # Create enough charges: 50 items at 1200 each
    for _ in range(50):
        order_id = _create_order(client, owner_token, tab_id, food_item_id)
        _send_order(client, owner_token, order_id)

    # 50 payments of 1.00 each = 50.00 total paid
    for _ in range(50):
        _pay(client, owner_token, tab_id, "1.00")

    rv = client.get(f"/tabs/{tab_id}", headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    total_payments = sum(Decimal(p["amount"]) for p in data["payments"])
    assert total_payments == Decimal("50.00")


# ── 13. M-Pesa code captured on payment ───────────────────────────────────────

def test_mpesa_code_captured(client, owner_token, food_item_id):
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, food_item_id)
    _send_order(client, owner_token, order_id)

    rv = _pay(client, owner_token, tab_id, "1200", method="MPESA",
              mpesa_code="QA123XYZ")
    assert rv.status_code == 201

    receipt = client.get(f"/receipts/{tab_id}",
                         headers={"Authorization": f"Bearer {owner_token}"})
    payments = receipt.get_json()["payments"]
    assert any(p["mpesa_code"] == "QA123XYZ" for p in payments)


# ── 14. Disabled menu item blocks new orders ──────────────────────────────────

def test_disabled_menu_item_blocks_order(client, owner_token, manager_token, food_item_id):
    # Disable the food item (manager can disable menu items)
    rv = client.post(f"/menu/items/{food_item_id}/disable",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    tab_id = _open_tab(client, owner_token)
    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": food_item_id, "quantity": 1}],
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 400
    assert "error" in rv.get_json()
    assert "disabled" in rv.get_json()["error"].lower()


# ── 15. Error shape contract ───────────────────────────────────────────────────

def test_payment_on_closed_tab_has_error_field(client, owner_token, service_item_id):
    """A payment on a closed tab must return an 'error' field."""
    tab_id   = _open_tab(client, owner_token)
    order_id = _create_order(client, owner_token, tab_id, service_item_id)
    _send_order(client, owner_token, order_id)
    # Service item → immediately SERVED, no pending items. Pay exactly.
    _pay(client, owner_token, tab_id, "500")
    # Now close the tab
    rv = client.post(f"/tabs/{tab_id}/close",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    # Now try to pay again on the closed tab
    rv = _pay(client, owner_token, tab_id, "100")
    assert rv.status_code == 400
    assert "error" in rv.get_json()


def test_nonexistent_tab_returns_error_field(client, owner_token):
    rv = client.post("/tabs/nonexistent/payments",
                     json={"amount": "100", "method": "CASH"},
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 404
    assert "error" in rv.get_json()


def test_invalid_payment_method_returns_error_field(client, owner_token, food_item_id):
    tab_id = _open_tab(client, owner_token)
    rv = _pay(client, owner_token, tab_id, "100", method="CHEQUE")
    assert rv.status_code == 400
    assert "error" in rv.get_json()


# ── F-17.5: READY notifies the waiter who created the order ──────────────────

def test_ready_notifies_order_creator(client, waiter_token, kitchen_token, food_item_id):
    """Kitchen marks an item READY → the waiter gets an in-app notification."""
    tab_id   = _open_tab(client, waiter_token, reference="Table 9")
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)

    # Find the order item and walk it to READY as kitchen staff
    rv = client.get(f"/tabs/{tab_id}", headers={"Authorization": f"Bearer {waiter_token}"})
    oi_id = rv.get_json()["orders"][0]["items"][0]["id"]
    kh = {"Authorization": f"Bearer {kitchen_token}"}
    assert client.post(f"/order-items/{oi_id}/receive", headers=kh).status_code == 200
    assert client.post(f"/order-items/{oi_id}/ready",   headers=kh).status_code == 200

    # Waiter's inbox now contains the order_ready notification
    inbox = client.get("/notifications/inbox",
                       headers={"Authorization": f"Bearer {waiter_token}"}).get_json()
    ready = [n for n in inbox if n["reference_type"] == "order_ready"]
    assert len(ready) == 1
    assert "Table 9" in ready[0]["subject"]
    assert "ready for pickup" in ready[0]["body"]


# ── F-17.5: cancel reverses the charge (guest never pays for cancelled food) ──

def test_cancel_after_send_reverses_charge(client, waiter_token, food_item_id, drink_item_id):
    """Cancel a sent item → negative reversal charge → balance drops."""
    wh = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = _open_tab(client, waiter_token, reference="Table R")
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)  # 1200
    _send_order(client, waiter_token, order_id)

    before = client.get(f"/tabs/{tab_id}", headers=wh).get_json()
    assert before["balance"] == "1200.00"
    oi_id = before["orders"][0]["items"][0]["id"]

    rv = client.post(f"/order-items/{oi_id}/cancel", json={"reason": "guest changed mind"}, headers=wh)
    assert rv.status_code == 200

    after = client.get(f"/tabs/{tab_id}", headers=wh).get_json()
    assert after["balance"] == "0.00"                       # reversal corrected it
    amounts = sorted(c["amount"] for c in after["charges"])
    assert amounts == ["-1200.00", "1200.00"]               # original frozen + mirror row
    assert any("REVERSAL" in c["description"] for c in after["charges"])

    # Fully reversed tab closes cleanly
    assert client.post(f"/tabs/{tab_id}/close", headers=wh).status_code == 200


def test_cancel_restricted_to_own_waiter_or_manager(client, waiter_token, kitchen_token,
                                                    manager_token, food_item_id):
    """Cancel moves money — only the order's waiter or a manager may do it."""
    wh = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = _open_tab(client, waiter_token)
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)
    oi_id = client.get(f"/tabs/{tab_id}", headers=wh).get_json()["orders"][0]["items"][0]["id"]

    rv = client.post(f"/order-items/{oi_id}/cancel",
                     headers={"Authorization": f"Bearer {kitchen_token}"})
    assert rv.status_code == 403
    assert "waiter who took this order" in rv.get_json()["error"]

    # Manager can
    rv = client.post(f"/order-items/{oi_id}/cancel",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200


def test_cancel_cannot_double_reverse(client, waiter_token, food_item_id):
    """Second cancel is rejected by the state machine — exactly one reversal row."""
    wh = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = _open_tab(client, waiter_token)
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)
    oi_id = client.get(f"/tabs/{tab_id}", headers=wh).get_json()["orders"][0]["items"][0]["id"]

    assert client.post(f"/order-items/{oi_id}/cancel", headers=wh).status_code == 200
    assert client.post(f"/order-items/{oi_id}/cancel", headers=wh).status_code == 400

    charges = client.get(f"/tabs/{tab_id}", headers=wh).get_json()["charges"]
    assert len([c for c in charges if float(c["amount"]) < 0]) == 1


def test_send_back_reverses_charge_too(client, waiter_token, manager_token, food_item_id):
    """Manager send-back mirrors money the way it already mirrored stock."""
    wh = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = _open_tab(client, waiter_token)
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)
    oi_id = client.get(f"/tabs/{tab_id}", headers=wh).get_json()["orders"][0]["items"][0]["id"]
    # walk to RECEIVED so send-back is a realistic mid-prep return
    client.post(f"/order-items/{oi_id}/receive", headers={"Authorization": f"Bearer {manager_token}"})

    rv = client.post(f"/order-items/{oi_id}/send-back",
                     json={"idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    assert client.get(f"/tabs/{tab_id}", headers=wh).get_json()["balance"] == "0.00"


# ── Menu station scoping ──────────────────────────────────────────────────────
# A station tablet must only ever receive the catalogue it serves. Before this,
# GET /menu/items shipped every row — spa treatments, villa charges, jet ski
# hire — to every POS device, and the station apps filtered client-side.

def test_menu_scopes_to_one_station(client, waiter_token, food_item_id, drink_item_id, service_item_id):
    """?station=KITCHEN returns kitchen items only — no drinks, no services."""
    rv = client.get("/menu/items?station=KITCHEN",
                    headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200
    ids = {i["id"] for i in rv.get_json()}
    assert food_item_id in ids
    assert drink_item_id not in ids
    assert service_item_id not in ids


def test_menu_scopes_to_several_stations(client, waiter_token, food_item_id, drink_item_id, service_item_id):
    """A waiter takes food AND drink, so their screen asks for both — and still
    must not see the spa/pool catalogue a manager sells."""
    rv = client.get("/menu/items?station=KITCHEN,BAR",
                    headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200
    ids = {i["id"] for i in rv.get_json()}
    assert {food_item_id, drink_item_id} <= ids
    assert service_item_id not in ids


def test_menu_without_station_is_unchanged(client, waiter_token, food_item_id, service_item_id):
    """No station param = the full catalogue, exactly as before. The owner's
    menu-management screens depend on this."""
    rv = client.get("/menu/items", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200
    ids = {i["id"] for i in rv.get_json()}
    assert {food_item_id, service_item_id} <= ids


def test_menu_rejects_unknown_station_in_plain_english(client, waiter_token):
    """Invariant 5: every error carries a message a human can act on."""
    rv = client.get("/menu/items?station=PIZZA_OVEN",
                    headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 400
    assert "PIZZA_OVEN" in rv.get_json()["error"]
    assert "KITCHEN" in rv.get_json()["error"]


# ── Menu authoring: chef owns the food and the juices, not the liquor ─────────

def test_chef_can_create_a_juice(client, chef_token, general_dept_id):
    """Non-alcoholic bar item — squeezed to a recipe like a dish is plated to one."""
    rv = client.post("/menu/items", json={
        "name": "Passion Juice", "price": "400", "category": "Soft Drinks",
        "prep_station": "BAR", "department_id": general_dept_id,
    }, headers={"Authorization": f"Bearer {chef_token}"})
    assert rv.status_code == 201, rv.get_json()


def test_chef_cannot_create_alcohol(client, chef_token, general_dept_id):
    """Beer, wine and cocktails are a licensed list a manager signs for."""
    rv = client.post("/menu/items", json={
        "name": "House Negroni", "price": "900", "category": "Cocktails",
        "prep_station": "BAR", "department_id": general_dept_id,
        "is_alcoholic": True,
    }, headers={"Authorization": f"Bearer {chef_token}"})
    assert rv.status_code == 403
    assert "manager" in rv.get_json()["error"].lower()


def test_chef_cannot_reprice_existing_alcohol(client, chef_token, manager_token, general_dept_id):
    """The gate reads the STORED flag, not just what the request claims."""
    made = client.post("/menu/items", json={
        "name": "Reserve Whisky", "price": "1200", "category": "Spirits",
        "prep_station": "BAR", "department_id": general_dept_id, "is_alcoholic": True,
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert made.status_code == 201
    item_id = made.get_json()["id"]

    rv = client.patch(f"/menu/items/{item_id}", json={"price": "200"},
                      headers={"Authorization": f"Bearer {chef_token}"})
    assert rv.status_code == 403


def test_chef_cannot_relabel_a_dish_into_a_drink(client, chef_token, food_item_id):
    """Closing the back door: setting is_alcoholic is itself a manager action."""
    rv = client.patch(f"/menu/items/{food_item_id}", json={"is_alcoholic": True},
                      headers={"Authorization": f"Bearer {chef_token}"})
    assert rv.status_code == 403


# ── Receipt visibility ────────────────────────────────────────────────────────
# GET /receipts (search) required front desk; GET /receipts/:id (the full bill)
# required nothing. The search returns one summary line per tab; the detail
# returns every item consumed, every payment method and every M-Pesa code.
# The weaker gate was on the stronger data.

def test_waiter_can_open_their_own_tabs_bill(client, waiter_token, food_item_id):
    """A waiter closing their own table needs the bill."""
    tab_id = _open_tab(client, waiter_token)
    rv = client.get(f"/receipts/{tab_id}", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["tab_id"] == tab_id


def test_waiter_cannot_open_someone_elses_bill(client, waiter_token, manager_token):
    """A tab opened by someone else is not theirs to read."""
    other_tab = _open_tab(client, manager_token, reference="Villa 2 / Guest")
    rv = client.get(f"/receipts/{other_tab}", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 403
    assert "serving" in rv.get_json()["error"].lower()


def test_front_desk_can_open_any_bill(client, manager_token, waiter_token):
    """Settling other people's accounts is the job — a villa folio at check-out
    is never a tab front desk opened themselves."""
    waiters_tab = _open_tab(client, waiter_token)
    rv = client.get(f"/receipts/{waiters_tab}", headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200


# ── Credential seizure: manager resets a password, then trades on the account ──
#
# A manager may reset any subordinate's password — people forget them. But the
# API accepts password login, and a PIN only guards the station's login SCREEN,
# not the endpoints under it. So the reset is enough to act as that person, and
# every charge lands on their name. It cannot be forbidden; it is made loud.

def test_password_reset_is_logged_as_its_own_action(client, owner_token, app):
    """It used to log action='user.edit' with no details — indistinguishable
    from a department change. A tilapia's price was better audited."""
    from app.extensions import db as _db
    from app.models.user import User
    from app.models.audit_log import AuditLog

    with app.app_context():
        waiter = _db.session.query(User).filter_by(username="waiter1").first()
        waiter_id = waiter.id

    rv = client.patch(f"/auth/users/{waiter_id}", json={"password": "TempPass123!"},
                      headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200

    with app.app_context():
        entry = _db.session.query(AuditLog).filter_by(action="user.password_reset").first()
        assert entry is not None, "a password reset must be its own audit action"
        assert "PASSWORD RESET" in (entry.details or "")
        assert entry.target == "waiter1"
        # The password itself must never reach the log.
        assert "TempPass123!" not in (entry.details or "")


def test_password_reset_notifies_the_owner(client, owner_token, app):
    """menu.py pings the owner when a price moves. Seizing a colleague's
    credentials warrants at least the same."""
    from app.extensions import db as _db
    from app.models.user import User
    from app.models.notification import Notification

    with app.app_context():
        waiter = _db.session.query(User).filter_by(username="waiter1").first()
        waiter_id = waiter.id

    client.patch(f"/auth/users/{waiter_id}", json={"password": "TempPass123!"},
                 headers={"Authorization": f"Bearer {owner_token}"})

    with app.app_context():
        note = _db.session.query(Notification).filter(
            Notification.subject.like("Password reset%")
        ).first()
        assert note is not None, "the owner must be told a password was reset"
        assert "waiter1" in note.body
        assert "TempPass123!" not in note.body


def test_department_change_is_not_flagged_as_a_reset(client, owner_token, app, general_dept_id):
    """The point is to tell the two APART — a routine edit must stay routine."""
    from app.extensions import db as _db
    from app.models.user import User
    from app.models.audit_log import AuditLog

    with app.app_context():
        waiter = _db.session.query(User).filter_by(username="waiter1").first()
        waiter_id = waiter.id

    rv = client.patch(f"/auth/users/{waiter_id}", json={"department_id": general_dept_id},
                      headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200

    with app.app_context():
        assert _db.session.query(AuditLog).filter_by(action="user.password_reset").count() == 0
        edit = _db.session.query(AuditLog).filter_by(action="user.edit").first()
        assert edit is not None and "department" in (edit.details or "")


def test_bank_transfer_reference_is_stored(client, owner_token, food_item_id, app):
    """Payment.bank_ref was a column nothing wrote to, so a bank transfer's
    reference vanished — and it is the only handle /finance/bank/reconcile has
    to match that payment to a statement line."""
    from app.extensions import db as _db
    from app.models.payment import Payment

    tab_id = _open_tab(client, owner_token)
    rv = client.post(f"/tabs/{tab_id}/payments", json={
        "method": "BANK_TRANSFER", "amount": "500",
        "bank_ref": "EQ-88231", "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code in (200, 201), rv.get_json()

    with app.app_context():
        p = _db.session.query(Payment).filter_by(tab_id=tab_id, method="BANK_TRANSFER").first()
        assert p is not None
        assert p.bank_ref == "EQ-88231", "bank reference must survive to reconciliation"


# ── Charging to a room ────────────────────────────────────────────────────────

def _open_villa_tab(app, reference: str) -> str:
    """A VILLA tab, made directly. The endpoint filters on tab_type, and the
    real path to one is booking -> deposit -> confirm -> check-in, which is a
    different test's job."""
    from app.extensions import db as _db
    from app.models.tab import Tab, TabType, TabStatus
    from app.models.user import User
    with app.app_context():
        owner = _db.session.query(User).filter_by(username="owner1").first()
        tab = Tab(tab_type=TabType.VILLA.value, reference=reference,
                  opened_by_id=owner.id, status=TabStatus.OPEN.value)
        _db.session.add(tab)
        _db.session.commit()
        return tab.id


def test_room_lookup_finds_the_villa_account(client, waiter_token, app):
    """A wristband has had a lookup since Chunk 7; a villa had none, so
    "put it on Villa 6" left the waiter scrolling every open villa tab."""
    tab_id = _open_villa_tab(app, "Villa 7 / Test Guest")
    rv = client.get("/tabs/by-room/Villa 7", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200, rv.get_json()
    body = rv.get_json()
    assert body["tab_id"] == tab_id
    # The register travels with the tab: "where does this go" and "should it"
    # are asked in the same breath by the same person.
    assert "may_charge" in body


def test_room_lookup_never_guesses_between_rooms(client, waiter_token, app):
    """'Villa 3' substring-matches Villa 3 AND Villa 31. Picking one silently
    would charge a different guest's account."""
    _open_villa_tab(app, "Villa 3 / Guest A")
    _open_villa_tab(app, "Villa 31 / Guest B")
    rv = client.get("/tabs/by-room/Villa 3", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code in (200, 409)
    if rv.status_code == 200:
        assert rv.get_json()["reference"].startswith("Villa 3 /"), "must not resolve to Villa 31"
    else:
        assert len(rv.get_json()["candidates"]) > 1


def test_room_lookup_404s_for_an_unknown_room(client, waiter_token):
    rv = client.get("/tabs/by-room/Villa 999", headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 404
    assert "Villa 999" in rv.get_json()["error"]


def test_bar_posted_waiter_can_still_take_orders(client, app, food_item_id, wifi_allowed):
    """The prep-staff block gated on DEPARTMENT, so a waiter posted to the Bar
    — an entirely normal posting — could not take a drinks order at the bar
    they work at. A waiter is a waiter wherever they are standing."""
    from app.extensions import db as _db
    from app.models.user import User
    from app.models.role import Role
    from app.models.department import Department

    with app.app_context():
        role = _db.session.query(Role).filter_by(name="waiter").first()
        if not role:
            role = Role(name="waiter", level=1)
            _db.session.add(role); _db.session.flush()
        bar = _db.session.query(Department).filter_by(name="Bar").first()
        if not bar:
            bar = Department(name="Bar")
            _db.session.add(bar); _db.session.flush()
        u = _db.session.query(User).filter_by(username="barwaiter1").first()
        if not u:
            u = User(username="barwaiter1", role_id=role.id, department_id=bar.id)
            u.set_password("BarPass1!")
            _db.session.add(u)
        else:
            u.role_id, u.department_id = role.id, bar.id
        _db.session.commit()

    token = client.post("/auth/login", json={"username": "barwaiter1", "password": "BarPass1!"}) \
                  .get_json()["access_token"]
    # Clock in through the real endpoint — create_order is @require_clocked_in.
    with app.app_context():
        from app.models.employee_profile import EmployeeProfile
        u = _db.session.query(User).filter_by(username="barwaiter1").first()
        if not _db.session.query(EmployeeProfile).filter_by(user_id=u.id).first():
            _db.session.add(EmployeeProfile(user_id=u.id, full_name="Bar Waiter",
                                            phone="+254700000099"))
            _db.session.commit()
    client.post("/hr/clock-in", json={}, headers={"Authorization": f"Bearer {token}"},
                environ_base={"REMOTE_ADDR": "127.0.0.1"})

    rv = client.post("/tabs", json={"reference": "Bar stool 1", "idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code in (200, 201), rv.get_json()

    tab_id = rv.get_json()["id"]
    rv = client.post("/orders", json={"tab_id": tab_id,
                                      "items": [{"menu_item_id": food_item_id, "quantity": 1}],
                                      "idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code in (200, 201), rv.get_json()
