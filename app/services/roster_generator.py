"""
services/roster_generator.py — turn each person's weekly pattern into shifts.

WHY THIS EXISTS. Rostering by hand does not survive a real week. Fourteen staff
across six days is eighty-odd rows somebody types every Sunday — so it gets
typed once, enthusiastically, and never again. Then the attendance board lists
nobody, absence can never be recorded (you cannot fail to turn up for a shift
you were never given), and payroll has no hours to measure. The feature does not
break loudly; it just quietly stops being true.

Every scheduling tool solves this the same way: a recurring template plus a
copy-forward. This is that, reduced to the smallest version that still gives a
board a manager can trust.

  the pattern lives on the person   roster_days / roster_start / roster_end
  the shifts are generated from it  one call, a week at a time
  exceptions stay manual            POST /hr/shifts still works exactly as before

WHAT IT WILL NOT DO:
  - roster somebody with no pattern (casuals stay manual, on purpose)
  - roster anyone on approved leave for that day
  - create a second shift where one already exists — running it twice is safe,
    which matters because it is the sort of thing somebody will click twice
"""
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.employee_profile import EmployeeProfile
from app.models.shift import Shift, ShiftStatus
from app.services.hr import has_approved_leave

EAT = ZoneInfo("Africa/Nairobi")
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def parse_pattern(profile) -> tuple[set[str], time, time] | None:
    """(days, start, end) or None when this person is not on a pattern."""
    if not (profile.roster_days and profile.roster_start and profile.roster_end):
        return None
    days = {d.strip().upper()[:3] for d in profile.roster_days.split(",") if d.strip()}
    if not days or not days.issubset(set(DAYS)):
        return None
    try:
        sh, sm = (int(x) for x in profile.roster_start.split(":"))
        eh, em = (int(x) for x in profile.roster_end.split(":"))
        return days, time(sh, sm), time(eh, em)
    except (ValueError, TypeError):
        return None


def generate_week(week_start, actor_id: str, dry_run: bool = False) -> dict:
    """Create shifts for every patterned employee across the 7 days from
    `week_start` (a date). Returns a summary; safe to run repeatedly.

    Times are written in UTC but READ as Africa/Nairobi, because that is how a
    person says them. "16:00" means four in the afternoon in Juja, not in UTC —
    storing the literal hour would put the bar shift three hours out.
    """
    made, skipped_leave, already, no_pattern = [], 0, 0, 0

    for profile in db.session.query(EmployeeProfile).filter_by(is_active=True).all():
        pattern = parse_pattern(profile)
        if not pattern:
            no_pattern += 1
            continue
        days, start_t, end_t = pattern

        for offset in range(7):
            day = week_start + timedelta(days=offset)
            if DAYS[day.weekday()] not in days:
                continue
            if has_approved_leave(profile.id, day):
                skipped_leave += 1
                continue

            start = datetime.combine(day, start_t, tzinfo=EAT).astimezone(timezone.utc)
            end = datetime.combine(day, end_t, tzinfo=EAT).astimezone(timezone.utc)
            # An end BEFORE the start means the shift runs past midnight — the
            # bar closing at 00:00 works until the next calendar day, not for
            # minus eight hours.
            if end <= start:
                end += timedelta(days=1)

            # Stable key: the same person, same day, same pattern is the same
            # shift however many times this is run.
            key = f"roster-{profile.id}-{day.isoformat()}"
            if db.session.query(Shift).filter_by(idempotency_key=key).first():
                already += 1
                continue
            if not dry_run:
                db.session.add(Shift(
                    employee_id=profile.id,
                    scheduled_start_utc=start.replace(tzinfo=None),
                    scheduled_end_utc=end.replace(tzinfo=None),
                    department_id=profile.user.department_id if profile.user else None,
                    status=ShiftStatus.SCHEDULED.value,
                    created_by_id=actor_id,
                    idempotency_key=key,
                ))
            made.append((profile.full_name, day.isoformat()))

    if not dry_run:
        db.session.commit()
    return {
        "week_start": week_start.isoformat(),
        "created": len(made),
        "already_rostered": already,
        "skipped_on_leave": skipped_leave,
        "no_pattern": no_pattern,
        "shifts": made,
    }
