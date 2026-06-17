"""
test_order_notes.py — Stage 5.3.5: notes field on OrderItem.
"""
import pytest
from app.extensions import db
from app.models.order_item import OrderItem
from app.models.menu_item import MenuItem


def _open_tab(client, token):
    rv = client.post("/tabs", json={}, headers={"Authorization": f"Bearer {token}"})
    return rv.get_json()["id"]


class TestOrderNotes:
    def test_notes_persists_on_create(self, app, client, waiter_token, food_item_id):
        tab_id = _open_tab(client, waiter_token)
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": food_item_id, "quantity": 1, "notes": "no onions please"}],
        }, headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 201

        oi = db.session.query(OrderItem).filter_by(order_id=rv.get_json()["id"]).first()
        assert oi.notes == "no onions please"

    def test_notes_in_queue_response(self, app, client, waiter_token, manager_token, food_item_id):
        tab_id = _open_tab(client, waiter_token)
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": food_item_id, "quantity": 1, "notes": "extra spicy"}],
        }, headers={"Authorization": f"Bearer {waiter_token}"})
        order_id = rv.get_json()["id"]
        client.post(f"/orders/{order_id}/send",
                     headers={"Authorization": f"Bearer {waiter_token}"})

        rv = client.get("/kitchen/queue",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        items = rv.get_json()
        noted = [i for i in items if i.get("notes") == "extra spicy"]
        assert len(noted) == 1

    def test_notes_truncated_at_200(self, app, client, waiter_token, food_item_id):
        tab_id = _open_tab(client, waiter_token)
        long_note = "x" * 300
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": food_item_id, "quantity": 1, "notes": long_note}],
        }, headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 201

        oi = db.session.query(OrderItem).filter_by(order_id=rv.get_json()["id"]).first()
        assert len(oi.notes) == 200
