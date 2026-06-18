"""
business_day.py — configurable business-day boundaries.

business_day_start_hour is stored in SystemSetting (default 6 = 6:00 AM Africa/Nairobi).
A timestamp BEFORE the cutoff belongs to the PREVIOUS business day.

Example with cutoff 6:00 AM EAT (UTC+3):
  5:30 AM EAT  → previous business day
  6:15 AM EAT  → current business day
  11:00 PM EAT → current business day
"""
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

EAT = ZoneInfo("Africa/Nairobi")
DEFAULT_START_HOUR = 6


def _get_tz() -> tzinfo:
    try:
        from app.extensions import db
        from app.models.system_setting import SystemSetting
        row = db.session.get(SystemSetting, "business_day_timezone")
        if row and row.value.upper() == "UTC":
            return timezone.utc
    except Exception:
        pass
    return EAT


def _get_start_hour() -> int:
    try:
        from app.extensions import db
        from app.models.system_setting import SystemSetting
        row = db.session.get(SystemSetting, "business_day_start_hour")
        if row:
            return int(row.value)
    except Exception:
        pass
    return DEFAULT_START_HOUR


def business_day_for(ts: datetime) -> datetime:
    """Return the business-day date that `ts` belongs to (in configured tz)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    tz = _get_tz()
    local_time = ts.astimezone(tz)
    start_hour = _get_start_hour()
    if local_time.hour < start_hour:
        local_time -= timedelta(days=1)
    return local_time.replace(hour=0, minute=0, second=0, microsecond=0)


def business_day_bounds(date_str: str) -> tuple[datetime, datetime]:
    """'YYYY-MM-DD' → (start_utc, end_utc) using business-day cutoff.

    Start = date at business_day_start_hour EAT, converted to UTC.
    End   = start + 24h.
    """
    from datetime import datetime as dt
    d = dt.strptime(date_str, "%Y-%m-%d")
    tz = _get_tz()
    start_hour = _get_start_hour()
    start_local = d.replace(hour=start_hour, minute=0, second=0, microsecond=0, tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    return start_utc, start_utc + timedelta(hours=24)


def business_day_bounds_today() -> tuple[datetime, datetime]:
    """Bounds for the current business day."""
    now = datetime.now(timezone.utc)
    bd = business_day_for(now)
    return business_day_bounds(bd.strftime("%Y-%m-%d"))
