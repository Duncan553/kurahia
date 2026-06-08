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
from app.equipment.safety_templates import get_template

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
    check_items = data.get("check_items")

    if not isinstance(check_items, dict) or not check_items:
        return jsonify({"error": "check_items is required and must be a non-empty object."}), 400

    # Validate against the template for this equipment type
    template = get_template(eq.equipment_type)
    if template:
        missing = [k for k in template if k not in check_items]
        unchecked = [
            k for k in template
            if k in check_items and check_items[k].get("checked") is not True
        ]
        not_confirmed = missing + unchecked
        if not_confirmed:
            return jsonify({
                "error": (
                    f"Safety check failed. The following items are not confirmed: "
                    f"{not_confirmed}. All {len(template)} items must be checked "
                    f"before equipment can be used."
                )
            }), 400
    else:
        # Unknown type: all supplied items must be checked=true
        unchecked = [k for k, v in check_items.items()
                     if not isinstance(v, dict) or v.get("checked") is not True]
        if unchecked:
            return jsonify({
                "error": (
                    f"Safety check failed. The following items are not confirmed: "
                    f"{unchecked}. All items must be checked before equipment can be used."
                )
            }), 400

    check = SafetyCheck(
        equipment_id=eq_id,
        performed_by_id=actor.id,
        performed_at_utc=datetime.now(timezone.utc),
        passed=True,
        check_items=check_items,
    )
    db.session.add(check)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="equipment.safety_check",
                 target=eq_id, details="passed=True")
    db.session.commit()
    return jsonify({"id": check.id, "passed": True,
                    "equipment_status": eq.status}), 201


@equipment_bp.get("/checklist-templates/<equipment_type>")
@require_active_user
def get_checklist_template(equipment_type):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    template = get_template(equipment_type)
    if template is None:
        return jsonify({"error": f"No checklist template found for equipment type '{equipment_type}'."}), 404
    return jsonify({
        "equipment_type": equipment_type.strip().lower(),
        "items": template,
        "count": len(template),
    }), 200
