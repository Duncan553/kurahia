"""
pos/menu.py — Menu item CRUD.
POST   /menu/items
PATCH  /menu/items/:id
POST   /menu/items/:id/disable
POST   /menu/items/:id/enable
GET    /menu/items
"""
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.menu_item import MenuItem, PrepStation
from app.models.department import Department
from app.models.user import User
from app.models.audit_log import AuditLog

menu_bp = Blueprint("menu", __name__, url_prefix="/menu/items")

MANAGER_LEVEL = 5


def _require_manager(actor):
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can manage menu items."}), 403
    return None


@menu_bp.post("")
@jwt_required()
def create_menu_item():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err

    data = request.get_json(silent=True) or {}
    name         = (data.get("name") or "").strip()
    raw_price    = data.get("price")
    category     = (data.get("category") or "").strip() or None
    station      = (data.get("prep_station") or PrepStation.NONE.value).upper()
    dept_id      = data.get("department_id")
    description  = data.get("description")

    if not name or raw_price is None or not dept_id:
        return jsonify({"error": "name, price, and department_id are required."}), 400
    if station not in PrepStation.__members__:
        return jsonify({"error": f"prep_station must be one of {list(PrepStation.__members__)}."}), 400
    try:
        price = Decimal(str(raw_price))
    except InvalidOperation:
        return jsonify({"error": "price must be a number."}), 400
    if price < 0:
        return jsonify({"error": "price cannot be negative."}), 400

    dept = db.session.get(Department, dept_id)
    if not dept or not dept.is_active:
        return jsonify({"error": "Department not found or disabled."}), 404

    if db.session.query(MenuItem).filter_by(name=name, department_id=dept_id).first():
        return jsonify({"error": f"A menu item named '{name}' already exists in this department."}), 409

    with db.session.begin_nested():
        item = MenuItem(name=name, price=price, category=category,
                        prep_station=station, department_id=dept_id, description=description)
        db.session.add(item)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="menu.item.create", target=name)
    db.session.commit()
    return jsonify({"id": item.id, "name": item.name, "price": str(item.price)}), 201


@menu_bp.patch("/<item_id>")
@jwt_required()
def edit_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404

    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        if "name" in data:
            item.name = data["name"].strip()
        if "price" in data:
            item.price = Decimal(str(data["price"]))
        if "category" in data:
            item.category = data["category"]
        if "prep_station" in data:
            item.prep_station = data["prep_station"].upper()
        if "description" in data:
            item.description = data["description"]

    db.session.commit()
    AuditLog.log(actor=actor.username, action="menu.item.edit", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "name": item.name, "price": str(item.price)}), 200


@menu_bp.post("/<item_id>/disable")
@jwt_required()
def disable_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    with db.session.begin_nested():
        item.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="menu.item.disable", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": False}), 200


@menu_bp.post("/<item_id>/enable")
@jwt_required()
def enable_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    with db.session.begin_nested():
        item.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="menu.item.enable", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": True}), 200


@menu_bp.get("")
@jwt_required()
def list_menu_items():
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    dept_filter      = request.args.get("department")

    query = db.session.query(MenuItem)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    if dept_filter:
        query = query.filter_by(department_id=dept_filter)

    return jsonify([
        {
            "id":           i.id,
            "name":         i.name,
            "price":        str(i.price),
            "category":     i.category,
            "prep_station": i.prep_station,
            "department_id": i.department_id,
            "is_active":    i.is_active,
        }
        for i in query.all()
    ]), 200
