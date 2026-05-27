"""
counts.py — Physical stock counts.

On submit:
  1. Create StockCount (the snapshot / anchor for variance math)
  2. Compute current derived stock
  3. Create a COUNT StockMovement for the difference (reconciles the running total)

This ensures get_current_stock() always reflects the latest physical reality.
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.stock_count import StockCount, CountType
from app.models.stock_movement import StockMovement, MovementReason
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.stock import get_current_stock

counts_bp = Blueprint("inv_counts", __name__, url_prefix="/inventory/counts")

MANAGER_LEVEL = 5


@counts_bp.post("")
@jwt_required()
def submit_count():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can submit stock counts."}), 403

    data = request.get_json(silent=True) or {}
    item_id      = data.get("item_id", "")
    raw_amount   = data.get("counted_amount")
    count_type   = data.get("count_type", CountType.DAILY.value).upper()
    notes        = data.get("notes")
    idem_key     = data.get("idempotency_key") or str(uuid.uuid4())

    # Idempotency
    if db.session.query(StockCount).filter_by(idempotency_key=idem_key).first():
        existing = db.session.query(StockCount).filter_by(idempotency_key=idem_key).first()
        return jsonify({"id": existing.id, "duplicate": True}), 200

    if raw_amount is None:
        return jsonify({"error": "counted_amount is required"}), 400
    try:
        counted = Decimal(str(raw_amount))
    except InvalidOperation:
        return jsonify({"error": "counted_amount must be a number"}), 400
    if counted < 0:
        return jsonify({"error": "counted_amount cannot be negative"}), 400

    if count_type not in CountType.__members__:
        return jsonify({"error": f"count_type must be one of {list(CountType.__members__)}"}), 400

    item = db.session.get(InventoryItem, item_id)
    if not item or not item.is_active:
        return jsonify({"error": "This item is disabled or does not exist. Re-enable it or choose another."}), 404

    with db.session.begin_nested():
        # Snapshot record for variance anchoring
        count = StockCount(
            item_id=item.id,
            counted_amount=counted,
            actor_id=actor.id,
            count_type=count_type,
            notes=notes,
            idempotency_key=idem_key,
        )
        db.session.add(count)
        db.session.flush()  # get count.id before the movement references it

        # Reconcile derived stock with physical reality
        current = get_current_stock(item.id)
        adjustment = counted - current
        if adjustment != Decimal("0"):
            reconciliation = StockMovement(
                item_id=item.id,
                change_amount=adjustment,
                reason=MovementReason.COUNT.value,
                actor_id=actor.id,
                notes=f"Reconciliation for count {count.id}",
                idempotency_key=f"reconcile-{idem_key}",
            )
            db.session.add(reconciliation)

    db.session.commit()
    AuditLog.log(
        actor=actor.username, action="inventory.count",
        target=item.name, details=f"counted={counted} prior={current}",
    )
    db.session.commit()

    return jsonify({
        "id":            count.id,
        "item":          item.name,
        "counted":       str(counted),
        "prior_stock":   str(current),
        "adjustment":    str(adjustment if adjustment != Decimal("0") else Decimal("0")),
    }), 201
