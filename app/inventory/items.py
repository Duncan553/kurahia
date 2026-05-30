"""
items.py — Create, edit, and list inventory items.
Disable never delete — is_active=False removes from operational views.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.stock import get_current_stock

items_bp = Blueprint("inv_items", __name__, url_prefix="/inventory/items")

MANAGER_LEVEL = 5


def _require_manager(actor: User):
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    return None


@items_bp.post("")
@require_active_user
def create_item():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err

    data = request.get_json(silent=True) or {}
    name        = (data.get("name") or "").strip()
    unit        = (data.get("unit") or "").strip()
    dept_id     = data.get("department_id")
    reorder     = data.get("reorder_level", "0")
    watch_list  = bool(data.get("is_watch_list", False))
    staff_food  = bool(data.get("is_staff_food", False))
    tolerance   = data.get("tolerance_percent")

    if not name or not unit or not dept_id:
        return jsonify({"error": "name, unit, and department_id are required"}), 400

    # Uniqueness enforced by DB constraint; return 409 on collision
    existing = db.session.query(InventoryItem).filter_by(name=name, department_id=dept_id).first()
    if existing:
        return jsonify({"error": "Item with this name already exists in this department."}), 409

    with db.session.begin_nested():
        item = InventoryItem(
            name=name, unit=unit, department_id=dept_id,
            reorder_level=str(reorder),
            is_watch_list=watch_list,
            is_staff_food=staff_food,
            tolerance_percent=str(tolerance) if tolerance is not None else None,
        )
        db.session.add(item)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="inventory.item.create", target=name)
    db.session.commit()

    return jsonify({"id": item.id, "name": item.name, "unit": item.unit}), 201


@items_bp.patch("/<item_id>")
@require_active_user
def edit_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err

    item = db.session.get(InventoryItem, item_id)
    if not item:
        return jsonify({"error": "Item not found."}), 404

    data = request.get_json(silent=True) or {}

    with db.session.begin_nested():
        if "name" in data:
            item.name = data["name"].strip()
        if "unit" in data:
            item.unit = data["unit"].strip()
        if "reorder_level" in data:
            item.reorder_level = str(data["reorder_level"])
        if "is_watch_list" in data:
            item.is_watch_list = bool(data["is_watch_list"])
        if "tolerance_percent" in data:
            item.tolerance_percent = str(data["tolerance_percent"]) if data["tolerance_percent"] is not None else None
        if "is_active" in data:
            item.is_active = bool(data["is_active"])

    db.session.commit()
    AuditLog.log(actor=actor.username, action="inventory.item.edit", target=item.name)
    db.session.commit()

    return jsonify({"id": item.id, "name": item.name, "is_active": item.is_active}), 200


@items_bp.get("")
@require_active_user
def list_items():
    actor = db.session.get(User, get_jwt_identity())
    dept_filter       = request.args.get("department")
    include_disabled  = request.args.get("include_disabled", "false").lower() == "true"

    query = db.session.query(InventoryItem)
    if not include_disabled:
        query = query.filter_by(is_active=True)

    # Managers see their own department; owners see everything
    if actor.role.level < 10 and actor.department_id:
        query = query.filter_by(department_id=actor.department_id)
    elif dept_filter:
        query = query.filter_by(department_id=dept_filter)

    items = query.all()
    result = []
    for it in items:
        stock = get_current_stock(it.id)
        result.append({
            "id":            it.id,
            "name":          it.name,
            "unit":          it.unit,
            "department_id": it.department_id,
            "is_active":     it.is_active,
            "current_stock": str(stock),
            "reorder_level": str(it.reorder_level),
            "below_reorder": stock < it.reorder_level,
            "is_watch_list": it.is_watch_list,
            "is_staff_food": it.is_staff_food,
        })

    return jsonify(result), 200


@items_bp.post("/<item_id>/disable")
@require_active_user
def disable_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(InventoryItem, item_id)
    if not item:
        return jsonify({"error": "Item not found."}), 404
    with db.session.begin_nested():
        item.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="inventory.item.disable", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": False}), 200


@items_bp.post("/<item_id>/enable")
@require_active_user
def enable_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(InventoryItem, item_id)
    if not item:
        return jsonify({"error": "Item not found."}), 404
    with db.session.begin_nested():
        item.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="inventory.item.enable", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": True}), 200
