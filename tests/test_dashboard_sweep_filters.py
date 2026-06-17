"""
test_dashboard_sweep_filters.py — Shared filters unlocking dept hubs.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from app.extensions import db
from app.models.user import User
from app.models.department import Department
from app.models.shift import Shift, ShiftStatus
from app.models.employee_profile import EmployeeProfile
from app.models.equipment import Equipment


class TestAttendanceDeptFilter:
    def test_department_id_filters_shifts(self, app, client, manager_token):
        """?department_id= returns only shifts for that department."""
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        bar = db.session.query(Department).filter_by(name="Bar").first()

        mgr = db.session.query(User).filter_by(username="manager1").first()
        p1 = EmployeeProfile(user_id=mgr.id, full_name="Chef A", phone="+254700000010")
        db.session.add(p1)
        db.session.flush()

        from app.services.business_day import business_day_bounds_today
        day_start, day_end = business_day_bounds_today()
        mid = day_start + timedelta(hours=4)

        s1 = Shift(employee_id=p1.id, department_id=kitchen.id,
                    scheduled_start_utc=mid, scheduled_end_utc=mid + timedelta(hours=8),
                    status=ShiftStatus.SCHEDULED.value, created_by_id=mgr.id,
                    idempotency_key=str(uuid.uuid4()))
        s2 = Shift(employee_id=p1.id, department_id=bar.id,
                    scheduled_start_utc=mid, scheduled_end_utc=mid + timedelta(hours=8),
                    status=ShiftStatus.SCHEDULED.value, created_by_id=mgr.id,
                    idempotency_key=str(uuid.uuid4()))
        db.session.add_all([s1, s2])
        db.session.commit()

        rv = client.get(f"/hr/attendance/today?department_id={kitchen.id}",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data) == 1

    def test_no_filter_returns_all(self, app, client, manager_token):
        """No ?department_id= returns all scheduled shifts."""
        rv = client.get("/hr/attendance/today",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200


class TestEquipmentFilters:
    def _make_equipment(self):
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        mgr = db.session.query(User).filter_by(username="manager1").first()
        e = Equipment(name="Test Oven", equipment_type="oven",
                      department_id=kitchen.id, created_by_id=mgr.id)
        db.session.add(e)
        db.session.commit()
        return e, kitchen

    def test_department_filter(self, app, client, manager_token):
        eq, kitchen = self._make_equipment()
        rv = client.get(f"/equipment?department_id={kitchen.id}",
                        headers={"Authorization": f"Bearer {manager_token}"})
        items = rv.get_json()
        assert all(i.get("department_id") == kitchen.id for i in items)

    def test_equipment_type_filter(self, app, client, manager_token):
        self._make_equipment()
        rv = client.get("/equipment?equipment_type=oven",
                        headers={"Authorization": f"Bearer {manager_token}"})
        items = rv.get_json()
        assert len(items) >= 1
        assert all("oven" in i["equipment_type"].lower() for i in items)


class TestOverviewAccessLevel:
    def test_manager_can_access_overview(self, app, client, manager_token):
        rv = client.get("/dashboard/overview",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200

    def test_owner_can_access_overview(self, app, client, owner_token):
        rv = client.get("/dashboard/overview",
                        headers={"Authorization": f"Bearer {owner_token}"})
        assert rv.status_code == 200

    def test_staff_blocked_from_overview(self, app, client, waiter_token):
        rv = client.get("/dashboard/overview",
                        headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 403
