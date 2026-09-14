"""
Who may write stock off, and for which department.

Spoilage and sent-back were manager-only. The person who SEES spoiled stock is
the station lead, and a loss that cannot be recorded does not stop existing —
it resurfaces as unexplained variance, which the judge reads as possible theft.
So the gate moved from rank alone to rank + department, the same shape the
stock count already uses.

These tests pin both halves: the lead can write off their own department, and
cannot reach another one.
"""
import uuid
import pytest

from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement


def _make_item(name, dept_name, qty="20"):
    """An active stock line in a named department, with stock on the shelf.

    Stock is a SUM of movements (invariant 2), never a stored field, so the
    opening balance has to be written as a PURCHASE rather than set."""
    from app.models.department import Department
    from app.models.stock_movement import MovementReason
    from decimal import Decimal

    from app.models.user import User

    dept = db.session.query(Department).filter_by(name=dept_name).one()
    item = InventoryItem(name=name, unit="kg", department_id=dept.id)
    db.session.add(item)
    db.session.flush()
    # actor_id is NOT NULL on purpose — no movement is anonymous, including the
    # opening balance. The manager stands in for the delivery that stocked it.
    stocker = db.session.query(User).filter_by(username="manager1").one()
    db.session.add(StockMovement(
        item_id=item.id, change_amount=Decimal(qty),
        reason=MovementReason.PURCHASE.value,
        actor_id=stocker.id,
        idempotency_key=str(uuid.uuid4()),
    ))
    db.session.commit()
    return item.id


@pytest.fixture
def kitchen_item(app):
    return _make_item("Fresh Milk", "Kitchen")


@pytest.fixture
def bar_item(app):
    return _make_item("Lime Cordial", "Bar")


def _stock(item_id):
    rows = db.session.query(StockMovement).filter_by(item_id=item_id).all()
    return sum(r.change_amount for r in rows)


class TestWriteOffScope:
    def test_station_lead_writes_off_own_department(self, client, app, chef_token, kitchen_item):
        """The chef sees the spoiled milk, so the chef records it."""
        with app.app_context():
            before = _stock(kitchen_item)
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": kitchen_item, "quantity": "2",
                               "notes": "turned overnight",
                               "idempotency_key": str(uuid.uuid4())},
                         headers={"Authorization": f"Bearer {chef_token}"})
        assert rv.status_code == 201, rv.get_json()
        with app.app_context():
            assert _stock(kitchen_item) == before - 2

    def test_station_lead_refused_another_department(self, client, chef_token, bar_item):
        """The kitchen does not write off the bar's stock."""
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": bar_item, "quantity": "1",
                               "idempotency_key": str(uuid.uuid4())},
                         headers={"Authorization": f"Bearer {chef_token}"})
        assert rv.status_code == 403
        # Invariant 5: the refusal says what to do about it, in plain English.
        assert "your own department" in rv.get_json()["error"].lower()

    def test_manager_writes_off_any_department(self, client, manager_token, bar_item):
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": bar_item, "quantity": "1",
                               "idempotency_key": str(uuid.uuid4())},
                         headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201, rv.get_json()

    def test_ordinary_staff_still_refused(self, client, waiter_token, kitchen_item):
        """Below lead, a write-off is somebody else's signature."""
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": kitchen_item, "quantity": "1",
                               "idempotency_key": str(uuid.uuid4())},
                         headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 403

    def test_write_off_lands_in_the_audit_log(self, client, app, chef_token, kitchen_item):
        """The whole reason this can be delegated is that it is not anonymous."""
        from app.models.audit_log import AuditLog
        with app.app_context():
            before = db.session.query(AuditLog).filter_by(action="inventory.spoilage").count()
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": kitchen_item, "quantity": "1",
                               "idempotency_key": str(uuid.uuid4())},
                         headers={"Authorization": f"Bearer {chef_token}"})
        assert rv.status_code == 201
        with app.app_context():
            after = db.session.query(AuditLog).filter_by(action="inventory.spoilage").count()
            assert after == before + 1
