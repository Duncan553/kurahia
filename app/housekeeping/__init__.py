"""
housekeeping/ — Villa cleaning task assignment and status tracking.

Endpoints:
  GET  /housekeeping/status         — list all rooms with current cleaning status
  POST /housekeeping/assign         — manager assigns a villa to a housekeeper
  POST /housekeeping/<id>/start     — housekeeper marks "cleaning started"
  POST /housekeeping/<id>/complete  — housekeeper marks "cleaning done"
  POST /housekeeping/<id>/inspect   — manager inspects and approves
  POST /housekeeping/<id>/flag      — flag issues (maintenance, missing items)

Auto-trigger: create_dirty_record() is called from the booking check-out
endpoint when a booking transitions to CHECKED_OUT.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.cleaning_status import (
    CleaningStatus, CleaningStatusEnum, VALID_CLEANING_TRANSITIONS,
)
from app.models.bookable_resource import BookableResource
from app.models.audit_log import AuditLog

housekeeping_bp = Blueprint("housekeeping", __name__, url_prefix="/housekeeping")

MANAGER_LEVEL = 5


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_hk_dept(actor: User) -> bool:
    """True if actor's department is villa/housekeeping. Three call sites in
    this file used to each inline this substring check — one shared source
    of truth now, so a department rename only needs updating in one place.
    Still a hardcoded name match rather than a DB-resident flag (invariant
    #10 in CLAUDE.md would ideally have this as owner-editable config, e.g.
    a Department.category column) — flagging as a real follow-up, not fixed
    here to avoid a schema change unrelated to the bug this was fixing."""
    dept_name = actor.department.name.lower() if actor.department else ""
    return any(k in dept_name for k in ("villa", "housekeep"))


def _status_dict(cs: CleaningStatus) -> dict:
    """Serialise a CleaningStatus row for JSON response."""
    return {
        "id":              cs.id,
        "resource_id":     cs.resource_id,
        "resource_name":   cs.resource.name if cs.resource else None,
        "status":          cs.status,
        "assigned_to_id":  cs.assigned_to_id,
        "assigned_to":     cs.assigned_to.username if cs.assigned_to else None,
        "assigned_at":     cs.assigned_at.isoformat() if cs.assigned_at else None,
        "completed_at":    cs.completed_at.isoformat() if cs.completed_at else None,
        "inspected_by_id": cs.inspected_by_id,
        "inspected_by":    cs.inspected_by.username if cs.inspected_by else None,
        "inspected_at":    cs.inspected_at.isoformat() if cs.inspected_at else None,
        "notes":           cs.notes,
        "is_flagged":      cs.is_flagged,
        "flag_reason":     cs.flag_reason,
        "created_at":      cs.created_at.isoformat() if cs.created_at else None,
        "updated_at":      cs.updated_at.isoformat() if cs.updated_at else None,
    }


def _transition_ok(current: str, target: str) -> tuple[bool, str]:
    """Validate cleaning status transition against the state machine."""
    allowed = VALID_CLEANING_TRANSITIONS.get(current, set())
    if target not in allowed:
        return False, f"Cannot move from {current} to {target}."
    return True, ""


def create_dirty_record(resource_id: str) -> CleaningStatus:
    """
    Auto-create a DIRTY cleaning status for a resource after checkout.
    Called from the booking check-out endpoint. Must be inside an active
    db session — caller commits.
    """
    record = CleaningStatus(
        resource_id=resource_id,
        status=CleaningStatusEnum.DIRTY.value,
    )
    db.session.add(record)
    return record


# ── GET /housekeeping/status — list all rooms with current cleaning status ──

@housekeeping_bp.get("/status")
@require_active_user
def list_status():
    """
    Returns the most recent cleaning record for each active villa/room.
    Visible to housekeeping dept (L1+) and managers (L5+).
    """
    actor = db.session.get(User, get_jwt_identity())

    # Housekeeping/villa dept staff (any level) or managers can view
    is_hk_dept = _is_hk_dept(actor)
    if actor.role.level < MANAGER_LEVEL and not is_hk_dept:
        return jsonify({"error": "Villa/housekeeping department or manager access required."}), 403

    # Get all active villa/room resources
    resources = db.session.query(BookableResource).filter_by(is_active=True).all()

    result = []
    for r in resources:
        # Most recent cleaning record for this resource
        latest = (
            db.session.query(CleaningStatus)
            .filter_by(resource_id=r.id)
            .order_by(CleaningStatus.created_at.desc())
            .first()
        )
        if latest:
            result.append(_status_dict(latest))
        else:
            # No cleaning record exists yet — show resource as having no status
            result.append({
                "id":              None,
                "resource_id":     r.id,
                "resource_name":   r.name,
                "status":          None,
                "assigned_to_id":  None,
                "assigned_to":     None,
                "assigned_at":     None,
                "completed_at":    None,
                "inspected_by_id": None,
                "inspected_by":    None,
                "inspected_at":    None,
                "notes":           None,
                "is_flagged":      False,
                "flag_reason":     None,
                "created_at":      None,
                "updated_at":      None,
            })

    return jsonify(result), 200


# ── POST /housekeeping/assign — manager assigns villa to housekeeper ────────

@housekeeping_bp.post("/assign")
@require_active_user
def assign():
    """Manager assigns a housekeeper to a cleaning task."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager access required to assign housekeepers."}), 403

    data = request.get_json(silent=True) or {}
    cleaning_id = data.get("cleaning_id")
    housekeeper_id = data.get("housekeeper_id")

    if not cleaning_id or not housekeeper_id:
        return jsonify({"error": "cleaning_id and housekeeper_id are required."}), 400

    record = db.session.get(CleaningStatus, cleaning_id)
    if not record:
        return jsonify({"error": "Cleaning record not found."}), 404

    housekeeper = db.session.get(User, housekeeper_id)
    if not housekeeper or not housekeeper.is_active:
        return jsonify({"error": "Housekeeper not found or inactive."}), 404

    record.assigned_to_id = housekeeper_id
    record.assigned_at = datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)

    db.session.flush()
    AuditLog.log(
        actor=actor.username, action="housekeeping.assign",
        target=cleaning_id,
        details=f"assigned {housekeeper.username} to {record.resource.name}",
    )
    db.session.commit()
    return jsonify(_status_dict(record)), 200


