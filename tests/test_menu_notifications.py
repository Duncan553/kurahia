"""
test_menu_notifications.py — Stage 4: menu catalog changes notify the owner.

Covers: create/disable/enable menu items each queue a QUEUED notification
to the owner with the correct subject and body.
"""
import pytest
from app.extensions import db
from app.models.department import Department
from app.models.notification import Notification


@pytest.fixture
def dept_id(app):
    with app.app_context():
        dept = db.session.query(Department).filter_by(name="General").first()
        return dept.id


def _create_item(client, manager_token, dept_id, name="Test Burger"):
    return client.post("/menu/items", json={
        "name": name, "price": "500", "prep_station": "KITCHEN",
        "department_id": dept_id,
    }, headers={"Authorization": f"Bearer {manager_token}"})


def test_create_menu_item_notifies_owner(app, client, manager_token, dept_id):
    """Creating a menu item queues a notification to the owner."""
    rv = _create_item(client, manager_token, dept_id)
    assert rv.status_code == 201

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.subject.like("Menu catalog change%")
        ).first()
        assert notif is not None
        assert "added" in notif.body
        assert "Test Burger" in notif.body


def test_disable_menu_item_notifies_owner(app, client, manager_token, owner_token, dept_id):
    """Disabling a menu item queues a notification to the owner."""
    item_id = _create_item(client, manager_token, dept_id, name="Disable Test").get_json()["id"]

    with app.app_context():
        # Clear creation notification so we isolate the disable one
        db.session.query(Notification).delete()
        db.session.commit()

    rv = client.post(f"/menu/items/{item_id}/disable",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.subject.like("Menu catalog change%")
        ).first()
        assert notif is not None
        assert "deactivated" in notif.body


def test_enable_menu_item_notifies_owner(app, client, manager_token, dept_id):
    """Re-enabling a menu item queues a notification to the owner."""
    item_id = _create_item(client, manager_token, dept_id, name="Enable Test").get_json()["id"]
    client.post(f"/menu/items/{item_id}/disable",
                headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        db.session.query(Notification).delete()
        db.session.commit()

    rv = client.post(f"/menu/items/{item_id}/enable",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.subject.like("Menu catalog change%")
        ).first()
        assert notif is not None
        assert "re-enabled" in notif.body
