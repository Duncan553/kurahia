"""
test_inventory_consumption.py — Stage 2: auto-consumption on Ready,
reversal on cancel-after-Ready, low-stock alerts, no-recipe alerts.
"""
import uuid
from decimal import Decimal
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.notification import Notification
from app.models.recipe_line import RecipeLine
from app.services.stock import get_current_stock


# ── Shared helpers ────────────────────────────────────────────────────────────

def _buy(client, token, item_id, qty, total_cost):
    return client.post("/inventory/purchases", json={
        "item_id": item_id, "quantity": qty, "actual_cost": total_cost,
        "receipt_photo_path": "receipts/test.jpg",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})


def _set_recipe(client, token, menu_item_id, inv_item_id, qty="0.3"):
    return client.post(f"/menu/items/{menu_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item_id, "quantity": qty}],
    }, headers={"Authorization": f"Bearer {token}"})


def _make_order_item(client, token, food_item_id):
    """Create order + send it → returns the order_item_id for a PENDING routed item."""
    rv = client.post("/orders", json={
        "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
    order_id = rv.get_json()["id"]

    rv2 = client.post(f"/orders/{order_id}/send",
                      headers={"Authorization": f"Bearer {token}"})
    assert rv2.status_code == 200

    # Get the order item
    from app.models.order import Order
    from app.models.order_item import OrderItem
    with client.application.app_context():
        order = db.session.get(Order, order_id)
        oi_id = order.items[0].id
    return oi_id


@pytest.fixture
def inv_item(app):
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(name="Tilapia Fillet", unit="kg",
                           department_id=dept.id, reorder_level="2")
        db.session.add(it)
        db.session.commit()
        return it.id


# ── 2.1: Auto-consumption on Ready ───────────────────────────────────────────

def test_ready_auto_consumes(app, client, manager_token, food_item_id, inv_item):
    """Marking an item READY deducts recipe ingredients from stock."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    with app.app_context():
        before = get_current_stock(inv_item)  # should be 10

    oi_id = _make_order_item(client, manager_token, food_item_id)

    # Receive
    rv = client.post(f"/order-items/{oi_id}/receive",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    # Mark READY → triggers auto-consumption
    rv2 = client.post(f"/order-items/{oi_id}/ready",
                      headers={"Authorization": f"Bearer {manager_token}"})
    assert rv2.status_code == 200

    with app.app_context():
        after = get_current_stock(inv_item)

    assert before - after == Decimal("0.3"), f"Expected 0.3 deducted, got {before - after}"


def test_ready_multi_qty_consumes_proportionally(app, client, manager_token, food_item_id, inv_item):
    """Order qty=2 deducts 2 × recipe.quantity from stock."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    # Create order with qty=2
    rv = client.post("/orders", json={
        "items": [{"menu_item_id": food_item_id, "quantity": 2}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {manager_token}"})
    order_id = rv.get_json()["id"]
    client.post(f"/orders/{order_id}/send",
                headers={"Authorization": f"Bearer {manager_token}"})

    from app.models.order import Order
    with app.app_context():
        oi_id = db.session.get(Order, order_id).items[0].id
        before = get_current_stock(inv_item)

    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        after = get_current_stock(inv_item)

    assert before - after == Decimal("0.6"), f"Expected 0.6 deducted, got {before - after}"


def test_ready_consumption_movement_reason(app, client, manager_token, food_item_id, inv_item):
    """Auto-consumption writes SALE movements (not SALE_PLACEHOLDER)."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        mv = db.session.query(StockMovement).filter_by(
            item_id=inv_item, reason=MovementReason.SALE.value
        ).first()
        assert mv is not None
        assert Decimal(str(mv.change_amount)) == Decimal("-0.3")


def test_ready_no_recipe_queues_chef_alert(app, client, manager_token, food_item_id):
    """If no recipe set, marking READY queues a no-recipe alert to the head chef / owner."""
    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.subject.contains("No recipe")
        ).first()
        assert notif is not None
        assert "recipe" in notif.body.lower()


def test_ready_no_recipe_alert_not_duplicated(app, client, manager_token, food_item_id):
    """Selling same no-recipe item twice only sends one alert."""
    for _ in range(2):
        oi_id = _make_order_item(client, manager_token, food_item_id)
        client.post(f"/order-items/{oi_id}/receive",
                    headers={"Authorization": f"Bearer {manager_token}"})
        client.post(f"/order-items/{oi_id}/ready",
                    headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        count = db.session.query(Notification).filter(
            Notification.subject.contains("No recipe")
        ).count()
        assert count == 1, f"Expected 1 no-recipe alert, got {count}"


# ── 2.2: Reversal on cancel-after-Ready ──────────────────────────────────────

def test_cancel_ready_reverses_stock(app, client, manager_token, food_item_id, inv_item):
    """Cancelling a READY item restores the consumed stock."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        after_ready = get_current_stock(inv_item)  # should be 9.7

    rv = client.post(f"/order-items/{oi_id}/cancel",
                     json={"reason": "wrong table"},
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    with app.app_context():
        after_cancel = get_current_stock(inv_item)

    assert after_cancel - after_ready == Decimal("0.3"), \
        f"Expected 0.3 restored, got {after_cancel - after_ready}"


def test_cancel_pending_no_stock_change(app, client, manager_token, food_item_id, inv_item):
    """Cancelling a PENDING item (not yet consumed) does not touch stock."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, manager_token, food_item_id)

    with app.app_context():
        before = get_current_stock(inv_item)

    client.post(f"/order-items/{oi_id}/cancel",
                json={"reason": "mistake"},
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        after = get_current_stock(inv_item)

    assert before == after, f"Expected no stock change, before={before} after={after}"


def test_cancel_ready_requires_manager(app, client, manager_token, waiter_token,
                                       food_item_id, inv_item):
    """A waiter cannot cancel a READY item — only a manager can."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, waiter_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    # Waiter tries to cancel — should be denied
    rv = client.post(f"/order-items/{oi_id}/cancel",
                     json={"reason": "customer left"},
                     headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 403


# ── 2.3: Low-stock alert ──────────────────────────────────────────────────────

def test_low_stock_alert_fires(app, client, manager_token, food_item_id, inv_item):
    """After consumption drops stock below reorder_level, owner gets a notification."""
    # reorder_level=2, buy 2.2 kg, recipe=0.3 kg → after Ready: 1.9 kg < 2 (triggers alert)
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty="2.2", total_cost=1100)

    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.subject == "Low stock: Tilapia Fillet"
        ).first()
        assert notif is not None
        assert "reorder" in notif.body.lower()
        assert notif.status == "QUEUED"


def test_low_stock_alert_no_spam(app, client, manager_token, food_item_id, inv_item):
    """Selling the same item below reorder level twice only queues one alert."""
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty="2.2", total_cost=1100)

    for _ in range(2):
        oi_id = _make_order_item(client, manager_token, food_item_id)
        client.post(f"/order-items/{oi_id}/receive",
                    headers={"Authorization": f"Bearer {manager_token}"})
        client.post(f"/order-items/{oi_id}/ready",
                    headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        count = db.session.query(Notification).filter(
            Notification.subject == "Low stock: Tilapia Fillet"
        ).count()
        assert count == 1, f"Expected 1 low-stock notification, got {count}"


def test_no_alert_when_stock_above_reorder(app, client, manager_token, food_item_id, inv_item):
    """No low-stock notification when stock stays above reorder_level."""
    # reorder_level=2, buy 10 kg, recipe=0.3 → after Ready: 9.7 kg >> 2
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        count = db.session.query(Notification).filter(
            Notification.subject == "Low stock: Tilapia Fillet"
        ).count()
        assert count == 0


# ── 2.4: Send-back does NOT reverse stock ────────────────────────────────────

def test_send_back_ready_item_no_extra_deduction(app, client, manager_token, food_item_id, inv_item):
    """
    Send-back on a READY item (chef-side rejection before serving).
    Auto-consumption already ran on Ready. The send-back itself does NOT write
    a second deduction — it only reverses the charge. Stock stays at the post-
    Ready level (already deducted once; ingredients consumed, food not salvageable).
    """
    _set_recipe(client, manager_token, food_item_id, inv_item, qty="0.3")
    _buy(client, manager_token, inv_item, qty=10, total_cost=5000)

    oi_id = _make_order_item(client, manager_token, food_item_id)
    client.post(f"/order-items/{oi_id}/receive",
                headers={"Authorization": f"Bearer {manager_token}"})
    client.post(f"/order-items/{oi_id}/ready",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        stock_after_ready = get_current_stock(inv_item)  # 9.7

    rv = client.post(f"/order-items/{oi_id}/send-back",
                     json={"idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    with app.app_context():
        stock_after_sendback = get_current_stock(inv_item)

    # send-back does not write any additional stock movement
    assert stock_after_sendback == stock_after_ready, \
        f"Expected no further stock change on send-back, before={stock_after_ready} after={stock_after_sendback}"

    # Confirm no SALE reversal movement was written (only the original SALE deduction exists)
    with app.app_context():
        reversals = db.session.query(StockMovement).filter(
            StockMovement.item_id == inv_item,
            StockMovement.change_amount > 0,
            StockMovement.reason == MovementReason.SALE.value,
        ).count()
        assert reversals == 0, "Send-back should not write a positive SALE movement"
