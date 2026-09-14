"""
hr/attendance.py — Attendance views for managers.

today:      Who clocked in, who is absent (with/without notice), on approved leave.
employee:   Full clock-event history for one staff member on a given date.
summary:    Period summary per employee — shifts, attended, hours, absent types.
"""
from datetime import datetime, timezone, timedelta, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.shift import Shift, ShiftStatus
from app.models.clock_event import ClockEvent, ClockEventType
from app.services.hr import (
    has_approved_leave, has_absence_notice,
    is_late, compute_hours_worked,
)

attendance_bp = Blueprint("hr_attendance", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


@attendance_bp.get("/attendance/today")
@require_active_user
def attendance_today():
    """
    Returns every employee scheduled today with their status:
    clocked_in | approved_leave | absent_with_notice | absent_no_notice
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    from app.services.business_day import business_day_bounds_today, business_day_for
    day_start, day_end = business_day_bounds_today()
    today = business_day_for(datetime.now(timezone.utc)).date()

    dept_filter = request.args.get("department_id")

    query = db.session.query(Shift).filter(
        Shift.status == ShiftStatus.SCHEDULED.value,
        Shift.scheduled_start_utc >= day_start,
        Shift.scheduled_start_utc < day_end,
    )
    if dept_filter:
        query = query.filter(Shift.department_id == dept_filter)

    shifts = query.all()

    # The board is the UNION of who was ROSTERED and who actually TURNED UP.
    #
    # It used to iterate shifts alone, so an employee with no scheduled shift
    # could not appear on it however long they worked — they clocked in, served
    # a full service, and the manager's attendance board stayed empty. On a
    # property that does not roster rigorously (and most do not, early on) that
    # makes the screen permanently blank while the resort is full of staff,
    # which is what it was showing today: "No shifts scheduled today" with three
    # people clocked in. It is also a payroll hole — hours worked off-roster
    # never reach the person who has to verify them.
    #
    # A shift answers "who was meant to be here". A clock event answers "who
    # is here". The screen is called Attendance, so it has to answer the second
    # and use the first as context.
    shift_by_emp = {s.employee_id: s for s in shifts}

    walk_ins = db.session.query(ClockEvent.employee_id).filter(
        ClockEvent.event_type == ClockEventType.CLOCK_IN.value,
        ClockEvent.occurred_at_utc >= day_start,
        ClockEvent.occurred_at_utc < day_end,
    ).distinct().all()

    for (emp_id,) in walk_ins:
        if emp_id in shift_by_emp:
            continue
        if dept_filter:
            # Honour the department filter for unrostered staff too, via their
            # profile — there is no shift row to read a department from.
            prof = db.session.get(EmployeeProfile, emp_id)
            if not prof or prof.department_id != dept_filter:
                continue
        shift_by_emp[emp_id] = None          # present, but not rostered

    rows = []
    for emp_id, s in shift_by_emp.items():
        profile = db.session.get(EmployeeProfile, emp_id)

        clocked_in = db.session.query(ClockEvent).filter(
            ClockEvent.employee_id == emp_id,
            ClockEvent.event_type == ClockEventType.CLOCK_IN.value,
            ClockEvent.occurred_at_utc >= day_start,
            ClockEvent.occurred_at_utc < day_end,
        ).first()

        on_leave = has_approved_leave(emp_id, today)

        # Approved leave OUTRANKS a clock event, and that ordering is deliberate.
        # Leave is a decision a manager signed off on; a clock-in is an event
        # anyone standing on the staff WiFi can produce. Checking the clock first
        # meant an approved leave day silently read as a normal working day.
        #
        # Clock-in is NOT blocked during leave (see app/hr/clock.py) — someone on
        # leave covering a gap is ordinary here, and barring the door strands a
        # person who is standing at the post ready to work. So both states really
        # can exist, and the manager needs to SEE that rather than have it
        # swallowed: leave sets the status, the flag below raises the clash.
        if on_leave:
            status = "approved_leave"
            late = None
        elif clocked_in:
            status = "clocked_in"
            # Lateness is measured against a rostered start. With no shift
            # there is no time to be late FOR, so it stays None rather than
            # inventing a baseline.
            late = is_late(clocked_in.occurred_at_utc, s) if s else None
        elif s and has_absence_notice(emp_id, s.id, today):
            status = "absent_with_notice"
            late = None
        else:
            status = "absent_no_notice"
            late = None

        rows.append({
            "employee_id":   emp_id,
            "employee_name": profile.full_name if profile else None,
            "shift_id":      s.id if s else None,
            "shift_start":   s.scheduled_start_utc.isoformat() if s else None,
            "shift_end":     s.scheduled_end_utc.isoformat() if s else None,
            # Present without a roster entry. Not an accusation — covering a
            # gap is ordinary — but the manager should see that it happened.
            "unrostered":    s is None,
            "status":        status,
            "late":          late,
            # True only in the contradictory case: on approved leave yet a clock
            # event exists for today. Surfaces the anomaly instead of hiding it.
            "clocked_in_while_on_leave": bool(on_leave and clocked_in),
        })

    return jsonify(rows), 200


@attendance_bp.get("/attendance/employee/<profile_id>")
@require_active_user
def attendance_employee(profile_id):
    """Clock events for one employee on a given date (defaults to today)."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    date_str = request.args.get("date")
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400
    else:
        today = _today_utc()
        d = datetime(today.year, today.month, today.day)

    day_start = d
    day_end   = d + timedelta(days=1)

    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404

    events = db.session.query(ClockEvent).filter(
        ClockEvent.employee_id == profile_id,
        ClockEvent.occurred_at_utc >= day_start,
        ClockEvent.occurred_at_utc < day_end,
    ).order_by(ClockEvent.occurred_at_utc).all()

    hours = compute_hours_worked(profile_id, day_start, day_end)

    return jsonify({
        "employee_id":   profile_id,
        "employee_name": profile.full_name,
        "date":          d.strftime("%Y-%m-%d"),
        "hours_worked":  str(hours),
        "events": [{
            "id":          ev.id,
            "event_type":  ev.event_type,
            "occurred_at": ev.occurred_at_utc.isoformat(),
            "shift_id":    ev.shift_id,
            "is_manual_override": ev.is_manual_override,
        } for ev in events],
    }), 200


@attendance_bp.get("/attendance/summary")
@require_active_user
def attendance_summary():
    """
    Per-employee summary for a period (start_date / end_date, defaults to current month).
    Returns shifts scheduled, attended, hours worked, absent-with-notice, absent-no-notice.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    today = _today_utc()
    start_str = request.args.get("start_date") or today.replace(day=1).isoformat()
    end_str   = request.args.get("end_date")   or today.isoformat()

    try:
        period_start = datetime.strptime(start_str, "%Y-%m-%d")
        period_end   = datetime.strptime(end_str,   "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "start_date and end_date must be YYYY-MM-DD."}), 400

    profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    result = []
    for p in profiles:
        shifts = db.session.query(Shift).filter(
            Shift.employee_id == p.id,
            Shift.status == ShiftStatus.SCHEDULED.value,
            Shift.scheduled_start_utc >= period_start,
            Shift.scheduled_start_utc < period_end,
        ).all()

        # DAYS worked, not clock-in EVENTS. This counted raw CLOCK_IN rows and
        # reported them as "shifts attended", but a PIN login at a station
        # clocks you in, so one person produces several a day. The board showed
        # "30/9 attended" — thirty out of nine — and the ratio meant nothing.
        # Distinct dates is the number a manager actually wants, and it counts
        # unrostered days too, which shifts alone cannot.
        clock_in_dates = {
            (ev.occurred_at_utc.date() if ev.occurred_at_utc.tzinfo is None
             else ev.occurred_at_utc.astimezone(timezone.utc).date())
            for ev in db.session.query(ClockEvent).filter(
                ClockEvent.employee_id == p.id,
                ClockEvent.event_type == ClockEventType.CLOCK_IN.value,
                ClockEvent.occurred_at_utc >= period_start,
                ClockEvent.occurred_at_utc < period_end,
            ).all()
        }
        days_worked = len(clock_in_dates)

        shifts_attended       = 0
        absent_with_notice    = 0
        absent_no_notice      = 0
        for s in shifts:
            s_date = s.scheduled_start_utc.date() if s.scheduled_start_utc.tzinfo is None \
                     else s.scheduled_start_utc.replace(tzinfo=None).date()

            clocked = db.session.query(ClockEvent).filter(
                ClockEvent.employee_id == p.id,
                ClockEvent.event_type == ClockEventType.CLOCK_IN.value,
                ClockEvent.shift_id == s.id,
            ).first()

            if clocked:
                shifts_attended += 1
            else:
                if (has_approved_leave(p.id, s_date) or
                        has_absence_notice(p.id, s.id, s_date)):
                    absent_with_notice += 1
                else:
                    absent_no_notice += 1

        hours = compute_hours_worked(p.id, period_start, period_end)

        result.append({
            "employee_id":        p.id,
            "employee_name":      p.full_name,
            "shifts_scheduled":   len(shifts),
            # Now bounded by shifts_scheduled, because it counts shifts that
            # actually had someone clock in against them.
            "shifts_attended":    shifts_attended,
            "days_worked":        days_worked,
            "absent_with_notice": absent_with_notice,
            "absent_no_notice":   absent_no_notice,
            "hours_worked":       str(hours),
        })

    return jsonify(result), 200
