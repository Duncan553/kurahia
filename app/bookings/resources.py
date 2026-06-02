"""
bookings/resources.py — BookableResource CRUD.
Manager+ can create / edit / disable / enable.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.bookable_resource import BookableResource, ResourceType
from app.models.audit_log import AuditLog
from decimal import Decimal, InvalidOperation

resources_bp = Blueprint("bookings_resources", __name__, url_prefix="/bookable-resources")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


@resources_bp.post("")
@require_active_user
def create_resource():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to create resources."}), 403

    data    = request.get_json(silent=True) or {}
    name    = (data.get("name") or "").strip()
    rtype   = (data.get("resource_type") or "").upper()
    dept_id = data.get("department_id")

    if not name:
        return jsonify({"error": "name is required."}), 400
    if rtype not in ResourceType.__members__:
        return jsonify({"error": f"resource_type must be one of {list(ResourceType.__members__)}."}), 400

    try:
        base_price = Decimal(str(data.get("base_price", 0)))
    except InvalidOperation:
        return jsonify({"error": "base_price must be a number."}), 400

    capacity = data.get("capacity")
    if capacity is not None:
        try:
            capacity = int(capacity)
        except (ValueError, TypeError):
            return jsonify({"error": "capacity must be an integer."}), 400

    resource = BookableResource(
        name=name,
        resource_type=rtype,
        base_price=base_price,
        capacity=capacity,
        department_id=dept_id,
    )
    db.session.add(resource)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.resource.create",
                 details=f"{rtype} {name}")
    db.session.commit()
    return jsonify(_resource_dict(resource)), 201


@resources_bp.get("")
@require_active_user
def list_resources():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    rtype            = request.args.get("resource_type", "").upper() or None
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"

    query = db.session.query(BookableResource)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    if rtype:
        query = query.filter_by(resource_type=rtype)

    return jsonify([_resource_dict(r) for r in query.all()]), 200


@resources_bp.patch("/<resource_id>")
@require_active_user
def edit_resource(resource_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    resource = db.session.get(BookableResource, resource_id)
    if not resource:
        return jsonify({"error": "Resource not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        resource.name = data["name"].strip()
    if "capacity" in data:
        resource.capacity = int(data["capacity"]) if data["capacity"] is not None else None
    if "base_price" in data:
        if actor.role.level < OWNER_LEVEL:
            return jsonify({"error": "Only the owner can change resource pricing."}), 403
        try:
            resource.base_price = Decimal(str(data["base_price"]))
        except InvalidOperation:
            return jsonify({"error": "base_price must be a number."}), 400
    if "department_id" in data:
        resource.department_id = data["department_id"]

    resource.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.resource.edit", target=resource_id)
    db.session.commit()
    return jsonify(_resource_dict(resource)), 200


@resources_bp.post("/<resource_id>/disable")
@require_active_user
def disable_resource(resource_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    resource = db.session.get(BookableResource, resource_id)
    if not resource:
        return jsonify({"error": "Resource not found."}), 404
    resource.is_active = False
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.resource.disable", target=resource_id)
    db.session.commit()
    return jsonify({"id": resource.id, "is_active": False}), 200


@resources_bp.post("/<resource_id>/enable")
@require_active_user
def enable_resource(resource_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    resource = db.session.get(BookableResource, resource_id)
    if not resource:
        return jsonify({"error": "Resource not found."}), 404
    resource.is_active = True
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.resource.enable", target=resource_id)
    db.session.commit()
    return jsonify({"id": resource.id, "is_active": True}), 200


def _resource_dict(r: BookableResource) -> dict:
    return {
        "id":            r.id,
        "name":          r.name,
        "resource_type": r.resource_type,
        "capacity":      r.capacity,
        "base_price":    str(r.base_price),
        "department_id": r.department_id,
        "is_active":     r.is_active,
    }
