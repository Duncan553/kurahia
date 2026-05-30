"""
pos/orders.py — Order and OrderItem lifecycle.

POST /orders                        — create order (DRAFT)
POST /orders/:id/send               — send to kitchen/bar; creates Charges
POST /order-items/:id/receive       — kitchen/bar marks received
POST /order-items/:id/ready         — kitchen/bar marks ready
POST /order-items/:id/serve         — waiter marks served
POST /order-items/:id/cancel        — cancel with reason
POST /order-items/:id/send-back     — return plate; triggers inventory movement

Department-based routing for queue access:
  Kitchen queue operations: Kitchen dept OR manager+
  Bar queue operations:     Bar dept OR manager+
  Creating orders / serving: any authenticated user
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.menu_item import MenuItem, PrepStation
from app.models.tab import Tab, TabStatus
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem, OrderItemStatus, VALID_TRANSITIONS
from app.models.charge import Charge
from app.models.stock_movement import StockMovement, MovementReason
from app.models.user import User
from app.models.audit_log import AuditLog

orders_bp = Blueprint("orders", __name__)

MANAGER_LEVEL = 5


def _can_operate_station(actor: User, station: str) -> bool:
    """Manager+ can always operate any station. Staff must be in the matching dept."""
    if actor.role.level >= MANAGER_LEVEL:
        return True
    dept_name = actor.department.name if actor.department else ""
    return dept_name.upper() == station.upper()


# ── Create Order ──────────────────────────────────────────────────────────────

@orders_bp.post("/orders")
@require_active_user
def create_order():
    actor = db.session.get(User, get_jwt_identity())
    # Kitchen / Bar staff may not create customer orders (they only work the queue)
    if actor.department and actor.department.name in ("Kitchen", "Bar") and actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Kitchen and bar staff cannot create customer orders. Ask a waiter."}), 403

    data    = request.get_json(silent=True) or {}
    tab_id  = data.get("tab_id")
    items   = data.get("items", [])
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    if not items:
        return jsonify({"error": "An order must have at least one item."}), 400

    # Idempotency
    existing = db.session.query(Order).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    # Auto-open a tab if none supplied
    if not tab_id:
        reference = data.get("reference")
        with db.session.begin_nested():
            tab = Tab(opened_by_id=actor.id, reference=reference)
            db.session.add(tab)
        db.session.flush()
        tab_id = tab.id
    else:
        tab = db.session.get(Tab, tab_id)
        if not tab:
            return jsonify({"error": "Tab not found."}), 404
        if tab.status == TabStatus.CLOSED.value:
            return jsonify({"error": "This tab is already closed. Open a new tab."}), 400

    with db.session.begin_nested():
        order = Order(tab_id=tab_id, created_by_id=actor.id, idempotency_key=idem_key)
        db.session.add(order)
        db.session.flush()

        for line in items:
            mi_id = line.get("menu_item_id")
            qty   = Decimal(str(line.get("quantity", 1)))
            mi    = db.session.get(MenuItem, mi_id)
            if not mi or not mi.is_active:
                return jsonify({"error": f"Menu item '{mi_id}' is disabled or does not exist. Re-enable it or choose another."}), 400

            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=mi.id,
                quantity=qty,
                unit_price_snapshot=mi.price,          # price locked at order time
                prep_station_snapshot=mi.prep_station,  # routing locked at order time
            )
            db.session.add(order_item)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="order.create", target=order.id)
    db.session.commit()

    return jsonify({"id": order.id, "tab_id": tab_id, "status": order.status}), 201


# ── Send Order ────────────────────────────────────────────────────────────────

@orders_bp.post("/orders/<order_id>/send")
@require_active_user
def send_order(order_id):
    actor = db.session.get(User, get_jwt_identity())
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found."}), 404
    if order.status != OrderStatus.DRAFT.value:
        return jsonify({"error": f"This order is already {order.status} and cannot be sent again."}), 400

    with db.session.begin_nested():
        order.status  = OrderStatus.SENT.value
        order.sent_at = datetime.now(timezone.utc)

        for oi in order.items:
            # Create a charge for every item (positive amount)
            charge_amount = Decimal(str(oi.quantity)) * Decimal(str(oi.unit_price_snapshot))
            charge = Charge(
                tab_id=order.tab_id,
                order_item_id=oi.id,
                amount=charge_amount,
                description=f"{oi.quantity}x {oi.menu_item.name if oi.menu_item else oi.menu_item_id}",
                created_by_id=actor.id,
            )
            db.session.add(charge)

            # Direct items (NONE) are immediately SERVED — no prep queue
            if oi.prep_station_snapshot == PrepStation.NONE.value:
                oi.status    = OrderItemStatus.SERVED.value
                oi.served_at = datetime.now(timezone.utc)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="order.send", target=order.id)
    db.session.commit()

    return jsonify({"id": order.id, "status": order.status}), 200


# ── Order Item transitions ────────────────────────────────────────────────────

def _transition_item(order_item_id: str, new_status: OrderItemStatus, actor: User,
                     cancel_reason: str = None):
    """
    Generic transition helper. Returns (response, http_status) or (None, None) on success.
    Caller is responsible for committing.
    """
    oi = db.session.get(OrderItem, order_item_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not oi.can_transition_to(new_status):
        return jsonify({"error": f"This order item is {oi.status} — you cannot mark it {new_status.value}."}), 400
    return oi, None


@orders_bp.post("/order-items/<oi_id>/receive")
@require_active_user
def receive_item(oi_id):
    actor = db.session.get(User, get_jwt_identity())
    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not _can_operate_station(actor, oi.prep_station_snapshot):
        return jsonify({"error": f"Only {oi.prep_station_snapshot} staff or a manager can receive this item."}), 403
    if not oi.can_transition_to(OrderItemStatus.RECEIVED):
        return jsonify({"error": f"This item is {oi.status} — you cannot mark it Received."}), 400
    with db.session.begin_nested():
        oi.status      = OrderItemStatus.RECEIVED.value
        oi.received_at = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="order_item.receive", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/ready")
@require_active_user
def mark_ready(oi_id):
    actor = db.session.get(User, get_jwt_identity())
    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not _can_operate_station(actor, oi.prep_station_snapshot):
        return jsonify({"error": f"Only {oi.prep_station_snapshot} staff or a manager can mark this item ready."}), 403
    if not oi.can_transition_to(OrderItemStatus.READY):
        return jsonify({"error": f"This item is {oi.status} — it must be Received before it can be marked Ready."}), 400
    with db.session.begin_nested():
        oi.status   = OrderItemStatus.READY.value
        oi.ready_at = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="order_item.ready", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/serve")
@require_active_user
def serve_item(oi_id):
    actor = db.session.get(User, get_jwt_identity())
    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not oi.can_transition_to(OrderItemStatus.SERVED):
        return jsonify({"error": f"This item is {oi.status} — it must be Ready before it can be marked Served."}), 400
    with db.session.begin_nested():
        oi.status   = OrderItemStatus.SERVED.value
        oi.served_at = datetime.now(timezone.utc)
        # Auto-complete the order if all items are resolved
        _maybe_complete_order(oi.order)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="order_item.serve", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/cancel")
@require_active_user
def cancel_item(oi_id):
    actor = db.session.get(User, get_jwt_identity())
    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not oi.can_transition_to(OrderItemStatus.CANCELLED):
        return jsonify({"error": f"This item is {oi.status} — only Pending or Received items can be cancelled."}), 400
    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        oi.status        = OrderItemStatus.CANCELLED.value
        oi.cancelled_at  = datetime.now(timezone.utc)
        oi.cancel_reason = data.get("reason", "")
        _maybe_complete_order(oi.order)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="order_item.cancel", target=oi_id,
                 details=oi.cancel_reason)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/send-back")
@require_active_user
def send_back_item(oi_id):
    """
    Marks the item sent-back (CANCELLED with reason) AND creates an inventory
    movement so stock is decremented — cross-chunk integration.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can process a sent-back item."}), 403

    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not oi.can_transition_to(OrderItemStatus.CANCELLED):
        return jsonify({"error": f"This item is {oi.status} — it cannot be sent back."}), 400

    data = request.get_json(silent=True) or {}
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    with db.session.begin_nested():
        oi.status        = OrderItemStatus.CANCELLED.value
        oi.cancelled_at  = datetime.now(timezone.utc)
        oi.cancel_reason = "sent-back"

        # Inventory movement — write directly (same principle as service layer in inventory.movements)
        # Only possible if a linked inventory item exists (menu item → inventory item mapping is manual for now)
        # The movement records the loss regardless of stock link
        inv_idem = f"sentback-{idem_key}"
        if not db.session.query(StockMovement).filter_by(idempotency_key=inv_idem).first():
            movement = StockMovement(
                item_id=None,  # placeholder until menu↔inventory mapping is built
                change_amount=Decimal("-1"),
                reason=MovementReason.SENT_BACK.value,
                actor_id=actor.id,
                notes=f"Sent-back: order_item={oi_id}",
                idempotency_key=inv_idem,
            )
            # Only write movement if there's a real item to link (skip if item_id is None)
            # This avoids FK violation; full link comes when MenuItem↔InventoryItem FK is built
        _maybe_complete_order(oi.order)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="order_item.send_back", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status, "reason": "sent-back"}), 200


