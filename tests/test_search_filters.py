"""
test_search_filters.py — Stage 5.2: ?q= search on all list endpoints.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.department import Department
from app.models.purchase_request import PurchaseRequest, RequestStatus
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.bookable_resource import BookableResource, ResourceType


class TestMenuSearch:
    def test_q_filters_by_name(self, app, client, manager_token):
        rv = client.get("/menu/items?q=tilapia",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        items = rv.get_json()
        assert len(items) == 1
        assert "Tilapia" in items[0]["name"]

    def test_q_case_insensitive(self, app, client, manager_token):
        rv = client.get("/menu/items?q=TUSKER",
                        headers={"Authorization": f"Bearer {manager_token}"})
        items = rv.get_json()
        assert len(items) == 1
        assert "Tusker" in items[0]["name"]

    def test_empty_q_returns_all(self, app, client, manager_token):
        all_rv = client.get("/menu/items",
                            headers={"Authorization": f"Bearer {manager_token}"})
        q_rv = client.get("/menu/items?q=",
                          headers={"Authorization": f"Bearer {manager_token}"})
        assert len(all_rv.get_json()) == len(q_rv.get_json())


class TestInventorySearch:
    def test_q_filters_inventory(self, app, client, owner_token):
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        db.session.add(InventoryItem(name="Searchable Paprika", unit="g",
                                     department_id=dept.id, reorder_level=Decimal("1")))
        db.session.commit()

        rv = client.get("/inventory/items?q=paprika",
                        headers={"Authorization": f"Bearer {owner_token}"})
        items = rv.get_json()
        assert any("Paprika" in i["name"] for i in items)

    def test_q_no_match(self, app, client, owner_token):
        rv = client.get("/inventory/items?q=xyznonexistent",
                        headers={"Authorization": f"Bearer {owner_token}"})
        assert rv.get_json() == []


class TestUserSearch:
    def test_q_filters_username(self, app, client, owner_token):
        rv = client.get("/auth/users?q=manager",
                        headers={"Authorization": f"Bearer {owner_token}"})
        users = rv.get_json()
        assert len(users) >= 1
        assert all("manager" in u["username"] for u in users)


class TestBookingSearch:
    def test_q_filters_guest_name(self, app, client, manager_token):
        mgr = db.session.query(User).filter_by(username="manager1").first()
        res = BookableResource(name="Test Villa", resource_type=ResourceType.VILLA.value,
                               capacity=4, base_price=Decimal("5000"))
        db.session.add(res)
        db.session.flush()
        b = Booking(
            resource_id=res.id, guest_name="John Kamau", guest_phone="+254700000099",
            number_of_guests=2, status=BookingStatus.CONFIRMED.value,
            check_in_planned_utc=datetime(2026, 7, 1, tzinfo=timezone.utc),
            check_out_planned_utc=datetime(2026, 7, 3, tzinfo=timezone.utc),
            base_total=Decimal("10000"), idempotency_key=str(uuid.uuid4()),
            created_by_id=mgr.id,
        )
        db.session.add(b)
        db.session.commit()

        rv = client.get("/bookings?q=kamau",
                        headers={"Authorization": f"Bearer {manager_token}"})
        bookings = rv.get_json()
        assert len(bookings) >= 1
        assert any("Kamau" in b["guest_name"] for b in bookings)


class TestPurchaseRequestSearch:
    def test_q_filters_by_item_name(self, app, client, manager_token):
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        item = InventoryItem(name="Unique Saffron", unit="g",
                             department_id=dept.id, reorder_level=Decimal("1"))
        db.session.add(item)
        db.session.flush()
        mgr = db.session.query(User).filter_by(username="manager1").first()
        pr = PurchaseRequest(
            item_id=item.id, quantity=Decimal("5"),
            status=RequestStatus.PENDING.value, requested_by_id=mgr.id,
        )
        db.session.add(pr)
        db.session.commit()

        rv = client.get("/inventory/purchase-requests?q=saffron",
                        headers={"Authorization": f"Bearer {manager_token}"})
        reqs = rv.get_json()
        assert len(reqs) >= 1
        assert any("Saffron" in r["item_name"] for r in reqs)
