"""
test_business_day.py — C1: business day boundaries with configurable cutoff.
"""
from datetime import datetime, timezone
import pytest
from app.extensions import db
from app.models.system_setting import SystemSetting
from app.services.business_day import business_day_for, business_day_bounds, EAT


def _set_eat(app):
    """Switch test env to EAT timezone + hour 6 for EAT-specific tests."""
    with app.app_context():
        tz_row = db.session.get(SystemSetting, "business_day_timezone")
        if tz_row:
            tz_row.value = "Africa/Nairobi"
        else:
            db.session.add(SystemSetting(key="business_day_timezone", value="Africa/Nairobi"))
        hr_row = db.session.get(SystemSetting, "business_day_start_hour")
        if hr_row:
            hr_row.value = "6"
        else:
            db.session.add(SystemSetting(key="business_day_start_hour", value="6"))
        db.session.commit()


class TestBusinessDay:
    def test_5am_eat_is_previous_day(self, app):
        """5:00 AM EAT (before 6:00 cutoff) → previous business day."""
        _set_eat(app)
        ts = datetime(2026, 6, 17, 2, 0, tzinfo=timezone.utc)  # 5:00 AM EAT
        bd = business_day_for(ts)
        assert bd.day == 16

    def test_7am_is_current_day(self, app):
        """7:00 AM UTC (after midnight cutoff in UTC mode) → current day."""
        ts = datetime(2026, 6, 17, 4, 0, tzinfo=timezone.utc)
        bd = business_day_for(ts)
        assert bd.day == 17

    def test_11pm_is_current_day(self, app):
        """11:00 PM UTC → current business day."""
        ts = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
        bd = business_day_for(ts)
        assert bd.day == 17

    def test_configurable_cutoff_with_eat(self, app):
        """Owner changes start hour to 4 in EAT → 5:00 AM EAT is now current day."""
        _set_eat(app)
        with app.app_context():
            hr = db.session.get(SystemSetting, "business_day_start_hour")
            hr.value = "4"
            db.session.commit()

            ts = datetime(2026, 6, 17, 2, 0, tzinfo=timezone.utc)  # 5:00 AM EAT
            bd = business_day_for(ts)
            assert bd.day == 17

    def test_bounds_eat_timezone(self, app):
        """Bounds in EAT mode: cutoff 6 → start = 3:00 UTC (6:00 EAT)."""
        _set_eat(app)
        start, end = business_day_bounds("2026-06-17")
        assert start.hour == 3
        assert (end - start).total_seconds() == 86400

    def test_bounds_utc_mode(self, app):
        """Bounds in UTC mode (test default): cutoff 0 → start = midnight UTC."""
        start, end = business_day_bounds("2026-06-17")
        assert start.hour == 0
        assert (end - start).total_seconds() == 86400

    def test_settings_endpoint_get(self, app, client, owner_token):
        rv = client.get("/admin/settings",
                        headers={"Authorization": f"Bearer {owner_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert "business_day_start_hour" in data

    def test_settings_endpoint_patch(self, app, client, owner_token):
        rv = client.patch("/admin/settings",
                          json={"business_day_start_hour": 5},
                          headers={"Authorization": f"Bearer {owner_token}"})
        assert rv.status_code == 200
        assert "business_day_start_hour" in rv.get_json()["updated"]

    def test_settings_rejects_invalid(self, app, client, owner_token):
        rv = client.patch("/admin/settings",
                          json={"business_day_start_hour": 25},
                          headers={"Authorization": f"Bearer {owner_token}"})
        assert rv.status_code == 400

    def test_parse_date_bounds_uses_business_day(self, app):
        """Chokepoint uses business day bounds (UTC mode in tests = midnight)."""
        from app.services.finance import parse_date_bounds
        start, end = parse_date_bounds("2026-06-17")
        assert start.hour == 0
        assert (end - start).total_seconds() == 86400