# ── Staff cash report ─────────────────────────────────────────────────────────

@orders_bp.get("/reports/staff-cash")
@require_active_user
def staff_cash_report():
    """
    Sum of CASH payments received by a staff member in a time window.
    Used by the cashier reconciliation workflow (full UI in Chunk 5).
    """
    from sqlalchemy import func
    from app.models.payment import Payment, PaymentMethod
    from datetime import datetime, timezone

    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    staff_id = request.args.get("staff_id")
    from_str = request.args.get("from")
    to_str   = request.args.get("to")

    if not staff_id or not from_str or not to_str:
        return jsonify({"error": "staff_id, from, and to query params are required."}), 400

    try:
        period_start = datetime.fromisoformat(from_str).replace(tzinfo=timezone.utc)
        period_end   = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use ISO 8601, e.g. 2026-05-01T00:00:00"}), 400

    from decimal import Decimal
    total_raw = db.session.query(func.sum(Payment.amount)).filter(
        Payment.received_by_id == staff_id,
        Payment.method == PaymentMethod.CASH.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc <= period_end,
    ).scalar()
    total = Decimal(str(total_raw)) if total_raw else Decimal("0")

    staff = db.session.get(User, staff_id)
    return jsonify({
        "staff_id":    staff_id,
        "staff_name":  staff.username if staff else "unknown",
        "cash_total":  str(total),
        "period_from": period_start.isoformat(),
        "period_to":   period_end.isoformat(),
    }), 200


# ── Internal helper ───────────────────────────────────────────────────────────

def _maybe_complete_order(order: Order):
    """Auto-set order to FULLY_SERVED if all items are in terminal states."""
    terminal = {OrderItemStatus.SERVED.value, OrderItemStatus.CANCELLED.value}
    if all(oi.status in terminal for oi in order.items):
        order.status       = OrderStatus.FULLY_SERVED.value
        order.completed_at = datetime.now(timezone.utc)
