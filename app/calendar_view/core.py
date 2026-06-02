"""
calendar_view/core.py — Peak dates, holidays, planning-meeting triggers.

Planning triggers: when a CalendarEntry has planning_trigger_offset_days set,
a QUEUED Notification is created for owner(s) at save time, scheduled for
(date_start - offset_days). Reuses the Chunk 8 notification pipeline.
"""
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.calendar_entry import CalendarEntry, CalendarEntryType
from app.models.notification import (
    Notification, NotificationStatus, NotificationReferenceType,
)
from app.models.audit_log import AuditLog

calendar_bp = Blueprint("calendar_core", __name__, url_prefix="/calendar")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


def _entry_dict(e: CalendarEntry) -> dict:
    return {
        "id":            e.id,
        "title":         e.title,
        "entry_type":    e.entry_type,
        "date_start":    e.date_start_utc.isoformat(),
        "date_end":      e.date_end_utc.isoformat(),
        "is_peak":       e.is_peak,
        "description":   e.description,
        "planning_trigger_offset_days": e.planning_trigger_offset_days,
        "is_active":     e.is_active,
    }


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _schedule_planning_trigger(entry: CalendarEntry) -> None:
    """If offset is set, queue a notification to all owner-level users."""
    if not entry.planning_trigger_offset_days:
        return
    trigger_dt = entry.date_start_utc - timedelta(days=entry.planning_trigger_offset_days)
    if trigger_dt.tzinfo is None:
        trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)

    owners = db.session.query(User).join(User.role).filter(
        User.role.has(level=OWNER_LEVEL)
    ).all()
    for owner in owners:
        idem = f"cal-trigger-{entry.id}-{owner.id}"
        if db.session.query(Notification).filter_by(idempotency_key=idem).first():
            continue
        notif = Notification(
            recipient_user_id=owner.id,
            reference_type=NotificationReferenceType.GENERAL.value,
            reference_id=entry.id,
            subject=f"[Planning] {entry.title} in {entry.planning_trigger_offset_days} days",
            body=(
                f"{entry.title} is in {entry.planning_trigger_offset_days} days "
                f"({entry.date_start_utc.strftime('%d %b %Y')}). "
                "Plan inventory, staffing, and special menu now."
            ),
            status=NotificationStatus.QUEUED.value,
            scheduled_for_utc=trigger_dt,
            idempotency_key=idem,
        )
        db.session.add(notif)
    db.session.flush()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@calendar_bp.post("")
@require_active_user
def create_entry():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data       = request.get_json(silent=True) or {}
    title      = (data.get("title") or "").strip()
    entry_type = (data.get("entry_type") or "").upper()
    start      = _parse_dt(data.get("date_start_utc") or data.get("date_start"))
    end        = _parse_dt(data.get("date_end_utc") or data.get("date_end")) or start

    if not title:
        return jsonify({"error": "title is required."}), 400
    if entry_type not in CalendarEntryType.__members__:
        return jsonify({"error": f"entry_type must be one of {list(CalendarEntryType.__members__)}."}), 400
    if not start:
        return jsonify({"error": "date_start is required (ISO format)."}), 400

    offset = data.get("planning_trigger_offset_days")
    if offset is not None:
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            return jsonify({"error": "planning_trigger_offset_days must be an integer."}), 400

    entry = CalendarEntry(
        title=title, entry_type=entry_type,
        date_start_utc=start, date_end_utc=end,
        is_peak=bool(data.get("is_peak", entry_type in (
            CalendarEntryType.PEAK.value, CalendarEntryType.HOLIDAY.value
        ))),
        description=data.get("description"),
        planning_trigger_offset_days=offset,
        created_by_id=actor.id,
    )
    db.session.add(entry)
    db.session.flush()
    _schedule_planning_trigger(entry)
    AuditLog.log(actor=actor.username, action="calendar.create",
                 details=f"{entry_type} {title}")
    db.session.commit()
    return jsonify(_entry_dict(entry)), 201


@calendar_bp.get("")
@require_active_user
def list_entries():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    from_dt = _parse_dt(request.args.get("from"))
    to_dt   = _parse_dt(request.args.get("to"))
    q = db.session.query(CalendarEntry).filter_by(is_active=True)
    if from_dt:
        q = q.filter(CalendarEntry.date_start_utc >= from_dt)
    if to_dt:
        q = q.filter(CalendarEntry.date_start_utc <= to_dt)
    entries = q.order_by(CalendarEntry.date_start_utc).all()
    return jsonify([_entry_dict(e) for e in entries]), 200


@calendar_bp.post("/<entry_id>/disable")
@require_active_user
def disable_entry(entry_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    entry = db.session.get(CalendarEntry, entry_id)
    if not entry:
        return jsonify({"error": "Calendar entry not found."}), 404
    entry.is_active = False
    db.session.commit()
    return jsonify({"id": entry.id, "is_active": False}), 200
