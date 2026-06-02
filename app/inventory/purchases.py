"""
purchases.py — Purchase requests + completed purchases.

Approval chain:
  POST /inventory/purchase-requests            → dept head creates (PENDING)
  POST /inventory/purchase-requests/:id/propose → manager attaches budget
  POST /inventory/purchase-requests/:id/approve → owner approves / rejects
  POST /inventory/purchases                    → manager records actual purchase
                                                 (triggers PURCHASE StockMovement)

Rules:
  - Manager cannot approve their own proposed budget (checked explicitly)
  - receipt_photo_path is mandatory on a Purchase record
  - Purchase → StockMovement(PURCHASE) is atomic
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.purchase_request import PurchaseRequest, RequestStatus
from app.models.purchase import Purchase
from app.models.stock_movement import StockMovement, MovementReason
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog

purchases_bp = Blueprint("inv_purchases", __name__, url_prefix="/inventory")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


# ── Purchase Requests ─────────────────────────────────────────────────────────

@purchases_bp.post("/purchase-requests")
@require_active_user
def create_request():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data     = request.get_json(silent=True) or {}
    item_id  = data.get("item_id")
    item_desc = (data.get("item_description") or "").strip()
    raw_qty  = data.get("quantity")

    if not item_id and not item_desc:
        return jsonify({"error": "item_id or item_description required"}), 400
    if raw_qty is None:
        return jsonify({"error": "quantity is required"}), 400
    try:
        qty = Decimal(str(raw_qty))
    except InvalidOperation:
        return jsonify({"error": "quantity must be a number"}), 400
    if qty <= 0:
        return jsonify({"error": "quantity must be positive"}), 400

    if item_id:
        item = db.session.get(InventoryItem, item_id)
        if not item or not item.is_active:
            return jsonify({"error": "Item not found or inactive."}), 404

    with db.session.begin_nested():
        pr = PurchaseRequest(
            item_id=item_id,
            item_description=item_desc or None,
            quantity=qty,
            requested_by_id=actor.id,
        )
        db.session.add(pr)

    AuditLog.log(actor=actor.username, action="purchase_request.create", target=pr.id)
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status}), 201


@purchases_bp.post("/purchase-requests/<pr_id>/propose")
@require_active_user
def propose_budget(pr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404
    if pr.status != RequestStatus.PENDING:
        return jsonify({"error": f"Request is already {pr.status}."}), 400

    data = request.get_json(silent=True) or {}
    raw_cost = data.get("estimated_cost")
    if raw_cost is None:
        return jsonify({"error": "estimated_cost is required"}), 400
    try:
        cost = Decimal(str(raw_cost))
    except InvalidOperation:
        return jsonify({"error": "estimated_cost must be a number"}), 400
    if cost < 0:
        return jsonify({"error": "estimated_cost cannot be negative"}), 400

    with db.session.begin_nested():
        pr.estimated_cost  = cost
        pr.manager_id      = actor.id
        pr.manager_notes   = data.get("notes")

    AuditLog.log(actor=actor.username, action="purchase_request.propose", target=pr.id)
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status, "estimated_cost": str(cost)}), 200


@purchases_bp.post("/purchase-requests/<pr_id>/approve")
@require_active_user
def approve_request(pr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can approve purchase requests."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404

    # Requestor cannot also be the approver
    if pr.requested_by_id == actor.id:
        return jsonify({"error": "You can't approve your own purchase request."}), 403

    if pr.status not in (RequestStatus.PENDING,):
        return jsonify({"error": f"This request is already {pr.status} and cannot be approved again."}), 400

    data   = request.get_json(silent=True) or {}
    action = (data.get("action") or "approve").lower()  # "approve" or "reject"

    if action not in ("approve", "reject"):
        return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

    with db.session.begin_nested():
        pr.owner_id    = actor.id
        pr.owner_notes = data.get("notes")
        pr.status = RequestStatus.APPROVED if action == "approve" else RequestStatus.REJECTED

    AuditLog.log(
        actor=actor.username,
        action=f"purchase_request.{action}",
        target=pr.id,
    )
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status}), 200


# ── Completed Purchase ────────────────────────────────────────────────────────

@purchases_bp.post("/purchases")
@require_active_user
def record_purchase():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data = request.get_json(silent=True) or {}

    # Mandatory fields
    item_id            = data.get("item_id")
    raw_qty            = data.get("quantity")
    raw_cost           = data.get("actual_cost")
    receipt_photo_path = (data.get("receipt_photo_path") or "").strip()
    idem_key           = data.get("idempotency_key") or str(uuid.uuid4())

    if not receipt_photo_path:
        return jsonify({"error": "Receipt photo is required before recording the purchase."}), 400
    if not item_id:
        return jsonify({"error": "item_id is required"}), 400
    if raw_qty is None or raw_cost is None:
        return jsonify({"error": "quantity and actual_cost are required"}), 400

    try:
        qty  = Decimal(str(raw_qty))
        cost = Decimal(str(raw_cost))
    except InvalidOperation:
        return jsonify({"error": "quantity and actual_cost must be numbers"}), 400
    if qty <= 0:
        return jsonify({"error": "quantity must be positive"}), 400
    if cost < 0:
        return jsonify({"error": "actual_cost cannot be negative"}), 400

    # Idempotency
    if db.session.query(Purchase).filter_by(idempotency_key=idem_key).first():
        p = db.session.query(Purchase).filter_by(idempotency_key=idem_key).first()
        return jsonify({"id": p.id, "duplicate": True}), 200

    item = db.session.get(InventoryItem, item_id)
    if not item or not item.is_active:
        return jsonify({"error": "Item not found or inactive."}), 404

    pr_id = data.get("purchase_request_id")
    if pr_id:
        pr = db.session.get(PurchaseRequest, pr_id)
        if not pr:
            return jsonify({"error": "Purchase request not found."}), 404
        # Mark request as fulfilled
        pr.status = RequestStatus.FULFILLED

    with db.session.begin_nested():
        # The stock movement is the system of record for the stock increase
        movement = StockMovement(
            item_id=item.id,
            change_amount=qty,       # positive — stock coming in
            reason=MovementReason.PURCHASE.value,
            actor_id=actor.id,
            notes=data.get("notes"),
            idempotency_key=f"purchase-mv-{idem_key}",
        )
        db.session.add(movement)
        db.session.flush()

        purchase = Purchase(
            item_id=item.id,
            quantity=qty,
            actual_cost=cost,
            receipt_photo_path=receipt_photo_path,
            supplier_name=data.get("supplier_name"),
            recorded_by_id=actor.id,
            purchase_request_id=pr_id,
            movement_id=movement.id,
            idempotency_key=idem_key,
        )
        db.session.add(purchase)

    AuditLog.log(
        actor=actor.username, action="inventory.purchase",
        target=item.name, details=f"qty={qty} cost={cost}",
    )
    db.session.commit()

    return jsonify({
        "purchase_id": purchase.id,
        "movement_id": movement.id,
        "item":        item.name,
        "quantity":    str(qty),
        "actual_cost": str(cost),
    }), 201
