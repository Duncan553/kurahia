"""
test_refund.py — POST /order-items/:id/refund endpoint.

GAP 2 fix tests:
  1. Manager can refund a SERVED item → status REFUNDED, negative charge on tab
  2. Waiter cannot refund (403)
  3. Non-SERVED item returns 409 with plain-English message
  4. Idempotency: same call twice returns same result, no double-charge reversal
"""
import uuid
import pytest
from decimal import Decimal
from app.extensions import db
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.charge import Charge


# ── helpers ────────────────────────────────────────────────────────────────────

def _open_tab(client, token):
    rv = client.post("/tabs", json={}, headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
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


def _get_order_item_id(app, order_id):
    """Return the first OrderItem id for a given order."""
    with app.app_context():
        oi = db.session.query(OrderItem).filter_by(order_id=order_id).first()
        return oi.id


def _fully_serve_kitchen_item(client, app, manager_token, waiter_token, food_item_id):
    """
    Create an order with a KITCHEN item and walk it all the way to SERVED.
    Returns (tab_id, order_item_id).
    KITCHEN path: PENDING → RECEIVED → READY → SERVED
    """
    tab_id = _open_tab(client, waiter_token)
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)

    oi_id = _get_order_item_id(app, order_id)

    # Kitchen receives it
    rv = client.post(f"/order-items/{oi_id}/receive",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200, rv.get_json()

    # Kitchen marks ready (also deducts stock)
    rv = client.post(f"/order-items/{oi_id}/ready",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200, rv.get_json()

    # Waiter marks served
    rv = client.post(f"/order-items/{oi_id}/serve",
                     headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 200, rv.get_json()

    return tab_id, oi_id


def _refund(client, token, oi_id, reason="wrong table", idem_key=None):
    return client.post(f"/order-items/{oi_id}/refund", json={
        "reason": reason,
        "idempotency_key": idem_key or str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})


# ── 1. Manager can refund a SERVED item ───────────────────────────────────────

def test_manager_refunds_served_item(app, client, manager_token, waiter_token, food_item_id):
    """
    Happy path: manager refunds a SERVED item.
    - Status becomes REFUNDED
    - A negative Charge is appended to the tab (append-only ledger)
    - The positive original Charge row is untouched
    """
    tab_id, oi_id = _fully_serve_kitchen_item(client, app, manager_token, waiter_token, food_item_id)

    rv = _refund(client, manager_token, oi_id, reason="wrong table charged")
    assert rv.status_code == 200, rv.get_json()

    data = rv.get_json()
    assert data["status"] == "REFUNDED"
    assert "Refund processed" in data["message"]
    assert data.get("duplicate") is None  # not a duplicate

    with app.app_context():
        oi = db.session.get(OrderItem, oi_id)
        assert oi.status == OrderItemStatus.REFUNDED.value
        assert oi.cancel_reason == "wrong table charged"

        # Append-only: both the positive charge and the negative reversal must exist
        charges = db.session.query(Charge).filter_by(order_item_id=oi_id).all()
        positive = [c for c in charges if c.amount > 0]
        negative = [c for c in charges if c.amount < 0]
        assert len(positive) == 1, "original charge must still exist (frozen history)"
        assert len(negative) == 1, "reversal charge must be appended"
        # Amounts cancel out
        assert positive[0].amount + negative[0].amount == 0


# ── 2. Waiter cannot refund (403) ─────────────────────────────────────────────

def test_waiter_cannot_refund(app, client, manager_token, waiter_token, food_item_id):
    """
    Waiters (role.level = 1) are below MANAGER_LEVEL = 5.
    Refund endpoint must return 403 before touching the item.
    """
    _, oi_id = _fully_serve_kitchen_item(client, app, manager_token, waiter_token, food_item_id)

    rv = _refund(client, waiter_token, oi_id)
    assert rv.status_code == 403
    body = rv.get_json()
    assert "error" in body
    # Item must still be SERVED (no state change happened)
    with app.app_context():
        oi = db.session.get(OrderItem, oi_id)
        assert oi.status == OrderItemStatus.SERVED.value


# ── 3. Non-SERVED item returns 409 ────────────────────────────────────────────

def test_non_served_item_returns_409(app, client, manager_token, waiter_token, food_item_id):
    """
    PENDING item (order sent but not yet received by kitchen) cannot be refunded.
    Must return 409 with a plain-English explanation so the manager understands
    they should use the cancel endpoint instead.
    """
    tab_id = _open_tab(client, waiter_token)
    order_id = _create_order(client, waiter_token, tab_id, food_item_id)
    _send_order(client, waiter_token, order_id)

    oi_id = _get_order_item_id(app, order_id)

    # Item is PENDING — refund must be refused
    rv = _refund(client, manager_token, oi_id, reason="should not work")
    assert rv.status_code == 409
    body = rv.get_json()
    assert "error" in body
    # Plain-English: should mention current status or direct to cancel endpoint
    assert any(word in body["error"].lower() for word in ["pending", "served", "cancel"])


# ── 4. Idempotency: same key twice, no double reversal ────────────────────────

def test_refund_idempotency(app, client, manager_token, waiter_token, food_item_id):
    """
    Calling the refund endpoint twice with the same idempotency_key must:
    - Return a success response both times (not 4xx on second call)
    - NOT create a second negative Charge (no double-reversal)
    - Return duplicate=True on the second call
    """
    tab_id, oi_id = _fully_serve_kitchen_item(client, app, manager_token, waiter_token, food_item_id)
    idem = str(uuid.uuid4())

    rv1 = _refund(client, manager_token, oi_id, idem_key=idem)
    assert rv1.status_code == 200, rv1.get_json()
    assert rv1.get_json().get("duplicate") is None  # first call is not a duplicate

    rv2 = _refund(client, manager_token, oi_id, idem_key=idem)
    assert rv2.status_code == 200, rv2.get_json()
    assert rv2.get_json()["duplicate"] is True  # second call signals duplicate

    with app.app_context():
        # Only one negative charge must exist — no double-reversal
        negative_charges = db.session.query(Charge).filter(
            Charge.order_item_id == oi_id,
            Charge.amount < 0,
        ).all()
        assert len(negative_charges) == 1, "double-reversal detected: two negative charges found"
