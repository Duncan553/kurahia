"""
Things nobody closed, raised to somebody who can.

Neither class is auto-resolved: closing a tab records a payment nobody made,
and approving leave is a manager's decision. They get a voice, not a verdict.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.tab import Tab, TabStatus
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import Notification
from app.services.stale_sweep import sweep, stale_tabs, STALE_TAB_HOURS, LEAVE_NUDGE_DAYS


def _tab(hours_ago, ref="Terrace 9"):
    """opened_by_id is NOT NULL — a tab is always somebody's."""
    from app.models.user import User
    who = db.session.query(User).filter_by(username="waiter1").one()
    t = Tab(reference=ref, tab_type="WALK_IN", status=TabStatus.OPEN.value,
            opened_by_id=who.id,
            opened_at_utc=datetime.now(timezone.utc) - timedelta(hours=hours_ago))
    db.session.add(t); db.session.commit()
    return t


def _leave(days_ago, profile_id):
    lr = LeaveRequest(employee_id=profile_id, leave_type="ANNUAL",
                      start_date=(datetime.now(timezone.utc) + timedelta(days=10)).date(),
                      end_date=(datetime.now(timezone.utc) + timedelta(days=12)).date(),
                      status=LeaveStatus.PENDING.value,
                      created_at_utc=datetime.now(timezone.utc) - timedelta(days=days_ago),
                      idempotency_key=str(uuid.uuid4()))
    db.session.add(lr); db.session.commit()
    return lr


class TestStaleSweep:
    def test_a_fresh_tab_is_not_stale(self, app):
        with app.app_context():
            _tab(hours_ago=2)
            assert all(t.reference != "Terrace 9" for t in stale_tabs())

    def test_a_tab_open_past_the_trading_day_is_raised(self, app):
        with app.app_context():
            _tab(hours_ago=STALE_TAB_HOURS + 5)
            assert any(t.reference == "Terrace 9" for t in stale_tabs())
            r = sweep()
            assert r["tab_notices"] > 0

    def test_the_tab_is_not_closed_for_them(self, app):
        """Closing it would record a payment nobody made."""
        with app.app_context():
            t = _tab(hours_ago=STALE_TAB_HOURS + 5)
            sweep()
            db.session.refresh(t)
            assert t.status == TabStatus.OPEN.value

    def test_recent_leave_is_left_alone(self, app, waiter_profile):
        with app.app_context():
            _leave(days_ago=1, profile_id=waiter_profile.id)
            assert sweep()["leave_notices"] == 0

    def test_leave_waiting_too_long_is_nudged(self, app, waiter_profile):
        with app.app_context():
            _leave(days_ago=LEAVE_NUDGE_DAYS + 1, profile_id=waiter_profile.id)
            assert sweep()["leave_notices"] > 0

    def test_leave_is_not_decided_for_them(self, app, waiter_profile):
        with app.app_context():
            lr = _leave(days_ago=LEAVE_NUDGE_DAYS + 1, profile_id=waiter_profile.id)
            sweep()
            db.session.refresh(lr)
            assert lr.status == LeaveStatus.PENDING.value

    def test_the_same_day_does_not_notify_twice(self, app):
        """A reminder that fires once ever is not a reminder — but it must not
        fire twice in one run, or if the cron runs twice."""
        with app.app_context():
            _tab(hours_ago=STALE_TAB_HOURS + 5)
            first = sweep()["tab_notices"]
            second = sweep()["tab_notices"]
            assert first > 0 and second == 0
