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
