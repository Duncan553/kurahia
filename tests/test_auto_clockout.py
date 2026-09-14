"""
The system closes the shift, not the worker.

597 clock-ins against 67 clock-outs meant every hours figure in the resort read
0.0 and payroll could not run. People clock in because the tablet asks them to;
nobody clocks out, because at the end of a shift they are leaving. So the
roster closes it for them — the manager has already said which shift each
person works.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.clock_event import ClockEvent, ClockEventType
from app.models.shift import Shift, ShiftStatus
from app.services.auto_clockout import auto_clock_out, MAX_SHIFT_HOURS
from app.services.hr import compute_hours_worked


def _window():
    start = datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc)   # 06:00 EAT
    return start, start + timedelta(days=1)


def _make_shift(emp_id, start, end):
    """Shifts carry created_by_id NOT NULL — a roster entry is somebody's
    decision, so it always has a name on it."""
    from app.models.user import User
    mgr = db.session.query(User).filter_by(username="manager1").one()
    sh = Shift(employee_id=emp_id, status=ShiftStatus.SCHEDULED.value,
               scheduled_start_utc=start, scheduled_end_utc=end,
               created_by_id=mgr.id, idempotency_key=str(uuid.uuid4()))
    db.session.add(sh); db.session.commit()
    return sh


def _clock_in(emp_id, at, shift_id=None):
    ev = ClockEvent(employee_id=emp_id, event_type=ClockEventType.CLOCK_IN.value,
                    occurred_at_utc=at, shift_id=shift_id,
                    idempotency_key=str(uuid.uuid4()))
    db.session.add(ev); db.session.commit()
    return ev


@pytest.fixture
def emp(app, waiter_profile):
    return waiter_profile.id


class TestAutoClockOut:
    def test_rostered_shift_closes_at_its_stated_end(self, app, emp):
        """The roster is the contract."""
        start, end = _window()
        with app.app_context():
            shift = _make_shift(emp, start + timedelta(hours=2),
                                start + timedelta(hours=10))
            _clock_in(emp, start + timedelta(hours=2), shift.id)

            closed, hours = auto_clock_out(start, end)
            assert closed == 1
            out = (db.session.query(ClockEvent)
                   .filter_by(employee_id=emp, event_type=ClockEventType.CLOCK_OUT.value)
                   .one())
            assert out.occurred_at_utc.replace(tzinfo=timezone.utc) == start + timedelta(hours=10)
            assert out.is_manual_override is True

    def test_night_shift_is_not_clamped_to_the_day_cutoff(self, app, emp):
        """22:00 -> 06:00 crosses the business day. Clamping would shave hours
        off every night worker, invisibly."""
        start, end = _window()
        with app.app_context():
            in_at  = start + timedelta(hours=16)          # 22:00 EAT
            out_at = start + timedelta(hours=24)          # 06:00 EAT next day
            shift = _make_shift(emp, in_at, out_at)
            _clock_in(emp, in_at, shift.id)

            auto_clock_out(start, end)
            ev = (db.session.query(ClockEvent)
                  .filter_by(employee_id=emp, event_type=ClockEventType.CLOCK_OUT.value)
                  .one())
            assert ev.occurred_at_utc.replace(tzinfo=timezone.utc) == out_at

    def test_unrostered_falls_back_to_the_stingy_cap(self, app, emp):
        """No roster entry means the system is guessing, so it guesses low."""
        start, end = _window()
        with app.app_context():
            _clock_in(emp, start + timedelta(hours=1))
            auto_clock_out(start, end)
            ev = (db.session.query(ClockEvent)
                  .filter_by(employee_id=emp, event_type=ClockEventType.CLOCK_OUT.value)
                  .one())
            expected = start + timedelta(hours=1 + MAX_SHIFT_HOURS)
            assert ev.occurred_at_utc.replace(tzinfo=timezone.utc) == expected

    def test_an_existing_clock_out_is_left_alone(self, app, emp):
        start, end = _window()
        with app.app_context():
            _clock_in(emp, start + timedelta(hours=1))
            db.session.add(ClockEvent(
                employee_id=emp, event_type=ClockEventType.CLOCK_OUT.value,
                occurred_at_utc=start + timedelta(hours=5),
                idempotency_key=str(uuid.uuid4())))
            db.session.commit()
            closed, _ = auto_clock_out(start, end)
            assert closed == 0

    def test_rerunning_the_sweep_does_not_double_close(self, app, emp):
        """Idempotency key is per open clock-in, so the cron can run twice."""
        start, end = _window()
        with app.app_context():
            _clock_in(emp, start + timedelta(hours=1))
            assert auto_clock_out(start, end)[0] == 1
            assert auto_clock_out(start, end)[0] == 0

    def test_hours_stop_being_zero(self, app, emp):
        """The whole point: payroll can read a number afterwards."""
        start, end = _window()
        with app.app_context():
            _clock_in(emp, start + timedelta(hours=2))
            assert compute_hours_worked(emp, start, end) == 0
            auto_clock_out(start, end)
            assert compute_hours_worked(emp, start, end) > 0
