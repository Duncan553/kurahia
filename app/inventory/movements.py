"""
movements.py — Stock-out movements: spoilage, staff meals, sent-back plates.

All three endpoints share the same write pattern:
  1. Idempotency check
  2. Validate item exists and is active
  3. Write StockMovement (negative change_amount)
  4. Write AuditLog entry
  5. Commit atomically

The caller supplies a positive quantity; the service layer negates it.
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.user import User
from app.models.audit_log import AuditLog

movements_bp = Blueprint("inv_movements", __name__, url_prefix="/inventory/movements")

MANAGER_LEVEL = 5


def _write_movement(actor: User, item: InventoryItem, quantity_positive: Decimal,
                    reason: MovementReason, idempotency_key: str, notes: str = None):
    """
    Core write: creates a negative StockMovement for a stock-out event.
    Returns (movement, None) on success, (None, (json_error, status)) on duplicate/error.
    Must be called inside an active db session; caller commits.
    """
    # Idempotency: if key already exists, return the existing movement silently
    existing = db.session.query(StockMovement).filter_by(
        idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing, None

    movement = StockMovement(
        item_id=item.id,
        change_amount=-abs(quantity_positive),  # always negative for stock-out
        reason=reason.value,
        actor_id=actor.id,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    db.session.add(movement)
    return movement, None


def _parse_quantity(data: dict) -> tuple[Decimal | None, str | None]:
    """Returns (Decimal, None) or (None, error_string)."""
    raw = data.get("quantity")
    if raw is None:
        return None, "quantity is required"
    try:
        qty = Decimal(str(raw))
    except InvalidOperation:
        return None, "quantity must be a number"
    if qty <= 0:
        return None, "quantity must be positive"
    return qty, None


def _get_item(item_id: str) -> tuple:
    item = db.session.get(InventoryItem, item_id)
    if not item or not item.is_active:
        return None, (jsonify({"error": "Item not found or inactive."}), 404)
    return item, None


# ── Spoilage ──────────────────────────────────────────────────────────────────

@movements_bp.post("/spoilage")
@jwt_required()
def log_spoilage():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data = request.get_json(silent=True) or {}
    qty, err = _parse_quantity(data)
    if err:
        return jsonify({"error": err}), 400

    item, err = _get_item(data.get("item_id", ""))
    if err:
        return err

    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    with db.session.begin_nested():
        movement, _ = _write_movement(
            actor, item, qty, MovementReason.SPOILAGE, idem_key, data.get("notes")
        )

    db.session.commit()
    AuditLog.log(
        actor=actor.username, action="inventory.spoilage",
        target=item.name, details=f"qty={qty}",
    )
    db.session.commit()

    return jsonify({"movement_id": movement.id, "item": item.name, "quantity": str(qty)}), 201


# ── Staff meal ────────────────────────────────────────────────────────────────

@movements_bp.post("/staff-meal")
@jwt_required()
def log_staff_meal():
    """
    Staff meal draws from is_staff_food items only.
    Regular stock never decreases via this endpoint.
    """
    actor = db.session.get(User, get_jwt_identity())

    data = request.get_json(silent=True) or {}
    qty, err = _parse_quantity(data)
    if err:
        return jsonify({"error": err}), 400

    item, err = _get_item(data.get("item_id", ""))
    if err:
        return err

    if not item.is_staff_food:
        return jsonify({"error": "Staff meal can only draw from staff-food items."}), 400

    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    with db.session.begin_nested():
        movement, _ = _write_movement(
            actor, item, qty, MovementReason.STAFF_MEAL, idem_key, data.get("notes")
        )

    db.session.commit()
    AuditLog.log(
        actor=actor.username, action="inventory.staff_meal",
        target=item.name, details=f"qty={qty}",
    )
    db.session.commit()

    return jsonify({"movement_id": movement.id, "item": item.name, "quantity": str(qty)}), 201


# ── Sent-back ─────────────────────────────────────────────────────────────────

@movements_bp.post("/sent-back")
@jwt_required()
def log_sent_back():
    """A returned plate/order — removes from stock (it cannot be resold)."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data = request.get_json(silent=True) or {}
    qty, err = _parse_quantity(data)
    if err:
        return jsonify({"error": err}), 400

    item, err = _get_item(data.get("item_id", ""))
    if err:
        return err

    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    with db.session.begin_nested():
        movement, _ = _write_movement(
            actor, item, qty, MovementReason.SENT_BACK, idem_key, data.get("notes")
        )

    db.session.commit()
    AuditLog.log(
        actor=actor.username, action="inventory.sent_back",
        target=item.name, details=f"qty={qty}",
    )
    db.session.commit()

    return jsonify({"movement_id": movement.id, "item": item.name, "quantity": str(qty)}), 201
