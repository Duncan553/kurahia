"""
test_auto_close.py — C2: auto-close clean business days, alert on problems.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from app.extensions import db
from app.models.user import User
from app.models.period_close import PeriodClose
from app.models.notification import Notification
from app.models.dispute import Dispute, DisputeStatus, DisputeCategory, DisputePriority
from app.models.employee_profile import EmployeeProfile
from app.services.auto_close import auto_close_day, check_day_health
from app.services.business_day import business_day_bounds


def _bounds():
    return business_day_bounds("2026-06-17")


class TestAutoClose:
    def test_clean_day_auto_closes(self, app):
        """No problems → auto-close + notification."""
        start, end = _bounds()
        closed, problems = auto_close_day(start, end)
        assert closed is True
        assert problems == []

        pc = db.session.query(PeriodClose).filter(
            PeriodClose.period_start_utc >= start,
        ).first()
        assert pc is not None
        assert pc.notes == "Auto-closed (all green)"

    def test_clean_day_sends_notification(self, app):
        """Auto-close sends quiet owner notification."""
        start, end = _bounds()
        auto_close_day(start, end)

        notif = db.session.query(Notification).filter(
            Notification.subject.like("Day closed%"),
        ).first()
        assert notif is not None
        assert "All cash reconciled" in notif.body

    def test_open_dispute_holds(self, app):
        """Open dispute → day NOT auto-closed + alert."""
        owner = db.session.query(User).filter_by(username="owner1").first()
        mgr = db.session.query(User).filter_by(username="manager1").first()
        profile = EmployeeProfile(user_id=mgr.id, full_name="Mgr", phone="+254700000002")
        db.session.add(profile)
        db.session.flush()

        d = Dispute(
            reporter_employee_id=profile.id,
            category=DisputeCategory.OTHER.value,
            status=DisputeStatus.OPEN.value,
            priority=DisputePriority.MEDIUM.value,
            description="Test dispute",
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(d)
        db.session.commit()

        start, end = _bounds()
        closed, problems = auto_close_day(start, end)
        assert closed is False
        assert any("dispute" in p for p in problems)

        alert = db.session.query(Notification).filter(
            Notification.subject.like("%not auto-closed%"),
        ).first()
        assert alert is not None

    def test_already_closed_returns_true(self, app):
        """If day already closed, returns (True, [])."""
        start, end = _bounds()
        auto_close_day(start, end)
        closed, problems = auto_close_day(start, end)
        assert closed is True
        assert problems == []

    def test_health_check_no_problems_on_clean(self, app):
        """check_day_health returns empty list when everything is clean."""
        start, end = _bounds()
        problems = check_day_health(start, end)
        assert problems == []

    def test_cli_command(self, app):
        """flask system auto-close runs without error."""
        runner = app.test_cli_runner()
        result = runner.invoke(args=["system_cli", "auto-close"])
        assert "Auto-close:" in result.output
