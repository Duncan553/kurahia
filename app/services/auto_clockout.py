"""
auto_clockout.py — close shifts nobody clocked out of.

The resort has 597 clock-INS against 67 clock-OUTS. compute_hours_worked pairs
IN with OUT and an unpaired IN contributes zero, so every hours figure in the
system reads 0.0 and payroll cannot be run at all. The function is correct;
the behaviour it depends on does not happen. People clock in because it is the
first thing they do and the tablet asks them to. Nobody clocks out, because at
the end of a shift they are leaving.

That is the same shape as the gate: a band stays ACTIVE until somebody
deactivates it, and the answer there was already an end-of-day sweep
(gate close-day / forfeit_day). This is that sweep for hours.

The roster is the authority. The manager has already set which shift each
person works — day or night — so a rostered shift closes at its stated end,
uncapped and unclamped. That matters most for nights: a 22:00-06:00 shift
crosses the business-day cutoff, and clamping it there would quietly shave
hours off every night worker.

Where there is NO roster entry the system is guessing, so it takes the stingy
branch: MAX_SHIFT_HOURS from the clock-in, or the day cutoff, whichever comes
first. Every row is flagged is_manual_override with a reason, so a manager can
see which hours the system supplied; corrections are new rows (append-only),
never edits.

Consequence worth stating plainly: if someone clocks in and leaves early, the
roster still pays the full shift. That is the trade the resort is making by
having the system close shifts on the worker's behalf.
"""
import uuid
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.clock_event import ClockEvent, ClockEventType
from app.models.shift import Shift
from app.models.audit_log import AuditLog

# Only used when there is NO rostered shift to close against. A rostered shift
# is never capped by this — the manager's roster outranks a default.
MAX_SHIFT_HOURS = 10


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def open_clock_ins(day_start: datetime, day_end: datetime):
    """Employees with a CLOCK_IN in the window and no later CLOCK_OUT."""
    events = db.session.query(ClockEvent).filter(
        ClockEvent.occurred_at_utc >= day_start,
        ClockEvent.occurred_at_utc < day_end,
    ).order_by(ClockEvent.occurred_at_utc).all()

    last_in = {}
    for ev in events:
        if ev.event_type == ClockEventType.CLOCK_IN.value:
            last_in[ev.employee_id] = ev
        elif ev.event_type == ClockEventType.CLOCK_OUT.value:
            last_in.pop(ev.employee_id, None)
    return list(last_in.values())


def auto_clock_out(day_start: datetime, day_end: datetime, actor_id: str | None = None):
    """Write a CLOCK_OUT for every shift left open. Returns (count, total_hours)."""
    from decimal import Decimal

    closed = 0
    total = Decimal("0")
    for ev in open_clock_ins(day_start, day_end):
        clock_in_at = _aware(ev.occurred_at_utc)

        # THE ROSTER IS THE CONTRACT. The manager has already said which shift
        # this person works — day or night — so the rostered end is the answer,
        # and it is not capped or clamped by anything else.
        #
        # A night shift is exactly why. It runs 22:00 -> 06:00, crossing the
        # business-day cutoff; clamping it to the cutoff, or to a fixed maximum
        # from the clock-in, would silently shave hours off every night worker
        # in the resort and nobody would see where they went.
        out_at = None
        if ev.shift_id:
            shift = db.session.get(Shift, ev.shift_id)
            if shift and shift.scheduled_end_utc:
                out_at = _aware(shift.scheduled_end_utc)

        if out_at is None:
            # No roster entry, so there is no stated finish to honour. Fall back
            # to the cap — deliberately the stingy option, because this is the
            # branch where the system is guessing.
            out_at = min(clock_in_at + timedelta(hours=MAX_SHIFT_HOURS),
                         _aware(day_end))

        # A clock-out can never precede its clock-in, whatever the roster says.
        out_at = max(out_at, clock_in_at)

        db.session.add(ClockEvent(
            employee_id=ev.employee_id,
            event_type=ClockEventType.CLOCK_OUT.value,
            occurred_at_utc=out_at,
            shift_id=ev.shift_id,
            is_manual_override=True,
            override_by_id=actor_id,
            override_reason="Auto clock-out at end of business day — no clock-out recorded.",
            # One per open clock-in, so re-running the sweep cannot double-close.
            idempotency_key=f"autoout-{ev.id}",
        ))
        total += Decimal(str(round((out_at - clock_in_at).total_seconds() / 3600, 4)))
        closed += 1

    if closed:
        AuditLog.log(
            actor="auto_clockout",
            action="hr.auto_clock_out",
            target=day_start.date().isoformat(),
            details=f"closed={closed} hours={total}",
        )
    db.session.commit()
    return closed, total
