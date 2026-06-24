"""
items.py — Create, edit, and list inventory items.
Disable never delete — is_active=False removes from operational views.
Catalog changes (add / disable / enable) notify the owner via the notification dispatcher.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.notification import Notification, NotificationStatus, NotificationReferenceType
from app.models.role import Role
from app.services.stock import get_current_stock

items_bp = Blueprint("inv_items", __name__, url_prefix="/inventory/items")

CATEGORY_PACK_DEFAULTS = {
    "spirit":      {"pack_size": 750, "pack_unit": "ml"},
    "wine":        {"pack_size": 750, "pack_unit": "ml"},
    "beer":        {"pack_size": 1,   "pack_unit": None},
    "soda":        {"pack_size": 300, "pack_unit": "ml"},
    "mixer":       {"pack_size": 300, "pack_unit": "ml"},
    "honey":       {"pack_size": 1000, "pack_unit": "g"},
    "syrup":       {"pack_size": 1000, "pack_unit": "g"},
}

MANAGER_LEVEL = 5


def _require_manager(actor: User):
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    return None


def _notify_owner_catalog_change(actor_name: str, verb: str, item_name: str, dept_name: str):
    """Queue an informational notification to the owner about a catalog change."""
    owner = db.session.query(User).join(User.role).filter(
        Role.level >= 10, User.is_active == True
    ).first()
    if not owner:
        return
    body = f"{actor_name} {verb} '{item_name}' in {dept_name} inventory."
    notif = Notification(
        recipient_user_id=owner.id,
        reference_type=NotificationReferenceType.GENERAL.value,
        subject=f"Inventory catalog change: {item_name}",
        body=body,
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(notif)


@items_bp.get("/category-defaults")
@require_active_user
def get_category_defaults():
    """Known pack defaults per category — drives frontend auto-fill."""
    return jsonify(CATEGORY_PACK_DEFAULTS), 200


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
    try:
        reorder = max(0, float(data.get("reorder_level", "0")))
    except (ValueError, TypeError):
        return jsonify({"error": "reorder_level must be a non-negative number."}), 400
    watch_list  = bool(data.get("is_watch_list", False))
    staff_food  = bool(data.get("is_staff_food", False))
    tolerance   = data.get("tolerance_percent")
    category    = (data.get("category") or "").strip() or None
    pack_size   = data.get("pack_size")
    pack_unit   = (data.get("pack_unit") or "").strip() or None

    if not name or not unit or not dept_id:
        return jsonify({"error": "name, unit, and department_id are required"}), 400

    from app.models.department import Department
    dept = db.session.get(Department, dept_id)
    if not dept or not dept.is_active:
        return jsonify({"error": "Department not found or disabled."}), 404

    # Smart defaults: when category is set but pack_size isn't, apply known defaults
    if category and pack_size is None:
        defaults = CATEGORY_PACK_DEFAULTS.get(category.lower())
        if defaults:
            pack_size = pack_size or defaults["pack_size"]
            pack_unit = pack_unit or defaults["pack_unit"]

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
            category=category,
            pack_size=str(pack_size) if pack_size is not None else None,
            pack_unit=pack_unit,
        )
        db.session.add(item)

    AuditLog.log(actor=actor.username, action="inventory.item.create", target=name)
    dept_name = item.department.name if item.department else "unknown"
    _notify_owner_catalog_change(actor.username, "added", name, dept_name)
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
        if "category" in data:
            item.category = data["category"].strip() if data["category"] else None
        if "pack_size" in data:
            item.pack_size = str(data["pack_size"]) if data["pack_size"] is not None else None
        if "pack_unit" in data:
            item.pack_unit = data["pack_unit"].strip() if data["pack_unit"] else None

    AuditLog.log(actor=actor.username, action="inventory.item.edit", target=item.name)
    db.session.commit()

    return jsonify({"id": item.id, "name": item.name, "is_active": item.is_active}), 200


@items_bp.get("")
@require_active_user
def list_items():
    from app.services.trust import compute_trust_tier
    actor = db.session.get(User, get_jwt_identity())
    dept_filter       = request.args.get("department")
    include_disabled  = request.args.get("include_disabled", "false").lower() == "true"
    for_count         = request.args.get("for_count", "false").lower() == "true"

    q = (request.args.get("q") or "").strip()

    query = db.session.query(InventoryItem)
    if q:
        query = query.filter(InventoryItem.name.ilike(f"%{q}%"))
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
        row = {
            "id":             it.id,
            "name":           it.name,
            "unit":           it.unit,
            "department_id":  it.department_id,
            "is_active":      it.is_active,
            "current_stock":  str(stock),
            "reorder_level":  str(it.reorder_level),
            "below_reorder":  stock < it.reorder_level,
            "is_watch_list":  it.is_watch_list,
            "is_staff_food":  it.is_staff_food,
            "cost_per_unit":  str(it.cost_per_unit) if it.cost_per_unit is not None else None,
            "pack_size":      str(it.pack_size) if it.pack_size is not None else None,
            "pack_unit":      it.pack_unit,
            "category":       it.category,
        }
        if for_count:
            tier, reason = compute_trust_tier(it)
            row["trust_tier"]   = tier
            row["trust_reason"] = reason
        result.append(row)

    if for_count:
        from collections import Counter
        tier_counts = Counter(r["trust_tier"] for r in result)
        return jsonify({
            "summary": {
                "MUST_COUNT":     tier_counts.get("MUST_COUNT", 0),
                "QUICK_VERIFY":   tier_counts.get("QUICK_VERIFY", 0),
                "AUTO_CONFIRMED": tier_counts.get("AUTO_CONFIRMED", 0),
                "total":          len(result),
            },
            "items": result,
        }), 200

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
    AuditLog.log(actor=actor.username, action="inventory.item.disable", target=item.name)
    dept_name = item.department.name if item.department else "unknown"
    _notify_owner_catalog_change(actor.username, "deactivated", item.name, dept_name)
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
    AuditLog.log(actor=actor.username, action="inventory.item.enable", target=item.name)
    dept_name = item.department.name if item.department else "unknown"
    _notify_owner_catalog_change(actor.username, "re-enabled", item.name, dept_name)
    db.session.commit()
    return jsonify({"id": item.id, "is_active": True}), 200
