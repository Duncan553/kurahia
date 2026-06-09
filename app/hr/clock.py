"""
hr/clock.py — Clock-in, clock-out, manual override, and event listing.

The WiFi rule: POST /hr/clock-in and /hr/clock-out check that
request.remote_addr falls within an active WiFiAllowList CIDR.
No allow-list entries → all clock-ins blocked (safe default).

Manual override: manager+ only, fully audited, sets is_manual_override=True.
Append-only: no edits. Corrections = new override records.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.clock_event import ClockEvent, ClockEventType
from app.models.audit_log import AuditLog
from app.services.hr import is_ip_allowed, find_matching_shift

clock_bp = Blueprint("hr_clock", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5
WIFI_REJECT_MSG = (
    "Clock-in only works on the hotel WiFi. "
    "Please connect to the staff network and try again."
)


def _get_own_profile(user_id: str) -> EmployeeProfile | None:
    return db.session.query(EmployeeProfile).filter_by(user_id=user_id, is_active=True).first()


def _write_clock_event(employee_id: str, event_type: ClockEventType,
                       source_ip: str | None, ssid: str | None,
                       idem_key: str, is_override: bool = False,
                       override_by_id: str | None = None,
                       override_reason: str | None = None) -> tuple:
    """
    Write a ClockEvent, auto-link to the nearest shift, return (event, existed).
    """
    existing = db.session.query(ClockEvent).filter_by(idempotency_key=idem_key).first()
    if existing:
        return existing, True

    now = datetime.now(timezone.utc)
    shift = find_matching_shift(employee_id, now)

    event = ClockEvent(
        employee_id=employee_id,
        event_type=event_type.value,
        occurred_at_utc=now,
        source_ip=source_ip,
        source_wifi_ssid=ssid,
        shift_id=shift.id if shift else None,
        is_manual_override=is_override,
        override_by_id=override_by_id,
        override_reason=override_reason,
        idempotency_key=idem_key,
    )
    db.session.add(event)
    db.session.commit()
    return event, False


@clock_bp.post("/clock-in")
@require_active_user
def clock_in():
    actor = db.session.get(User, get_jwt_identity())
    profile = _get_own_profile(actor.id)
    if not profile:
        return jsonify({"error": "No employee profile found. Ask your manager to create one."}), 403

    source_ip = request.remote_addr
    if not is_ip_allowed(source_ip):
        return jsonify({"error": WIFI_REJECT_MSG}), 403

    data     = request.get_json(silent=True) or {}
    ssid     = data.get("ssid")
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    event, existed = _write_clock_event(
        profile.id, ClockEventType.CLOCK_IN, source_ip, ssid, idem_key
    )
    if existed:
        return jsonify({"id": event.id, "duplicate": True}), 200

    AuditLog.log(actor=actor.username, action="hr.clock_in", target=profile.id,
                 details=f"ip={source_ip} shift={'linked' if event.shift_id else 'none'}")
    db.session.commit()

    return jsonify({
        "id":          event.id,
        "event_type":  event.event_type,
        "occurred_at": event.occurred_at_utc.isoformat(),
        "shift_id":    event.shift_id,
        "no_shift":    event.shift_id is None,
    }), 201


@clock_bp.post("/clock-out")
@require_active_user
def clock_out():
    actor = db.session.get(User, get_jwt_identity())
    profile = _get_own_profile(actor.id)
    if not profile:
        return jsonify({"error": "No employee profile found."}), 403

    source_ip = request.remote_addr
    if not is_ip_allowed(source_ip):
        return jsonify({"error": WIFI_REJECT_MSG}), 403

    data     = request.get_json(silent=True) or {}
    ssid     = data.get("ssid")
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    event, existed = _write_clock_event(
        profile.id, ClockEventType.CLOCK_OUT, source_ip, ssid, idem_key
    )
    if existed:
        return jsonify({"id": event.id, "duplicate": True}), 200

    AuditLog.log(actor=actor.username, action="hr.clock_out", target=profile.id)
    db.session.commit()

    return jsonify({
        "id":          event.id,
        "event_type":  event.event_type,
        "occurred_at": event.occurred_at_utc.isoformat(),
        "shift_id":    event.shift_id,
    }), 201


@clock_bp.post("/clock-events/manual")
@require_active_user
def manual_clock():
    """
    Manager+ manually clocks someone in or out.
    Used when WiFi is down, phone is lost, etc.
    Every override is audit-logged — cannot be quietly abused.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can manually clock someone in/out."}), 403

    data        = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")          # EmployeeProfile.id
    event_type  = (data.get("event_type") or "").upper()
    reason      = (data.get("reason") or "").strip()
    idem_key    = data.get("idempotency_key") or str(uuid.uuid4())

    if not employee_id:
        return jsonify({"error": "employee_id is required."}), 400
    if event_type not in ClockEventType.__members__:
        return jsonify({"error": f"event_type must be CLOCK_IN or CLOCK_OUT."}), 400
    if not reason:
        return jsonify({"error": "reason is required for manual overrides."}), 400

    # Self-override block: a manager cannot override their own clock events
    # (avoids "I worked 4 extra hours" fraud). Owner can override anyone.
    from app.models.employee_profile import EmployeeProfile as _EP
    _target_profile = db.session.get(_EP, employee_id)
    if _target_profile and _target_profile.user_id == actor.id:
        return jsonify({"error": "You cannot manually override your own clock events. "
                                 "Ask another manager or the owner to do this."}), 403

    profile = db.session.get(EmployeeProfile, employee_id)
    if not profile or not profile.is_active:
        return jsonify({"error": "Employee profile not found or disabled."}), 404

    event, existed = _write_clock_event(
        employee_id, ClockEventType(event_type),
        source_ip=request.remote_addr,
        ssid=None,
        idem_key=idem_key,
        is_override=True,
        override_by_id=actor.id,
        override_reason=reason,
    )
    if existed:
        return jsonify({"id": event.id, "duplicate": True}), 200

    AuditLog.log(
        actor=actor.username, action="hr.manual_override",
        target=employee_id,
        details=f"type={event_type} reason={reason}",
    )
    db.session.commit()

    return jsonify({
        "id":                event.id,
        "event_type":        event.event_type,
        "occurred_at":       event.occurred_at_utc.isoformat(),
        "is_manual_override": True,
        "override_reason":   reason,
    }), 201


