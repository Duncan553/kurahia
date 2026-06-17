"""
pos/menu.py — Menu item CRUD + recipe management.
POST   /menu/items
PATCH  /menu/items/:id
POST   /menu/items/:id/disable
POST   /menu/items/:id/enable
GET    /menu/items
GET    /menu/items/:id/recipe
POST   /menu/items/:id/recipe  (set/replace)
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.menu_item import MenuItem, PrepStation
from app.models.recipe_line import RecipeLine
from app.models.inventory_item import InventoryItem
from app.models.department import Department
from app.models.user import User
from app.models.role import Role
from app.models.audit_log import AuditLog
from app.models.notification import Notification, NotificationStatus, NotificationReferenceType
from app.services.stock import get_current_stock

menu_bp = Blueprint("menu", __name__, url_prefix="/menu/items")

MANAGER_LEVEL = 5


def _notify_owner_menu_change(actor_name: str, verb: str, item_name: str):
    """Queue an informational notification to the owner about a menu catalog change."""
    owner = db.session.query(User).join(User.role).filter(
        Role.level >= 10, User.is_active == True
    ).first()
    if not owner:
        return
    db.session.add(Notification(
        recipient_user_id=owner.id,
        reference_type=NotificationReferenceType.GENERAL.value,
        subject=f"Menu catalog change: {item_name}",
        body=f"{actor_name} {verb} '{item_name}' from the menu.",
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    ))


def _require_manager(actor):
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can manage menu items."}), 403
    return None


@menu_bp.post("")
@require_active_user
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

    AuditLog.log(actor=actor.username, action="menu.item.create", target=name)
    _notify_owner_menu_change(actor.username, "added", name)
    db.session.commit()
    return jsonify({"id": item.id, "name": item.name, "price": str(item.price)}), 201


@menu_bp.patch("/<item_id>")
@require_active_user
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

    AuditLog.log(actor=actor.username, action="menu.item.edit", target=item.name)
    db.session.commit()
    return jsonify({"id": item.id, "name": item.name, "price": str(item.price)}), 200


@menu_bp.post("/<item_id>/disable")
@require_active_user
def disable_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    with db.session.begin_nested():
        item.is_active = False
    AuditLog.log(actor=actor.username, action="menu.item.disable", target=item.name)
    _notify_owner_menu_change(actor.username, "deactivated", item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": False}), 200


@menu_bp.post("/<item_id>/enable")
@require_active_user
def enable_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    with db.session.begin_nested():
        item.is_active = True
    AuditLog.log(actor=actor.username, action="menu.item.enable", target=item.name)
    _notify_owner_menu_change(actor.username, "re-enabled", item.name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": True}), 200


@menu_bp.get("")
@require_active_user
def list_menu_items():
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    dept_filter      = request.args.get("department")
    dept_name_filter = request.args.get("dept_name")

    query = db.session.query(MenuItem)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    if dept_filter:
        query = query.filter_by(department_id=dept_filter)
    if dept_name_filter:
        dept = db.session.query(Department).filter_by(name=dept_name_filter).first()
        if not dept:
            return jsonify([]), 200
        query = query.filter_by(department_id=dept.id)

    result = []
    for i in query.all():
        result.append({
            "id":            i.id,
            "name":          i.name,
            "price":         str(i.price),
            "category":      i.category,
            "prep_station":  i.prep_station,
            "department_id": i.department_id,
            "is_active":     i.is_active,
            **_compute_menu_item_cost_fields(i),
        })
    return jsonify(result), 200


def _compute_menu_item_cost_fields(item: MenuItem) -> dict:
    """
    Compute food_cost, gross_margin, food_cost_pct, in_stock from recipe lines.
    Returns all-None dict when the item has no recipe or any cost is missing.
    """
    lines = db.session.query(RecipeLine).filter_by(
        menu_item_id=item.id, is_active=True
    ).all()

    if not lines:
        return {"food_cost": None, "gross_margin": None, "food_cost_pct": None, "in_stock": None}

    food_cost = Decimal("0")
    all_have_cost = True
    in_stock = True

    for line in lines:
        inv = line.inventory_item
        if inv is None or inv.cost_per_unit is None:
            all_have_cost = False
        else:
            food_cost += Decimal(str(line.quantity)) * Decimal(str(inv.cost_per_unit))

        # Stock check: current_stock must cover this recipe's required quantity
        current = get_current_stock(inv.id if inv else line.inventory_item_id)
        if current < Decimal(str(line.quantity)):
            in_stock = False

    if not all_have_cost:
        return {"food_cost": None, "gross_margin": None, "food_cost_pct": None, "in_stock": in_stock}

    price = Decimal(str(item.price))
    gross_margin = price - food_cost
    food_cost_pct = (food_cost / price * 100) if price > 0 else None

    return {
        "food_cost":      str(food_cost.quantize(Decimal("0.01"))),
        "gross_margin":   str(gross_margin.quantize(Decimal("0.01"))),
        "food_cost_pct":  str(food_cost_pct.quantize(Decimal("0.01"))) if food_cost_pct is not None else None,
        "in_stock":       in_stock,
    }


# ── Recipe management ─────────────────────────────────────────────────────────

@menu_bp.get("/<item_id>/recipe")
@require_active_user
def get_recipe(item_id):
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404

    lines = db.session.query(RecipeLine).filter_by(
        menu_item_id=item_id, is_active=True
    ).all()

    return jsonify([{
        "id":                l.id,
        "inventory_item_id": l.inventory_item_id,
        "inventory_item_name": l.inventory_item.name if l.inventory_item else None,
        "quantity":          str(l.quantity),
        "unit":              l.unit,
    } for l in lines]), 200


@menu_bp.post("/<item_id>/recipe")
@require_active_user
def set_recipe(item_id):
    """
    Set/replace a menu item's recipe. Deactivates all previous lines and creates new ones.
    Auth: manager (level >= 5) OR head chef (level >= 5, dept=KITCHEN).
    Both map to role.level >= 5 — the head chef distinction is structural, not a separate check.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or head chef required."}), 403

    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404

    data = request.get_json(silent=True) or {}
    lines_data = data.get("lines", [])

    if not isinstance(lines_data, list):
        return jsonify({"error": "lines must be an array."}), 400

    # Validate all inventory items before writing anything
    parsed_lines = []
    for idx, ld in enumerate(lines_data):
        inv_id = ld.get("inventory_item_id")
        raw_qty = ld.get("quantity")
        if not inv_id or raw_qty is None:
            return jsonify({"error": f"Line {idx}: inventory_item_id and quantity required."}), 400
        try:
            qty = Decimal(str(raw_qty))
        except InvalidOperation:
            return jsonify({"error": f"Line {idx}: quantity must be a number."}), 400
        if qty <= 0:
            return jsonify({"error": f"Line {idx}: quantity must be positive."}), 400
        inv_item = db.session.get(InventoryItem, inv_id)
        if not inv_item or not inv_item.is_active:
            return jsonify({"error": f"Inventory item '{inv_id}' not found or inactive."}), 404
        parsed_lines.append((inv_item, qty))

    with db.session.begin_nested():
        # Deactivate existing recipe lines (append-only spirit — rows stay in DB)
        existing = db.session.query(RecipeLine).filter_by(
            menu_item_id=item_id, is_active=True
        ).all()
        for old_line in existing:
            old_line.is_active = False

        # Write new lines
        new_lines = []
        for inv_item, qty in parsed_lines:
            line = RecipeLine(
                menu_item_id=item_id,
                inventory_item_id=inv_item.id,
                quantity=qty,
                unit=inv_item.unit,
            )
            db.session.add(line)
            new_lines.append(line)

    AuditLog.log(
        actor=actor.username,
        action="menu.recipe.set",
        target=item.name,
        details=f"{len(new_lines)} lines",
    )
    db.session.commit()

    return jsonify({
        "menu_item_id": item_id,
        "lines":        len(new_lines),
    }), 201
