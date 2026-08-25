"""
hr/roster.py — Daily station roster.

Every employee has a fixed home department on their User record. This is the
day-to-day override: manager assigns each person to a department/station for
today (or a given date), and that's what governs which work dashboard they
land on — not their permanent department. Lets a manager cover gaps (e.g. a
waiter helping Front Desk today) without touching anyone's account.

POST /hr/roster        — manager+ assigns one employee to a department for a date
GET  /hr/roster?date=  — manager+ sees the full roster for that date
GET  /hr/roster/me     — any staff: my own assignment for today (falls back to
                          their home department if nobody rostered them)
"""
from datetime import datetime, timezone, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.department import Department
from app.models.station_roster import StationRoster
from app.models.audit_log import AuditLog

roster_bp = Blueprint("hr_roster", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _entry_dict(r: StationRoster) -> dict:
    return {
        "id":            r.id,
        "user_id":       r.user_id,
        "username":      r.user.username if r.user else None,
        "department_id": r.department_id,
        "department":    r.department.name if r.department else None,
        "roster_date":   r.roster_date.isoformat(),
        "assigned_by":   r.assigned_by.username if r.assigned_by else None,
    }


@roster_bp.post("/roster")
@require_active_user
def assign_station():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to set the roster."}), 403

    data          = request.get_json(silent=True) or {}
    user_id       = data.get("user_id")
    department_id = data.get("department_id")
    roster_date   = _parse_date(data.get("roster_date")) or _today()

    if not user_id or not department_id:
        return jsonify({"error": "user_id and department_id are required."}), 400

    target = db.session.get(User, user_id)
    if not target or not target.is_active:
        return jsonify({"error": "Employee not found or disabled."}), 404
    dept = db.session.get(Department, department_id)
    if not dept or not dept.is_active:
        return jsonify({"error": "Department not found or disabled."}), 404

    entry = db.session.query(StationRoster).filter_by(
        user_id=user_id, roster_date=roster_date
    ).first()
    if entry:
        entry.department_id = dept.id
        entry.assigned_by_id = actor.id
        entry.updated_at_utc = datetime.now(timezone.utc)
    else:
        entry = StationRoster(
            user_id=user_id, department_id=dept.id,
            roster_date=roster_date, assigned_by_id=actor.id,
        )
        db.session.add(entry)

    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.roster.assign", target=user_id,
                 details=f"{target.username} -> {dept.name} on {roster_date.isoformat()}")
    db.session.commit()
    return jsonify(_entry_dict(entry)), 200


@roster_bp.get("/roster")
@require_active_user
def list_roster():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    roster_date = _parse_date(request.args.get("date")) or _today()
    entries = db.session.query(StationRoster).filter_by(roster_date=roster_date).all()
    return jsonify([_entry_dict(r) for r in entries]), 200


@roster_bp.get("/roster/me")
@require_active_user
def my_station():
    """Today's station for the caller. Falls back to their home department
    if nobody explicitly rostered them (the common case on a normal day)."""
    actor = db.session.get(User, get_jwt_identity())
    entry = db.session.query(StationRoster).filter_by(
        user_id=actor.id, roster_date=_today()
    ).first()
    if entry:
        return jsonify({
            "department_id": entry.department_id,
            "department":    entry.department.name if entry.department else None,
            "is_rostered":   True,
        }), 200
    return jsonify({
        "department_id": actor.department_id,
        "department":    actor.department.name if actor.department else None,
        "is_rostered":   False,
    }), 200