@clock_bp.get("/clock-status")
@require_active_user
def my_clock_status():
    """Current user's own latest clock event — accessible to all staff (no Manager check)."""
    actor   = db.session.get(User, get_jwt_identity())
    profile = _get_own_profile(actor.id)
    if not profile:
        return jsonify({"error": "No employee profile found."}), 404

    latest = (
        db.session.query(ClockEvent)
        .filter_by(employee_id=profile.id)
        .order_by(ClockEvent.occurred_at_utc.desc())
        .first()
    )
    if not latest:
        return jsonify({"status": "CLOCKED_OUT", "last_event": None}), 200

    return jsonify({
        "status": latest.event_type,
        "last_event": {
            "id":          latest.id,
            "event_type":  latest.event_type,
            "occurred_at": latest.occurred_at_utc.isoformat(),
            "shift_id":    latest.shift_id,
        },
    }), 200


@clock_bp.get("/clock-events")
@require_active_user
def list_clock_events():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    employee_id = request.args.get("employee_id")
    date_str    = request.args.get("date")

    query = db.session.query(ClockEvent)
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(
                ClockEvent.occurred_at_utc >= d,
                ClockEvent.occurred_at_utc <  d.replace(hour=23, minute=59, second=59),
            )
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400

    events = query.order_by(ClockEvent.occurred_at_utc).all()
    return jsonify([{
        "id":          ev.id,
        "employee_id": ev.employee_id,
        "event_type":  ev.event_type,
        "occurred_at": ev.occurred_at_utc.isoformat(),
        "shift_id":    ev.shift_id,
        "is_manual_override": ev.is_manual_override,
        "source_ip":   ev.source_ip,
    } for ev in events]), 200
