"""
dispatcher.py — Alive-presence delivery engine.

For each due QUEUED notification:
  1. Is recipient clocked in and on-site? → deliver IN_APP (inbox available immediately).
  2. Is WhatsApp channel active? → try WhatsApp socket.
  3. Is SMS channel active?      → try SMS socket.
  4. All failed → status=FAILED, notes explain why.

Presence = most recent ClockEvent is CLOCK_IN within 16 hours.
"Within 16 hours" is a generous window covering any normal shift length.
"""
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.notification import (
    Notification, NotificationStatus, NotificationChannel, NotificationChannelConfig,
)
from app.models.audit_log import AuditLog


def _channel_active(name: str) -> bool:
    """True if the owner hasn't disabled this channel."""
    cfg = db.session.query(NotificationChannelConfig).filter_by(
        channel_name=name, is_active=True
    ).first()
    return cfg is not None


def is_user_present(user_id: str) -> bool:
    """
    True if the employee last clocked IN within the past 16 hours.
    Users without an EmployeeProfile (e.g. system owner with no profile) are never present.
    """
    from app.models.employee_profile import EmployeeProfile
    from app.models.clock_event import ClockEvent, ClockEventType

    profile = db.session.query(EmployeeProfile).filter_by(user_id=user_id).first()
    if not profile:
        return False

    last = db.session.query(ClockEvent).filter_by(employee_id=profile.id)\
        .order_by(ClockEvent.occurred_at_utc.desc()).first()
    if not last or last.event_type != ClockEventType.CLOCK_IN.value:
        return False

    occurred = last.occurred_at_utc
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - occurred).total_seconds() < 16 * 3600


def _get_phone(user_id: str) -> str | None:
    from app.models.employee_profile import EmployeeProfile
    profile = db.session.query(EmployeeProfile).filter_by(user_id=user_id).first()
    return profile.phone if profile else None


def deliver_notification(notif: Notification) -> str:
    """
    Attempt delivery of a single QUEUED notification. Updates notif in place.
    Returns the final status string.
    """
    from app.services.notifications.whatsapp import send_whatsapp
    from app.services.notifications.sms import send_sms

    now = datetime.now(timezone.utc)

    # Path 1: recipient is on-site and clocked in → deliver in-app immediately
    if is_user_present(notif.recipient_user_id):
        notif.channel       = NotificationChannel.IN_APP.value
        notif.status        = NotificationStatus.DELIVERED.value
        notif.sent_at_utc   = now
        AuditLog.log(actor="dispatcher", action="notification.in_app",
                     target=notif.id, details=f"user={notif.recipient_user_id}")
        return notif.status

    phone = _get_phone(notif.recipient_user_id)

    # Path 2: try WhatsApp
    if phone and _channel_active(NotificationChannel.WHATSAPP.value):
        status_code, msg = send_whatsapp(phone, notif.body)
        if status_code == "SENT":
            notif.channel     = NotificationChannel.WHATSAPP.value
            notif.status      = NotificationStatus.DELIVERED.value
            notif.sent_at_utc = now
            return notif.status
        notif.notes = f"WhatsApp: {msg}"

    # Path 3: try SMS fallback
    if phone and _channel_active(NotificationChannel.SMS.value):
        status_code, msg = send_sms(phone, notif.body)
        if status_code == "SENT":
            notif.channel     = NotificationChannel.SMS.value
            notif.status      = NotificationStatus.DELIVERED.value
            notif.sent_at_utc = now
            return notif.status
        notif.notes = (notif.notes or "") + f" | SMS: {msg}"

    # Path 4: all paths down
    notif.status = NotificationStatus.FAILED.value
    if not notif.notes:
        notif.notes = "no gateway configured"
    AuditLog.log(actor="dispatcher", action="notification.failed",
                 target=notif.id, details=notif.notes)
    return notif.status


def deliver_due(now: datetime | None = None) -> dict:
    """
    Sweep all QUEUED notifications whose scheduled_for_utc has passed.
    Returns a summary dict.
    """
    now = now or datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    due = db.session.query(Notification).filter(
        Notification.status == NotificationStatus.QUEUED.value,
    ).all()

    # filter those whose scheduled time has passed
    pending = []
    for n in due:
        sched = n.scheduled_for_utc
        if sched is None:
            continue
        sched_naive = sched.replace(tzinfo=None) if sched.tzinfo else sched
        if sched_naive <= now_naive:
            pending.append(n)

    results = {"delivered": 0, "failed": 0, "total": len(pending)}
    for notif in pending:
        final = deliver_notification(notif)
        if final == NotificationStatus.DELIVERED.value:
            results["delivered"] += 1
        else:
            results["failed"] += 1

    if pending:
        db.session.flush()

    return results
