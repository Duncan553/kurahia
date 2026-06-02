"""
equipment/core.py — Equipment CRUD, maintenance log, safety checks.
service_due flag is derived at read time (never stored).
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.equipment import Equipment, MaintenanceLog, SafetyCheck, EquipmentStatus
from app.models.audit_log import AuditLog

equipment_bp = Blueprint("equipment_core", __name__, url_prefix="/equipment")

MANAGER_LEVEL = 5


def _eq_dict(e: Equipment) -> dict:
    return {
        "id":                   e.id,
        "name":                 e.name,
        "equipment_type":       e.equipment_type,
        "department_id":        e.department_id,
        "status":               e.status,
        "last_service_utc":     e.last_service_utc.isoformat() if e.last_service_utc else None,
        "service_interval_days": e.service_interval_days,
        "is_due_service":       e.is_due_service,
        "notes":                e.notes,
        "is_active":            e.is_active,
    }


@equipment_bp.post("")
@require_active_user
def create_equipment():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    eq_type = (data.get("equipment_type") or "").strip()
    if not name or not eq_type:
        return jsonify({"error": "name and equipment_type are required."}), 400
    eq = Equipment(
        name=name, equipment_type=eq_type,
        department_id=data.get("department_id"),
        service_interval_days=data.get("service_interval_days"),
        notes=data.get("notes"),
        created_by_id=actor.id,
    )
    db.session.add(eq)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.create", target=eq.id, details=name)
    db.session.commit()
    return jsonify(_eq_dict(eq)), 201


@equipment_bp.get("")
@require_active_user
def list_equipment():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    include_retired = request.args.get("include_retired", "false").lower() == "true"
    q = db.session.query(Equipment).filter_by(is_active=True)
    if not include_retired:
        q = q.filter(Equipment.status != EquipmentStatus.RETIRED.value)
    return jsonify([_eq_dict(e) for e in q.order_by(Equipment.name).all()]), 200


@equipment_bp.patch("/<eq_id>")
@require_active_user
def edit_equipment(eq_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    eq = db.session.get(Equipment, eq_id)
    if not eq or not eq.is_active:
        return jsonify({"error": "Equipment not found or disabled."}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data: eq.name = data["name"].strip()
    if "equipment_type" in data: eq.equipment_type = data["equipment_type"].strip()
    if "status" in data:
        if data["status"] not in EquipmentStatus.__members__:
            return jsonify({"error": f"status must be one of {list(EquipmentStatus.__members__)}."}), 400
        eq.status = data["status"]
    if "service_interval_days" in data: eq.service_interval_days = data["service_interval_days"]
    if "notes" in data: eq.notes = data["notes"]
    eq.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.edit", target=eq_id)
    db.session.commit()
    return jsonify(_eq_dict(eq)), 200


@equipment_bp.post("/<eq_id>/disable")
@require_active_user
def disable_equipment(eq_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    eq = db.session.get(Equipment, eq_id)
    if not eq:
        return jsonify({"error": "Equipment not found."}), 404
    eq.is_active = False
    eq.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.disable", target=eq_id)
    db.session.commit()
    return jsonify({"id": eq.id, "is_active": False}), 200


@equipment_bp.post("/<eq_id>/maintenance")
@require_active_user
def log_maintenance(eq_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    eq = db.session.get(Equipment, eq_id)
    if not eq or not eq.is_active:
        return jsonify({"error": "Equipment not found."}), 404
    data = request.get_json(silent=True) or {}
    try:
        performed_at = datetime.fromisoformat(data.get("performed_at_utc") or
                                               datetime.now(timezone.utc).isoformat())
        if performed_at.tzinfo is None:
            performed_at = performed_at.replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "performed_at_utc must be ISO 8601."}), 400
    cost = None
    if data.get("cost") is not None:
        try:
            cost = Decimal(str(data["cost"]))
        except InvalidOperation:
            return jsonify({"error": "cost must be a number."}), 400
    log = MaintenanceLog(
        equipment_id=eq_id,
        performed_by_id=actor.id,
        performed_at_utc=performed_at,
        notes=data.get("notes"),
        cost=cost,
    )
    db.session.add(log)
    # Update last service date
    existing = eq.last_service_utc
    if existing and existing.tzinfo is None:
        existing = existing.replace(tzinfo=timezone.utc)
    if not existing or performed_at > existing:
        eq.last_service_utc = performed_at
    eq.status = EquipmentStatus.ACTIVE.value
    eq.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.maintenance", target=eq_id)
    db.session.commit()
    return jsonify({"id": log.id, "equipment_id": eq_id,
                    "performed_at": log.performed_at_utc.isoformat()}), 201


@equipment_bp.post("/<eq_id>/safety-check")
@require_active_user
def log_safety_check(eq_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    eq = db.session.get(Equipment, eq_id)
    if not eq or not eq.is_active:
        return jsonify({"error": "Equipment not found."}), 404
    data = request.get_json(silent=True) or {}
    passed = data.get("passed")
    if passed is None:
        return jsonify({"error": "passed (true/false) is required."}), 400
    check = SafetyCheck(
        equipment_id=eq_id,
        performed_by_id=actor.id,
        performed_at_utc=datetime.now(timezone.utc),
        passed=bool(passed),
        checklist_notes=data.get("checklist_notes"),
    )
    db.session.add(check)
    if not passed:
        eq.status = EquipmentStatus.MAINTENANCE.value
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.safety_check",
                 target=eq_id, details=f"passed={passed}")
    db.session.commit()
    return jsonify({"id": check.id, "passed": check.passed,
                    "equipment_status": eq.status}), 201
