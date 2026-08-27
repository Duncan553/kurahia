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
from app.models.menu_item import MenuItem, PrepStation, StockTracking
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


# WHO OWNS WHAT
#
# The split follows what the item IS, not which screen it lives on:
#
#   head chef -> what the resort MAKES in house. Kitchen dishes, and bar
#                cocktails and juices, with their recipes, ingredients and
#                prices. These are the things with a yield and a food cost, so
#                the person who designs them is the person who should price them.
#
#   manager   -> what the resort OFFERS as a service. Spa treatments, the pool
#                day pass, jet ski hire, guided walks — every department's
#                catalogue and its prices.
#
# This is a ROLE check, not a level check. head_chef sits at level 3, and so do
# front_desk and gate_lead — a plain `level >= 3` gate would hand menu pricing
# to the gate staff.
MENU_AUTHOR_ROLES = {"head_chef"}

# The stations the head chef makes things at.
CHEF_STATIONS = {PrepStation.KITCHEN.value, PrepStation.BAR.value}


def _can_manage_menu(actor, prep_station: str | None = None) -> bool:
    """May this person author this item?

    Manager and owner: anything. Head chef: only what is cooked or poured —
    a spa treatment is a service the manager sells, not a dish.

    prep_station None means "not station-specific" (e.g. listing), which the
    head chef is allowed to do.
    """
    if actor.role.level >= MANAGER_LEVEL:
        return True
    if actor.role.name not in MENU_AUTHOR_ROLES:
        return False
    return prep_station is None or str(prep_station).upper() in CHEF_STATIONS


def _require_manager(actor, prep_station: str | None = None):
    """Kept under its original name so every call site reads the same.

    Means "may author this item": a manager or owner for anything, the head chef
    for kitchen and bar.
    """
    if not _can_manage_menu(actor, prep_station):
        if actor.role.name in MENU_AUTHOR_ROLES:
            return jsonify({
                "error": "The head chef manages kitchen and bar items. "
                         "Spa, water and other services are set by a manager."
            }), 403
        return jsonify({
            "error": "Only the head chef, a manager or the owner can manage menu items."
        }), 403
    return None


@menu_bp.post("")
@require_active_user
def create_menu_item():
    actor = db.session.get(User, get_jwt_identity())
    data = request.get_json(silent=True) or {}
    # Authorised per station: the head chef makes kitchen and bar items, the
    # manager sells services. Checked after parsing because the station decides.
    if (err := _require_manager(actor, (data.get("prep_station") or PrepStation.NONE.value))):
        return err

    name         = (data.get("name") or "").strip()
    raw_price    = data.get("price")
    # Normalize category: strip whitespace + title-case so "mains", "MAINS", "Mains" are identical
    _raw_cat     = (data.get("category") or "").strip()
    category     = _raw_cat.title() if _raw_cat else None
    station      = (data.get("prep_station") or PrepStation.NONE.value).upper()
    dept_id      = data.get("department_id")
    description  = data.get("description")
    image_path   = (data.get("image_path") or "").strip() or None
    allergens    = data.get("allergens")       # optional, comma-separated string
    dietary_flags = data.get("dietary_flags")  # optional, comma-separated string

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
                        prep_station=station, department_id=dept_id,
                        description=description, image_path=image_path,
                        allergens=allergens, dietary_flags=dietary_flags)
        db.session.add(item)

    AuditLog.log(actor=actor.username, action="menu.item.create", target=name)
    _notify_owner_menu_change(actor.username, "added", name)
    db.session.commit()
    return jsonify({"id": item.id, "name": item.name, "price": str(item.price)}), 201


@menu_bp.patch("/<item_id>")
@require_active_user
def edit_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    # Gate on what this item IS, and on where it is being moved TO, so a chef
    # cannot reclassify a spa service into the kitchen to gain control of it.
    data_peek = request.get_json(silent=True) or {}
    for station in {item.prep_station, (data_peek.get("prep_station") or item.prep_station)}:
        if (err := _require_manager(actor, station)):
            return err

    data = request.get_json(silent=True) or {}
    # Capture what actually changed, so the audit log records old -> new rather
    # than just "someone edited this". A price is the most sensitive field on a
    # menu item: repricing is how margin quietly disappears, and "who dropped
    # the Tilapia to 900 and when" is unanswerable without the old value.
    changes: list[str] = []

    with db.session.begin_nested():
        if "name" in data:
            new_name = data["name"].strip()
            if new_name != item.name:
                changes.append(f"name {item.name!r} -> {new_name!r}")
            item.name = new_name
        if "price" in data:
            new_price = Decimal(str(data["price"]))
            if new_price < 0:
                return jsonify({"error": "Price cannot be negative."}), 400
            if new_price != Decimal(str(item.price)):
                changes.append(f"price {item.price} -> {new_price}")
            item.price = new_price
        if "category" in data:
            # Same normalization as create: strip + title-case
            _raw_cat = (data.get("category") or "").strip()
            item.category = _raw_cat.title() if _raw_cat else None
        if "prep_station" in data:
            item.prep_station = data["prep_station"].upper()
        if "stock_tracking" in data:
            want = str(data["stock_tracking"]).upper()
            if want not in StockTracking.__members__:
                return jsonify({
                    "error": f"stock_tracking must be one of "
                             f"{[m.value for m in StockTracking]}."
                }), 400
            # DIRECT is a claim about data, so it has to be true.
            if want == StockTracking.DIRECT.value and not (
                data.get("inventory_item_id") or item.inventory_item_id
            ):
                return jsonify({
                    "error": "DIRECT tracking needs inventory_item_id — the stock "
                             "item this sale draws down."
                }), 400
            if want != item.stock_tracking:
                changes.append(f"tracking {item.stock_tracking} -> {want}")
            item.stock_tracking = want
        if "inventory_item_id" in data:
            item.inventory_item_id = data["inventory_item_id"] or None
            # Linking a stock item is itself a statement of how this deducts,
            # unless a recipe already says something more specific.
            if item.inventory_item_id and "stock_tracking" not in data:
                has_recipe = db.session.query(RecipeLine).filter_by(
                    menu_item_id=item.id, is_active=True
                ).first() is not None
                if not has_recipe:
                    if item.stock_tracking != StockTracking.DIRECT.value:
                        changes.append(f"tracking {item.stock_tracking} -> DIRECT")
                    item.stock_tracking = StockTracking.DIRECT.value
        if "description" in data:
            item.description = data["description"]
        if "image_path" in data:
            item.image_path = data["image_path"]
        if "allergens" in data:
            item.allergens = data["allergens"]
        if "dietary_flags" in data:
            item.dietary_flags = data["dietary_flags"]

    AuditLog.log(actor=actor.username, action="menu.item.edit", target=item.name,
                 details="; ".join(changes) if changes else "no effective change")
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


