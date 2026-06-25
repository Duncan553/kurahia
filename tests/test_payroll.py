"""
tests/test_payroll.py — Payroll calculation tests.

Coverage:
  - calculate_payroll() service function:
    - HOURLY, DAILY, MONTHLY wage computations
    - Staff meal deductions reduce net pay
    - Net pay never goes below zero
    - Employee with no wage config → gross_pay/net_pay = None
    - No clock events → 0 hours worked
  - GET /finance/payroll?period=YYYY-MM endpoint:
    - Manager+ access, staff blocked
    - Missing/invalid period parameter
    - Returns correct structure
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.clock_event import ClockEvent, ClockEventType
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.department import Department


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def hourly_employee(app):
    """Employee with HOURLY wage @ KSh 200/hr."""
    user = db.session.query(User).filter_by(username="waiter1").first()
    profile = EmployeeProfile(
        user_id=user.id,
        full_name="Hourly Worker",
        phone="+254700100001",
        wage_rate=Decimal("200"),
        wage_period="HOURLY",
    )
    db.session.add(profile)
    db.session.commit()
    return profile


@pytest.fixture
def daily_employee(app):
    """Employee with DAILY wage @ KSh 1500/day."""
    user = db.session.query(User).filter_by(username="kitchen1").first()
    profile = EmployeeProfile(
        user_id=user.id,
        full_name="Daily Worker",
        phone="+254700100002",
        wage_rate=Decimal("1500"),
        wage_period="DAILY",
    )
    db.session.add(profile)
    db.session.commit()
    return profile


@pytest.fixture
def monthly_employee(app):
    """Employee with MONTHLY wage @ KSh 45000/month."""
    user = db.session.query(User).filter_by(username="staff1").first()
    # staff1 has no password so we need to give them one for login; but
    # for payroll we only need the profile, not login.
    profile = EmployeeProfile(
        user_id=user.id,
        full_name="Monthly Worker",
        phone="+254700100003",
        wage_rate=Decimal("45000"),
        wage_period="MONTHLY",
    )
    db.session.add(profile)
    db.session.commit()
    return profile


@pytest.fixture
def no_wage_employee(app):
    """Employee with no wage config (wage_rate=None)."""
    user = db.session.query(User).filter_by(username="manager1").first()
    profile = EmployeeProfile(
        user_id=user.id,
        full_name="No Wage Config",
        phone="+254700100004",
        # wage_rate and wage_period left as None
    )
    db.session.add(profile)
    db.session.commit()
    return profile


def _add_clock_pair(employee_id, clock_in_dt, clock_out_dt):
    """Helper: insert a CLOCK_IN / CLOCK_OUT pair for an employee."""
    cin = ClockEvent(
        employee_id=employee_id,
        event_type=ClockEventType.CLOCK_IN.value,
        occurred_at_utc=clock_in_dt,
        idempotency_key=str(uuid.uuid4()),
    )
    cout = ClockEvent(
        employee_id=employee_id,
        event_type=ClockEventType.CLOCK_OUT.value,
        occurred_at_utc=clock_out_dt,
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add_all([cin, cout])
    db.session.commit()


def _add_staff_meal(user_id, item, qty, timestamp):
    """Helper: insert a STAFF_MEAL stock movement (negative change)."""
    mov = StockMovement(
        item_id=item.id,
        change_amount=-abs(qty),
        reason=MovementReason.STAFF_MEAL.value,
        actor_id=user_id,
        timestamp_utc=timestamp,
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(mov)
    db.session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 1. calculate_payroll() — unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCalculatePayroll:
    def test_hourly_wage(self, app, hourly_employee):
        """8 hours worked @ 200/hr → gross 1600, net 1600 (no deductions)."""
        # Clock in at 08:00, out at 16:00 on Jan 15, 2030
        cin = datetime(2030, 1, 15, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 15, 16, 0, tzinfo=timezone.utc)
        _add_clock_pair(hourly_employee.id, cin, cout)

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        # Find our employee
        row = next(r for r in rows if r["employee_id"] == hourly_employee.id)
        assert row["employee_name"] == "Hourly Worker"
        assert row["wage_period"] == "HOURLY"
        assert Decimal(row["hours_worked"]) == Decimal("8")
        assert Decimal(row["gross_pay"]) == Decimal("1600")
        assert Decimal(row["net_pay"]) == Decimal("1600")

    def test_daily_wage(self, app, daily_employee):
        """8 hours = 1 standard day @ 1500/day → gross 1500."""
        cin = datetime(2030, 1, 10, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 10, 16, 0, tzinfo=timezone.utc)
        _add_clock_pair(daily_employee.id, cin, cout)

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == daily_employee.id)
        assert Decimal(row["gross_pay"]) == Decimal("1500")

    def test_daily_wage_half_day(self, app, daily_employee):
        """4 hours = 0.5 day @ 1500/day → gross 750."""
        cin = datetime(2030, 1, 10, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 10, 12, 0, tzinfo=timezone.utc)
        _add_clock_pair(daily_employee.id, cin, cout)

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == daily_employee.id)
        assert Decimal(row["gross_pay"]) == Decimal("750")

    def test_monthly_wage_flat(self, app, monthly_employee):
        """Monthly wage is flat regardless of hours → gross = wage_rate."""
        cin = datetime(2030, 1, 5, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 5, 16, 0, tzinfo=timezone.utc)
        _add_clock_pair(monthly_employee.id, cin, cout)

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == monthly_employee.id)
        assert Decimal(row["gross_pay"]) == Decimal("45000")

    def test_no_wage_config_returns_none(self, app, no_wage_employee):
        """Employee with no wage_rate → gross_pay and net_pay are None."""
        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == no_wage_employee.id)
        assert row["gross_pay"] is None
        assert row["net_pay"] is None

    def test_no_clock_events_zero_hours(self, app, hourly_employee):
        """No clock events → 0 hours, gross = 0 for hourly."""
        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == hourly_employee.id)
        assert Decimal(row["hours_worked"]) == Decimal("0")
        assert Decimal(row["gross_pay"]) == Decimal("0")

    def test_meal_deduction(self, app, hourly_employee):
        """Staff meal deduction reduces net pay: gross 1600 - 300 meal = 1300."""
        # 8-hour shift
        cin = datetime(2030, 1, 15, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 15, 16, 0, tzinfo=timezone.utc)
        _add_clock_pair(hourly_employee.id, cin, cout)

        # Create an inventory item with known cost
        dept = db.session.query(Department).filter_by(name="General").first()
        food_item = InventoryItem(
            name="Staff Rice",
            unit="kg",
            department_id=dept.id,
            cost_per_unit=Decimal("150"),  # KSh 150/kg
        )
        db.session.add(food_item)
        db.session.commit()

        # Log 2kg of staff rice consumed by this employee
        user = db.session.query(User).filter_by(username="waiter1").first()
        _add_staff_meal(
            user_id=user.id,
            item=food_item,
            qty=Decimal("2"),
            timestamp=datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc),
        )

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == hourly_employee.id)
        assert Decimal(row["gross_pay"]) == Decimal("1600")
        assert Decimal(row["meal_deduction"]) == Decimal("300")  # 2kg * 150
        assert Decimal(row["net_pay"]) == Decimal("1300")

    def test_net_pay_never_negative(self, app, hourly_employee):
        """If deductions exceed gross, net is clamped to 0 (never negative)."""
        # Short shift: 1 hour = gross 200
        cin = datetime(2030, 1, 15, 8, 0, tzinfo=timezone.utc)
        cout = datetime(2030, 1, 15, 9, 0, tzinfo=timezone.utc)
        _add_clock_pair(hourly_employee.id, cin, cout)

        # Expensive meal: 5kg @ 100 = 500 > 200 gross
        dept = db.session.query(Department).filter_by(name="General").first()
        food_item = InventoryItem(
            name="Staff Steak",
            unit="kg",
            department_id=dept.id,
            cost_per_unit=Decimal("100"),
        )
        db.session.add(food_item)
        db.session.commit()

        user = db.session.query(User).filter_by(username="waiter1").first()
        _add_staff_meal(
            user_id=user.id,
            item=food_item,
            qty=Decimal("5"),
            timestamp=datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc),
        )

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == hourly_employee.id)
        assert Decimal(row["gross_pay"]) == Decimal("200")
        assert Decimal(row["net_pay"]) == Decimal("0")  # clamped, not -300

    def test_multiple_shifts_summed(self, app, hourly_employee):
        """Multiple clock pairs in the period sum correctly."""
        # Day 1: 8 hours
        _add_clock_pair(
            hourly_employee.id,
            datetime(2030, 1, 10, 8, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 10, 16, 0, tzinfo=timezone.utc),
        )
        # Day 2: 4 hours
        _add_clock_pair(
            hourly_employee.id,
            datetime(2030, 1, 11, 8, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 11, 12, 0, tzinfo=timezone.utc),
        )

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        row = next(r for r in rows if r["employee_id"] == hourly_employee.id)
        assert Decimal(row["hours_worked"]) == Decimal("12")
        assert Decimal(row["gross_pay"]) == Decimal("2400")  # 12 * 200

    def test_only_active_employees_included(self, app, hourly_employee):
        """Disabled employee excluded from payroll results."""
        hourly_employee.is_active = False
        db.session.commit()

        from app.services.payroll import calculate_payroll
        period_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2030, 2, 1, tzinfo=timezone.utc)
        rows = calculate_payroll(period_start, period_end)

        ids = [r["employee_id"] for r in rows]
        assert hourly_employee.id not in ids


# ══════════════════════════════════════════════════════════════════════════════
# 2. GET /finance/payroll — endpoint integration tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPayrollEndpoint:
    def test_manager_gets_payroll(self, client, manager_token, app):
        """Manager with period param → 200 with correct structure."""
        # Create a profile so there's at least one employee
        user = db.session.query(User).filter_by(username="waiter1").first()
        profile = EmployeeProfile(
            user_id=user.id,
            full_name="Endpoint Worker",
            phone="+254700200001",
            wage_rate=Decimal("100"),
            wage_period="HOURLY",
        )
        db.session.add(profile)
        db.session.commit()

        rv = client.get("/finance/payroll?period=2030-01", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["period"] == "2030-01"
        assert "period_start" in data
        assert "period_end" in data
        assert "employees" in data
        assert isinstance(data["employees"], list)

    def test_missing_period_400(self, client, manager_token):
        """No period param → 400."""
        rv = client.get("/finance/payroll", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "period" in rv.get_json()["error"]

    def test_invalid_period_400(self, client, manager_token):
        """Bad period format → 400."""
        rv = client.get("/finance/payroll?period=not-a-date", headers=auth(manager_token))
        assert rv.status_code == 400

    def test_staff_blocked(self, client, waiter_token):
        """Staff (level 1) blocked → 403."""
        rv = client.get("/finance/payroll?period=2030-01", headers=auth(waiter_token))
        assert rv.status_code == 403
