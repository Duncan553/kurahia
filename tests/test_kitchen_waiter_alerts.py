"""
The two halves of the kitchen conversation.

The kitchen has always been told when an order arrives. The other direction
was only half built: marking an item READY wrote a notification to the waiter,
so the cook's "Waiter has been notified." was true — but the waiter's end
rendered it silently on one screen they are never standing at.

These fix the server half in place: the ping exists, it goes to the RIGHT
waiter, it reads like something a person can act on, and it retires when the
plate is collected.
"""
import uuid
import pytest
from tests.helpers import open_tab
from decimal import Decimal

from app.extensions import db


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _ready_pings_for(username):
    from app.models.notification import Notification
    from app.models.user import User
    u = db.session.query(User).filter_by(username=username).first()
    return db.session.query(Notification).filter_by(
        recipient_user_id=u.id, reference_type="order_ready").all()


@pytest.fixture
def kitchen_item(app):
    """A dish that goes to the kitchen and consumes nothing."""
    from app.models.menu_item import MenuItem, StockTracking, PrepStation
    from app.models.department import Department
    dept = db.session.query(Department).first()
    item = MenuItem(name="Grilled Tilapia (test)", price=Decimal("1200.00"),
                    category="Main", department_id=dept.id, is_active=True,
                    prep_station=PrepStation.KITCHEN.value,
                    stock_tracking=StockTracking.SERVICE.value)
    db.session.add(item)
    db.session.commit()
    return item.id


def _send_order(client, waiter_token, item_id, reference="Table 9"):
    # The floor cannot open a nameless account any more — every bill belongs to
    # a wristband or a room. This test is about the kitchen seeing the order,
    # not about who may open an account, so it uses the manager override.
    tab = open_tab(client, reference)
    order = client.post("/orders", json={
        "tab_id": tab["id"], "items": [{"menu_item_id": item_id, "quantity": 1}],
    }, headers=auth(waiter_token)).get_json()
    sent = client.post(f"/orders/{order['id']}/send", headers=auth(waiter_token))
    assert sent.status_code == 200, sent.get_json()
    return tab, order


def test_kitchen_sees_the_order_the_waiter_sent(client, waiter_token, chef_token, kitchen_item):
    _, order = _send_order(client, waiter_token, kitchen_item)
    q = client.get("/kitchen/queue", headers=auth(chef_token)).get_json()
    assert any(row["order_id"] == order["id"] for row in q)


def test_marking_ready_alerts_the_waiter_who_sent_it(
        client, waiter_token, chef_token, kitchen_item):
    """The half that was missing at the waiter's end."""
    _, order = _send_order(client, waiter_token, kitchen_item)
    q = client.get("/kitchen/queue", headers=auth(chef_token)).get_json()
    oi = next(r["order_item_id"] for r in q if r["order_id"] == order["id"])

    client.post(f"/order-items/{oi}/receive", headers=auth(chef_token))
    assert client.post(f"/order-items/{oi}/ready", headers=auth(chef_token)).status_code == 200

    pings = [p for p in _ready_pings_for("waiter1") if p.reference_id == oi]
    assert pings, "the cook was told the waiter was notified; the waiter was not"
    body = pings[0].body
    # It has to name the table — "an order is ready" is useless in a full room.
    assert "Table 9" in body
    assert "Grilled Tilapia (test)" in body
    # Plates are counted, not weighed: "1x", never "1.00x"
    assert "1.00x" not in body
    assert "1x" in body


def test_the_alert_goes_to_the_waiter_who_sent_it_and_nobody_else(
        client, waiter_token, chef_token, kitchen_item):
    """
    A second waiter on shift must not be pulled to another person's table. The
    ping is addressed to order.created_by, and this is what holds that.
    """
    _, order = _send_order(client, waiter_token, kitchen_item)
    q = client.get("/kitchen/queue", headers=auth(chef_token)).get_json()
    oi = next(r["order_item_id"] for r in q if r["order_id"] == order["id"])
    client.post(f"/order-items/{oi}/receive", headers=auth(chef_token))
    client.post(f"/order-items/{oi}/ready", headers=auth(chef_token))

    from app.models.notification import Notification
    from app.models.user import User
    recipients = {
        db.session.get(User, n.recipient_user_id).username
        for n in db.session.query(Notification).filter_by(
            reference_type="order_ready", reference_id=oi).all()
    }
    assert recipients == {"waiter1"}


def test_the_alert_retires_once_the_plate_is_served(
        client, waiter_token, chef_token, kitchen_item):
    """
    An alert that stays up after the food is collected is an alert people learn
    to ignore — and then they ignore the next one too.
    """
    _, order = _send_order(client, waiter_token, kitchen_item)
    q = client.get("/kitchen/queue", headers=auth(chef_token)).get_json()
    oi = next(r["order_item_id"] for r in q if r["order_id"] == order["id"])
    client.post(f"/order-items/{oi}/receive", headers=auth(chef_token))
    client.post(f"/order-items/{oi}/ready", headers=auth(chef_token))

    inbox = client.get("/notifications/inbox", headers=auth(waiter_token)).get_json()
    assert any(n["reference_id"] == oi for n in inbox)

    assert client.post(f"/order-items/{oi}/serve", headers=auth(waiter_token)).status_code == 200

    after = client.get("/notifications/inbox", headers=auth(waiter_token)).get_json()
    assert not any(n["reference_id"] == oi for n in after), \
        "the plate was collected but the waiter is still being told to collect it"
