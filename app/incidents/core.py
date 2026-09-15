"""
incidents/core.py — Accident / incident logging.

Any authenticated staff can log. Managers (level 5+) can list and acknowledge.
Append-only: rows are never edited or deleted.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.incident import Incident, IncidentSeverity
from app.models.audit_log import AuditLog
from app.models.notification import (
    Notification, NotificationStatus, NotificationChannel,
)
from app.utils.auth_decorators import require_active_user

incidents_bp = Blueprint("incidents", __name__, url_prefix="/incidents")

MANAGER_LEVEL = 5
VALID_SEVERITIES = {s.value for s in IncidentSeverity}


def _incident_dict(inc: Incident) -> dict:
    return {
        "id":             inc.id,
        "description":    inc.description,
        "location":       inc.location,
        "severity":       inc.severity,
        "involved_guest": inc.involved_guest,
        "actioned":       inc.actioned,
        "actioned_by":    inc.actioner.username if inc.actioner else None,
        "actioned_at":    inc.actioned_at.isoformat() if inc.actioned_at else None,
        "reported_by":    inc.reporter.username if inc.reporter else None,
        "created_at":     inc.created_at.isoformat() if inc.created_at else None,
    }


@incidents_bp.post("")
@require_active_user
def log_incident():
    """Any authenticated staff can log an incident."""
    actor = db.session.get(User, get_jwt_identity())
    data  = request.get_json(silent=True) or {}

    description    = (data.get("description") or "").strip()
    location       = (data.get("location") or "").strip()
    severity       = (data.get("severity") or "").strip().upper()
    involved_guest = (data.get("involved_guest") or "").strip() or None
    idem_key       = (data.get("idempotency_key") or "").strip()

    if not description:
        return jsonify({"error": "description is required."}), 400
    if not location:
        return jsonify({"error": "location is required."}), 400
    if severity not in VALID_SEVERITIES:
        return jsonify({"error": f"severity must be one of: {', '.join(sorted(VALID_SEVERITIES))}."}), 400
    if not idem_key:
        return jsonify({"error": "idempotency_key is required."}), 400

    # Idempotency check
    existing = db.session.query(Incident).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({**_incident_dict(existing), "duplicate": True}), 200

    inc = Incident(
        reported_by_id  = actor.id,
        description     = description,
        location        = location,
        severity        = severity,
        involved_guest  = involved_guest,
        idempotency_key = idem_key,
    )
    db.session.add(inc)
    db.session.flush()          # inc.id, for the notifications below
    AuditLog.log(
        actor=actor.username, action="incident.log",
        target=inc.id, details=f"severity={severity} location={location}",
    )
    _alert_managers(inc, actor)
    db.session.commit()
    return jsonify(_incident_dict(inc)), 201


def _alert_managers(inc, reporter) -> None:
    """Put the incident in front of somebody.

    Logging one wrote the row and an audit line and told NOBODY. Listing them
    is manager-only, so a guest hurt at the jet ski dock sat in a table until
    a manager happened to open a screen they have no reason to open — while
    the person who filed it saw "Incident logged." and reasonably believed it
    had been raised. The one thing an incident report exists to do is reach
    someone who can act, and it was the one thing missing.

    Every severity goes out, not just HIGH: the severity is the reporter's
    guess made in the moment, and "low" is exactly how a small thing that was
    actually a big thing gets described. A manager can read three lines.
    """
    managers = db.session.query(User).filter(
        User.is_active.is_(True)
    ).join(User.role).filter(
        # Same floor as list_incidents — telling someone who cannot then open
        # the list would be a notification with nowhere to go.
        db.text("roles.level >= :lvl")
    ).params(lvl=MANAGER_LEVEL).all()

    now = datetime.now(timezone.utc)
    for m in managers:
        db.session.add(Notification(
            recipient_user_id = m.id,
            reference_type    = "incident",
            reference_id      = inc.id,
            subject           = f"{inc.severity} incident — {inc.location}",
            body              = (f"{reporter.username} logged: {inc.description}"
                                 + (f" Guest: {inc.involved_guest}." if inc.involved_guest else "")),
            status            = NotificationStatus.DELIVERED.value,
            channel           = NotificationChannel.IN_APP.value,
            scheduled_for_utc = now,
            sent_at_utc       = now,
            # One per manager per incident. A retried request reuses the
            # incident's idempotency key upstream, so this never doubles.
            idempotency_key   = f"incident-{inc.id}-{m.id}",
        ))


@incidents_bp.get("")
@require_active_user
def list_incidents():
    """Manager+ can list incidents with optional filters."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager access required."}), 403

    severity = request.args.get("severity", "").upper() or None
    actioned = request.args.get("actioned", "")
    limit    = min(int(request.args.get("limit", 50)), 200)

    q = db.session.query(Incident)
    if severity:
        if severity not in VALID_SEVERITIES:
            return jsonify({"error": f"severity must be one of: {', '.join(sorted(VALID_SEVERITIES))}."}), 400
        q = q.filter_by(severity=severity)
    if actioned.lower() == "true":
        q = q.filter_by(actioned=True)
    elif actioned.lower() == "false":
        q = q.filter_by(actioned=False)

    incidents = q.order_by(Incident.created_at.desc()).limit(limit).all()
    return jsonify([_incident_dict(i) for i in incidents]), 200


@incidents_bp.patch("/<incident_id>/action")
@require_active_user
def action_incident(incident_id: str):
    """Manager+ acknowledges an incident."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager access required."}), 403

    inc = db.session.get(Incident, incident_id)
    if not inc:
        return jsonify({"error": "Incident not found."}), 404

    if inc.actioned:
        return jsonify({**_incident_dict(inc), "duplicate": True}), 200

    inc.actioned       = True
    inc.actioned_by_id = actor.id
    inc.actioned_at    = datetime.now(timezone.utc)

    AuditLog.log(
        actor=actor.username, action="incident.action",
        target=incident_id, details=f"severity={inc.severity}",
    )
    db.session.commit()
    return jsonify(_incident_dict(inc)), 200
