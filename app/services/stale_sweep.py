"""
stale_sweep.py — things nobody closed, raised to somebody who can.

An audit of every open-ended state in this system found the same shape four
times: a row one person creates and a DIFFERENT person must close. The closing
action always costs the second person something and gains them nothing, so it
does not happen. Wristbands had a sweep (gate close-day). Clock-ins now have one
(auto_clockout). Bookings have two (flag_no_shows, release_expired_holds).

Two had none, measured on live data:
  4 tabs open longer than 24h — one at 499 hours
  20 leave requests sitting PENDING, with nothing ageing or escalating them

Neither is auto-RESOLVED here, and that is deliberate. Closing a tab records a
payment nobody made, and approving leave is a manager's decision. Inventing
either would be worse than leaving them open. What they get instead is a voice:
the tab lands on the manager's exceptions, and the leave request nudges its
approver and then the owner.
"""
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.tab import Tab, TabStatus
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.user import User
from app.models.notification import (
    Notification, NotificationStatus, NotificationChannel,
)
from app.models.audit_log import AuditLog

MANAGER_LEVEL = 5
OWNER_LEVEL = 10

# A tab still open after the trading day ended is a bill nobody settled.
STALE_TAB_HOURS = 24
# A leave request is a person waiting for an answer about their own time.
LEAVE_NUDGE_DAYS = 3       # -> the approver
LEAVE_ESCALATE_DAYS = 7    # -> the owner


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _recipients(min_level):
    return db.session.query(User).join(User.role).filter(
        User.is_active.is_(True),
    ).all()


def _notify(user_id, subject, body, ref_type, ref_id):
    """One notification per (recipient, thing, day).

    The idempotency key carries the DATE, so a sweep that runs every day nudges
    once a day rather than once ever — a reminder that fires a single time is
    not a reminder. It also cannot fire twice if the cron runs twice.
    """
    day = datetime.now(timezone.utc).date().isoformat()
    key = f"stale-{ref_type}-{ref_id}-{user_id}-{day}"
    if db.session.query(Notification).filter_by(idempotency_key=key).first():
        return False
    db.session.add(Notification(
        recipient_user_id=user_id,
        reference_type=ref_type,
        reference_id=ref_id,
        subject=subject,
        body=body,
        status=NotificationStatus.DELIVERED.value,
        channel=NotificationChannel.IN_APP.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        sent_at_utc=datetime.now(timezone.utc),
        idempotency_key=key,
    ))
    return True


def stale_tabs(now=None):
    """Tabs open past the trading day. Returns the list, newest first."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_TAB_HOURS)
    rows = db.session.query(Tab).filter(
        Tab.status == TabStatus.OPEN.value,
        Tab.opened_at_utc < cutoff.replace(tzinfo=None),
    ).all()
    return sorted(rows, key=lambda t: _aware(t.opened_at_utc))


def sweep(now=None):
    """Raise both classes to whoever can act. Returns a summary dict."""
    from app.services.tab import get_tab_balance

    now = now or datetime.now(timezone.utc)
    managers = [u for u in _recipients(MANAGER_LEVEL) if u.role and u.role.level >= MANAGER_LEVEL]
    owners   = [u for u in managers if u.role.level >= OWNER_LEVEL]

    tabs = stale_tabs(now)
    tab_notices = 0
    for t in tabs:
        age_h = int((now - _aware(t.opened_at_utc)).total_seconds() // 3600)
        bal = get_tab_balance(t.id)
        ref = t.reference or "Walk-in"
        for m in managers:
            if _notify(m.id, f"Tab still open — {ref}",
                       f"{ref} has been open {age_h}h with KSh {bal} outstanding. "
                       f"Settle it or close it.",
                       "stale_tab", t.id):
                tab_notices += 1

    pending = db.session.query(LeaveRequest).filter(
        LeaveRequest.status == LeaveStatus.PENDING.value
    ).all()
    leave_notices = 0
    for lr in pending:
        age_d = (now - _aware(lr.created_at_utc)).days
        if age_d < LEAVE_NUDGE_DAYS:
            continue
        # Past the escalation mark the owner is added, because the approver has
        # now had a week and the person asking still has no answer.
        targets = owners if age_d >= LEAVE_ESCALATE_DAYS else managers
        who = lr.employee.full_name if lr.employee else "A staff member"
        for m in targets:
            if _notify(m.id, f"Leave request waiting {age_d} days",
                       f"{who} asked for leave {lr.start_date} to {lr.end_date} "
                       f"and has had no answer for {age_d} days.",
                       "stale_leave", lr.id):
                leave_notices += 1

    if tab_notices or leave_notices:
        AuditLog.log(actor="stale_sweep", action="ops.stale_sweep",
                     target=now.date().isoformat(),
                     details=f"tabs={len(tabs)} leave={len(pending)}")
    db.session.commit()
    return {
        "stale_tabs": len(tabs),
        "tab_notices": tab_notices,
        "pending_leave": len(pending),
        "leave_notices": leave_notices,
    }
