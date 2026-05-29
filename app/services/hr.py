"""
services/hr.py — HR calculation helpers.

WiFi validation, shift matching, attendance logic, performance scoring,
payroll draft math. All derived from immutable records.
"""
import ipaddress
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import func
from app.extensions import db

LATE_GRACE_MINUTES    = 15
SHIFT_WINDOW_HOURS    = 2    # ±hours for shift auto-link
SHORTFALL_PENALTY_PER = 10   # points deducted per cash shortfall
SCORE_WEIGHTS = {
    "punctuality":  Decimal("0.30"),
    "attendance":   Decimal("0.40"),
    "cash_health":  Decimal("0.15"),
    "void_health":  Decimal("0.15"),
}


# ── WiFi validation ───────────────────────────────────────────────────────────

def is_ip_allowed(remote_addr: str | None) -> bool:
    """True if remote_addr falls within any active WiFiAllowList CIDR."""
    if not remote_addr:
        return False
    from app.models.wifi_allow_list import WiFiAllowList
    entries = db.session.query(WiFiAllowList).filter_by(is_active=True).all()
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    for entry in entries:
        try:
            network = ipaddress.ip_network(entry.ip_cidr, strict=False)
            if ip in network:
                return True
        except ValueError:
            continue
    return False


# ── Shift matching ────────────────────────────────────────────────────────────

def find_matching_shift(employee_id: str, occurred_at: datetime):
    """
    Find the SCHEDULED shift closest to occurred_at within ±SHIFT_WINDOW_HOURS.
    Returns the Shift object or None (no-shift event).
    """
    from app.models.shift import Shift, ShiftStatus
    window = timedelta(hours=SHIFT_WINDOW_HOURS)

    # Normalize to naive UTC for SQLite compatibility
    occ = occurred_at
    if occ.tzinfo is not None:
        occ = occ.replace(tzinfo=None)

    candidates = db.session.query(Shift).filter(
        Shift.employee_id == employee_id,
        Shift.status == ShiftStatus.SCHEDULED.value,
    ).all()

    # Filter in Python to avoid SQLite timezone issues
    matched = []
    for s in candidates:
        start = s.scheduled_start_utc
        end   = s.scheduled_end_utc
        if start and start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        if end and end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        if start is None or end is None:
            continue
        # Check if event falls within ±window of shift window
        if (start - window) <= occ <= (end + window):
            matched.append((s, abs((start - occ).total_seconds())))

    if not matched:
        return None
    return min(matched, key=lambda x: x[1])[0]


def is_late(occurred_at: datetime, shift) -> bool:
    """True if CLOCK_IN happened more than LATE_GRACE_MINUTES after shift start."""
    start = shift.scheduled_start_utc
    if start and start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    occ = occurred_at
    if occ.tzinfo is not None:
        occ = occ.replace(tzinfo=None)
    return occ > start + timedelta(minutes=LATE_GRACE_MINUTES)


def is_early_out(occurred_at: datetime, shift) -> bool:
    """True if CLOCK_OUT happened before shift end."""
    end = shift.scheduled_end_utc
    if end and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    occ = occurred_at
    if occ.tzinfo is not None:
        occ = occ.replace(tzinfo=None)
    return occ < end


# ── Attendance helpers ────────────────────────────────────────────────────────

def has_approved_leave(employee_id: str, check_date: date) -> bool:
    """True if the employee has an APPROVED leave request covering check_date."""
    from app.models.leave_request import LeaveRequest, LeaveStatus
    leave = db.session.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == LeaveStatus.APPROVED.value,
        LeaveRequest.start_date <= check_date,
        LeaveRequest.end_date   >= check_date,
    ).first()
    return leave is not None


def has_absence_notice(employee_id: str, shift_id: str | None,
                       check_date: date) -> bool:
    """True if there's an AbsenceNotice for this employee on this date/shift."""
    from app.models.absence_notice import AbsenceNotice
    query = db.session.query(AbsenceNotice).filter(
        AbsenceNotice.employee_id == employee_id,
    )
    if shift_id:
        query = query.filter(AbsenceNotice.expected_shift_id == shift_id)
    else:
        # Match by date of sent_at
        day_start = datetime(check_date.year, check_date.month, check_date.day)
        day_end   = day_start + timedelta(days=1)
        query = query.filter(
            AbsenceNotice.sent_at_utc >= day_start,
            AbsenceNotice.sent_at_utc < day_end,
        )
    return query.first() is not None


# ── Hours worked ──────────────────────────────────────────────────────────────

def compute_hours_worked(employee_id: str,
                         period_start: datetime,
                         period_end: datetime) -> Decimal:
    """
    Pair CLOCK_IN / CLOCK_OUT events chronologically; sum durations in hours.
    Unpaired CLOCK_IN (open shift) contributes 0 hours.
    """
    from app.models.clock_event import ClockEvent, ClockEventType

    events = db.session.query(ClockEvent).filter(
        ClockEvent.employee_id == employee_id,
        ClockEvent.occurred_at_utc >= period_start,
        ClockEvent.occurred_at_utc < period_end,
    ).order_by(ClockEvent.occurred_at_utc).all()

    total_seconds = 0
    last_in = None
    for ev in events:
        t = ev.occurred_at_utc
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if ev.event_type == ClockEventType.CLOCK_IN.value:
            last_in = t
        elif ev.event_type == ClockEventType.CLOCK_OUT.value and last_in is not None:
            total_seconds += (t - last_in).total_seconds()
            last_in = None

    return Decimal(str(round(total_seconds / 3600, 4)))