# ── POST /housekeeping/<id>/start — housekeeper starts cleaning ─────────────

@housekeeping_bp.post("/<cleaning_id>/start")
@require_active_user
def start_cleaning(cleaning_id):
    """Housekeeper marks cleaning as started (DIRTY → CLEANING)."""
    actor = db.session.get(User, get_jwt_identity())

    record = db.session.get(CleaningStatus, cleaning_id)
    if not record:
        return jsonify({"error": "Cleaning record not found."}), 404

    # The assigned housekeeper, a manager, or — if nobody's been assigned yet —
    # any housekeeping/villa-dept worker can self-claim it. Without this, a
    # freshly-dirtied room (auto-created with assigned_to_id=None on checkout)
    # had no working "Start Cleaning" path until a manager happened to assign it.
    is_hk_dept = _is_hk_dept(actor)
    can_self_claim = record.assigned_to_id is None and is_hk_dept
    if record.assigned_to_id != actor.id and actor.role.level < MANAGER_LEVEL and not can_self_claim:
        return jsonify({"error": "Only the assigned housekeeper or a manager can start cleaning."}), 403

    ok, err = _transition_ok(record.status, CleaningStatusEnum.CLEANING.value)
    if not ok:
        return jsonify({"error": err}), 400

    if can_self_claim:
        record.assigned_to_id = actor.id
    record.status = CleaningStatusEnum.CLEANING.value
    record.updated_at = datetime.now(timezone.utc)

    db.session.flush()
    AuditLog.log(
        actor=actor.username, action="housekeeping.start",
        target=cleaning_id,
        details=record.resource.name if record.resource else None,
    )
    db.session.commit()
    return jsonify(_status_dict(record)), 200