def _reject_if_untracked(item):
    """An item may not go on sale until someone has said how it moves stock.

    UNTRACKED is not "consumes nothing" — it is "nobody has decided". SERVICE is
    the way to say a pool day pass legitimately consumes nothing, and it is a
    positive statement a person makes. Blocking only UNTRACKED is what keeps the
    rule enforceable: without the distinction this check would fire on every
    genuine service, staff would learn to route around it, and the real gaps
    (a jet ski that actually burns fuel) would leak behind the noise.
    """
    if item.stock_tracking == StockTracking.UNTRACKED.value:
        return jsonify({
            "error": (
                f"'{item.name}' has no stock tracking set, so selling it would not "
                f"move inventory. Set a recipe, link it to a stock item, or mark it "
                f"as a service that consumes nothing."
            )
        }), 400
    return None


@menu_bp.post("/<item_id>/enable")
@require_active_user
def enable_menu_item(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_manager(actor)):
        return err
    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"error": "Menu item not found."}), 404
    if (err := _reject_if_untracked(item)):
        return err
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

    q = (request.args.get("q") or "").strip()

    query = db.session.query(MenuItem)
    if q:
        query = query.filter(MenuItem.name.ilike(f"%{q}%"))
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
            "is_active":      i.is_active,
            "image_path":     i.image_path,
            "allergens":      i.allergens,
            "dietary_flags":  i.dietary_flags,
            **_compute_menu_item_cost_fields(i),
        })
    return jsonify(result), 200


@menu_bp.get("/categories")
@require_active_user
def list_categories():
    """Return distinct active menu item categories, sorted, for autocomplete."""
    from sqlalchemy import distinct
    rows = (
        db.session.query(distinct(MenuItem.category))
        .filter(MenuItem.is_active == True, MenuItem.category.isnot(None))
        .order_by(MenuItem.category)
        .all()
    )
    return jsonify({"categories": [r[0] for r in rows]}), 200


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
        recipe_qty = Decimal(str(line.quantity))
        if inv is None or inv.cost_per_unit is None:
            all_have_cost = False
        else:
            ruc = inv.recipe_unit_cost()
            food_cost += recipe_qty * ruc

        current = get_current_stock(inv.id if inv else line.inventory_item_id)
        stock_needed = inv.recipe_to_stock(recipe_qty) if inv else recipe_qty
        if current < stock_needed:
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


# ── Recipe templates ──────────────────────────────────────────────────────────

RECIPE_TEMPLATES = {
    "shot": [
        {"role": "spirit", "quantity": 30, "unit": "ml"},
    ],
    "cocktail": [
        {"role": "spirit", "quantity": 50, "unit": "ml"},
        {"role": "mixer",  "quantity": 200, "unit": "ml"},
        {"role": "garnish", "quantity": 1, "unit": "piece"},
    ],
    "mocktail": [
        {"role": "mixer",  "quantity": 200, "unit": "ml"},
        {"role": "mixer",  "quantity": 50, "unit": "ml"},
        {"role": "garnish", "quantity": 1, "unit": "piece"},
    ],
}


@menu_bp.get("/templates")
@require_active_user
def get_recipe_templates():
    """Starter recipe structures. GET /menu/items/templates?type=cocktail"""
    template_type = request.args.get("type", "").lower()
    if template_type and template_type in RECIPE_TEMPLATES:
        return jsonify({"type": template_type, "lines": RECIPE_TEMPLATES[template_type]}), 200
    return jsonify({"types": list(RECIPE_TEMPLATES.keys()), "templates": RECIPE_TEMPLATES}), 200


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
    # Recipes are the head chef's core job — this is what makes a sale
    # deduct the right stock, so the person who designs the dish writes it.
    if not _can_manage_menu(actor):
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

        # Writing a recipe IS the act of saying how this item moves stock, so the
        # tracking state must follow it. Without this, a correctly configured
        # item stayed UNTRACKED and the "untracked cannot be sold" block refused
        # to let it go live — every newly built item blocked despite being right.
        # Clearing the recipe hands it back to UNTRACKED unless a direct link
        # takes over, because at that point nobody has said how it deducts again.
        if new_lines:
            item.stock_tracking = StockTracking.RECIPE.value
        elif item.inventory_item_id:
            item.stock_tracking = StockTracking.DIRECT.value
        else:
            item.stock_tracking = StockTracking.UNTRACKED.value

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