# ── Guest-rating socket (activated in Chunk 9) ───────────────────────────────

def _get_guest_rating(employee_id: str,
                      period_start: datetime, period_end: datetime) -> str | None:
    """
    Average GuestFeedback score (1-5) for this employee in the period.
    Returns None if no feedback exists — the composite score stays unaffected.
    """
    from app.models.guest_feedback import GuestFeedback
    result = db.session.query(func.avg(GuestFeedback.score)).filter(
        GuestFeedback.served_by_employee_id == employee_id,
        GuestFeedback.created_at_utc >= period_start,
        GuestFeedback.created_at_utc < period_end,
    ).scalar()
    if result is None:
        return None
    return str(round(Decimal(str(result)), 2))


# ── Performance scoring ───────────────────────────────────────────────────────

def compute_performance(employee_id: str,
                        period_start: datetime,
                        period_end: datetime) -> dict:
    """
    Derives all performance metrics. Returns a dict with scores + breakdown.
    Guest rating: null (socket ready for Chunk 8 Feedback model).
    """
    from app.models.shift import Shift, ShiftStatus
    from app.models.clock_event import ClockEvent, ClockEventType
    from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus
    from app.models.leave_request import LeaveRequest, LeaveStatus
    from app.services.finance import get_void_rates

    # Shifts scheduled in the period
    shifts = db.session.query(Shift).filter(
        Shift.employee_id == employee_id,
        Shift.status == ShiftStatus.SCHEDULED.value,
        Shift.scheduled_start_utc >= period_start,
        Shift.scheduled_start_utc < period_end,
    ).all()

    # Approved leave days in the period
    approved_leave = db.session.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == LeaveStatus.APPROVED.value,
        LeaveRequest.start_date <= period_end.date(),
        LeaveRequest.end_date   >= period_start.date(),
    ).all()
    leave_days = set()
    for lr in approved_leave:
        d = lr.start_date
        while d <= lr.end_date:
            leave_days.add(d)
            d = d.replace(day=d.day + 1) if d.day < 28 else (
                d.replace(month=d.month + 1, day=1) if d.month < 12
                else d.replace(year=d.year + 1, month=1, day=1)
            )

    expected_shifts = len([s for s in shifts if s.scheduled_start_utc.date() not in leave_days
                           if s.scheduled_start_utc.tzinfo is None
                           or s.scheduled_start_utc.replace(tzinfo=None).date() not in leave_days])
    # Simpler: just count all scheduled shifts, subtract approved leave count
    expected_shifts = max(len(shifts) - len(approved_leave), 0)

    # Clock-in events in the period (for this employee)
    clock_ins = db.session.query(ClockEvent).filter(
        ClockEvent.employee_id == employee_id,
        ClockEvent.event_type == ClockEventType.CLOCK_IN.value,
        ClockEvent.occurred_at_utc >= period_start,
        ClockEvent.occurred_at_utc < period_end,
    ).all()

    attended = len(clock_ins)

    # Punctuality: clock-ins that were on time (linked to a shift and not late)
    on_time = 0
    for ci in clock_ins:
        if ci.shift_id:
            shift = db.session.get(Shift, ci.shift_id)
            if shift and not is_late(ci.occurred_at_utc, shift):
                on_time += 1
        else:
            on_time += 1   # no shift → unscheduled, not counted as late

    punctuality_score = Decimal("100") if attended == 0 else Decimal(str(
        round(on_time / attended * 100, 1)
    ))
    attendance_score = Decimal("100") if expected_shifts == 0 else Decimal(str(
        min(round(attended / expected_shifts * 100, 1), 100)
    ))

    # Cash shortfalls
    short_count = db.session.query(CashReconciliation).filter(
        CashReconciliation.staff_id == employee_id,
        CashReconciliation.status == ReconciliationStatus.SHORT.value,
        CashReconciliation.period_end_utc >= period_start,
        CashReconciliation.period_end_utc < period_end,
    ).count()
    cash_health = Decimal(str(max(0, 100 - short_count * SHORTFALL_PENALTY_PER)))

    # Void rate
    void_rates = get_void_rates(period_start, period_end)
    void_rate_pct = Decimal("0")
    for row in void_rates:
        if row["staff_id"] == employee_id:
            void_rate_pct = Decimal(str(row["void_rate_pct"]))
            break
    void_health = Decimal(str(max(Decimal("0"), Decimal("100") - void_rate_pct)))

    composite = (
        punctuality_score * SCORE_WEIGHTS["punctuality"] +
        attendance_score  * SCORE_WEIGHTS["attendance"]  +
        cash_health       * SCORE_WEIGHTS["cash_health"] +
        void_health       * SCORE_WEIGHTS["void_health"]
    )

    hours_worked = compute_hours_worked(employee_id, period_start, period_end)

    return {
        "punctuality_score":  str(punctuality_score),
        "attendance_score":   str(attendance_score),
        "cash_health_score":  str(cash_health),
        "void_health_score":  str(void_health),
        "composite_score":    str(round(composite, 1)),
        "detail": {
            "shifts_scheduled": len(shifts),
            "shifts_attended":  attended,
            "on_time_clock_ins": on_time,
            "cash_shortfalls":  short_count,
            "void_rate_pct":    str(void_rate_pct),
            "hours_worked":     str(hours_worked),
            "guest_rating":     _get_guest_rating(employee_id, period_start, period_end),
        },
        "weights": {k: str(v) for k, v in SCORE_WEIGHTS.items()},
    }