# ── POST /housekeeping/<id>/complete — housekeeper marks done ───────────────

@housekeeping_bp.post("/<cleaning_id>/complete")
@require_active_user
def complete_cleaning(cleaning_id):
    """Housekeeper marks cleaning as complete (CLEANING → CLEAN)."""
    actor = db.session.get(User, get_jwt_identity())

    record = db.session.get(CleaningStatus, cleaning_id)
    if not record:
        return jsonify({"error": "Cleaning record not found."}), 404

    # Only the assigned housekeeper or a manager can complete
    if record.assigned_to_id != actor.id and actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only the assigned housekeeper or a manager can complete cleaning."}), 403

    ok, err = _transition_ok(record.status, CleaningStatusEnum.CLEAN.value)
    if not ok:
        return jsonify({"error": err}), 400

    record.status = CleaningStatusEnum.CLEAN.value
    record.completed_at = datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)

    data = request.get_json(silent=True) or {}
    if data.get("notes"):
        record.notes = data["notes"][:500]

    db.session.flush()
    AuditLog.log(
        actor=actor.username, action="housekeeping.complete",
        target=cleaning_id,
        details=record.resource.name if record.resource else None,
    )
    db.session.commit()
    return jsonify(_status_dict(record)), 200


# ── POST /housekeeping/<id>/inspect — manager inspects ──────────────────────

@housekeeping_bp.post("/<cleaning_id>/inspect")
@require_active_user
def inspect(cleaning_id):
    """Manager inspects and approves a cleaned room (CLEAN → INSPECTED)."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager access required to inspect rooms."}), 403

    record = db.session.get(CleaningStatus, cleaning_id)
    if not record:
        return jsonify({"error": "Cleaning record not found."}), 404

    ok, err = _transition_ok(record.status, CleaningStatusEnum.INSPECTED.value)
    if not ok:
        return jsonify({"error": err}), 400

    record.status = CleaningStatusEnum.INSPECTED.value
    record.inspected_by_id = actor.id
    record.inspected_at = datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)

    data = request.get_json(silent=True) or {}
    if data.get("notes"):
        record.notes = data["notes"][:500]

    db.session.flush()
    AuditLog.log(
        actor=actor.username, action="housekeeping.inspect",
        target=cleaning_id,
        details=record.resource.name if record.resource else None,
    )
    db.session.commit()
    return jsonify(_status_dict(record)), 200


# ── POST /housekeeping/<id>/flag — flag issues ──────────────────────────────

@housekeeping_bp.post("/<cleaning_id>/flag")
@require_active_user
def flag_issue(cleaning_id):
    """Flag a room for issues (maintenance needed, missing items, etc.)."""
    actor = db.session.get(User, get_jwt_identity())

    record = db.session.get(CleaningStatus, cleaning_id)
    if not record:
        return jsonify({"error": "Cleaning record not found."}), 404

    # Any housekeeping staff or manager can flag
    is_hk_dept = _is_hk_dept(actor)
    if actor.role.level < MANAGER_LEVEL and not is_hk_dept:
        return jsonify({"error": "Villa/housekeeping department or manager access required."}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "reason is required when flagging an issue."}), 400

    record.is_flagged = True
    record.flag_reason = reason[:500]
    record.updated_at = datetime.now(timezone.utc)

    if data.get("notes"):
        record.notes = data["notes"][:500]

    db.session.flush()
    AuditLog.log(
        actor=actor.username, action="housekeeping.flag",
        target=cleaning_id,
        details=f"{record.resource.name}: {reason[:100]}",
    )
    db.session.commit()
    return jsonify(_status_dict(record)), 200
