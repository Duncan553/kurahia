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
from app.utils.auth_decorators import require_active_user, require_clocked_in
from app.utils.money import parse_amount, parse_quantity
from app.extensions import db
from app.models.menu_item import MenuItem, PrepStation
from app.models.tab import Tab, TabStatus
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem, OrderItemStatus, VALID_TRANSITIONS
from app.models.charge import Charge
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.inventory_item import InventoryItem
from app.services.consumption import consume_order_item, reverse_consumption
from app.services.tax import rate_for_menu_item
from app.services.tab import check_band_credit

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
@require_clocked_in
def create_order():
    actor = db.session.get(User, get_jwt_identity())
    # Prep-station staff cannot create orders — they MAKE things, they don't sell
    # them. The separation is what stops the person cooking a dish from also
    # being the person who says it was ordered.
    #
    # Gated on the DEPARTMENT plus an explicit exemption for waiters, because
    # department alone was wrong: peter.mwendwa is a waiter assigned to the Bar,
    # which is an entirely normal posting, and he could not take a drinks order
    # at the bar he works at. A waiter is a waiter wherever they are standing.
    SERVING_ROLES = {"waiter"}
    prep_stations = {ps.value for ps in PrepStation if ps != PrepStation.NONE}
    if (actor.department and actor.department.name.upper() in prep_stations
            and actor.role.name not in SERVING_ROLES
            and actor.role.level < MANAGER_LEVEL):
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
        # Audited on the same terms as POST /tabs (app/pos/tabs.py), which logs
        # "tab.open" for the identical write. This path had no audit row at all
        # — and on a busy night MOST tabs are opened here, by a waiter starting
        # an order rather than opening a tab first. So most tab openings had no
        # trail, which is the opposite of how it looked.
        AuditLog.log(actor=actor.username, action="tab.open", target=tab.id,
                     details=f"ref={reference} (auto-opened with an order)")
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
            # `qty <= 0 or not qty.is_finite()` read fine and was wrong: the
            # comparison runs FIRST and Decimal('NaN') <= 0 raises, so a NaN
            # quantity was an unhandled 500. parse_quantity checks finite first.
            qty, err = parse_quantity(line.get("quantity", 1), "Quantity")
            if err:
                return jsonify({"error": err}), 400
            mi    = db.session.get(MenuItem, mi_id)
            if not mi:
                return jsonify({"error": f"Menu item '{mi_id}' not found."}), 404
            if not mi.is_active:
                return jsonify({"error": f"'{mi.name}' is disabled. Re-enable it or choose another."}), 400

            # Stock pre-check: warn if recipe ingredients are depleted
            from app.models.recipe_line import RecipeLine
            from app.services.stock import get_current_stock
            recipe_lines = db.session.query(RecipeLine).filter_by(
                menu_item_id=mi.id, is_active=True).all()
            for rl in recipe_lines:
                inv = db.session.get(InventoryItem, rl.inventory_item_id)
                if inv:
                    needed = inv.recipe_to_stock(Decimal(str(rl.quantity))) * qty
                    if get_current_stock(inv.id) < needed:
                        return jsonify({
                            "error": f"{mi.name} is sold out — {inv.name} stock is too low. "
                                     f"Check with the kitchen before ordering."
                        }), 409

            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=mi.id,
                quantity=qty,
                unit_price_snapshot=mi.price,
                prep_station_snapshot=mi.prep_station,
                notes=(line.get("notes") or "").strip()[:200] or None,
            )
            db.session.add(order_item)

    AuditLog.log(actor=actor.username, action="order.create", target=order.id)
    db.session.commit()

    return jsonify({"id": order.id, "tab_id": tab_id, "status": order.status}), 201


# ── Send Order ────────────────────────────────────────────────────────────────

@orders_bp.post("/orders/<order_id>/send")
@require_active_user
@require_clocked_in
def send_order(order_id):
    actor = db.session.get(User, get_jwt_identity())
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found."}), 404
    if order.status != OrderStatus.DRAFT.value:
        return jsonify({"error": f"This order is already {order.status} and cannot be sent again."}), 400

    # Band-tab credit ceiling: sum all charges for this send and check before committing
    total_new_charge = sum(
        Decimal(str(oi.quantity)) * Decimal(str(oi.unit_price_snapshot))
        for oi in order.items
    )
    ok, credit_err = check_band_credit(order.tab_id, total_new_charge)
    if not ok:
        return jsonify({"error": credit_err}), 400

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
                # Frozen per charge: rates change by statute, and a sale must
                # keep computing with the rate that applied when it was made.
                tax_rate_snapshot=rate_for_menu_item(oi.menu_item),
            )
            db.session.add(charge)

            # Direct items (NONE) are immediately SERVED — no prep queue.
            #
            # They must still consume their recipe HERE, because they never pass
            # through READY, which is the only other place consume_order_item is
            # called. Without this a spa treatment or a jet-ski ride deducted
            # NOTHING from stock — and worse, the "no recipe -> alert the head
            # chef" safety net inside consume_order_item never fired either, so
            # the gap was silent. Kitchen and bar were tracked; every direct
            # service department leaked.
            if oi.prep_station_snapshot == PrepStation.NONE.value:
                oi.status    = OrderItemStatus.SERVED.value
                oi.served_at = datetime.now(timezone.utc)
                consume_order_item(oi, actor)

    AuditLog.log(actor=actor.username, action="order.send", target=order.id)
    db.session.commit()

    return jsonify({"id": order.id, "status": order.status}), 200


def _reverse_charge(oi: OrderItem, actor: User):
    """
    Append-only money correction: a cancelled item gets a NEGATIVE charge
    mirroring its original, so the guest never pays for cancelled food.
    History stays frozen (original row untouched); balance is derived so it
    corrects itself. One reversal per item — the state machine blocks a second
    cancel, and the existing-reversal check is belt-and-braces on top.
    Mirrors the inventory side: send-back already wrote a negative
    StockMovement; this is the same pattern applied to money.
    """
    original = db.session.query(Charge).filter(
        Charge.order_item_id == oi.id, Charge.amount > 0).first()
    if not original:
        return  # never sent → no charge exists → nothing to reverse
    already = db.session.query(Charge).filter(
        Charge.order_item_id == oi.id, Charge.amount < 0).first()
    if already:
        return
    db.session.add(Charge(
        tab_id=original.tab_id,
        order_item_id=oi.id,
        amount=-original.amount,
        description=f"REVERSAL: {original.description}",
        created_by_id=actor.id,
        # The SAME rate as the charge being reversed, not today's. A refund of a
        # sale made at 16% removes 16% of tax even if the rate has since moved,
        # otherwise the VAT return would not net back to zero.
        tax_rate_snapshot=original.tax_rate_snapshot,
    ))


def _notify_waiter_ready(oi: OrderItem):
    """
    Kitchen/bar marked an item READY → ping the waiter who created the order.
    In-app delivery is immediate (waiter is on shift, tablet polls the inbox);
    Web Push fires best-effort on top. Called inside the caller's transaction.
    """
    from app.models.notification import Notification, NotificationStatus, NotificationChannel
    from app.services.notifications.webpush import push_to_user

    order = oi.order
    if not order or not order.created_by_id:
        return
    tab_ref   = order.tab.reference if order.tab and order.tab.reference else "Walk-in"
    item_name = oi.menu_item.name if oi.menu_item else "Item"
    body = f"{tab_ref}: {oi.quantity}x {item_name} is ready for pickup."

    db.session.add(Notification(
        recipient_user_id=order.created_by_id,
        reference_type="order_ready",
        reference_id=oi.id,
        subject=f"Order ready — {tab_ref}",
        body=body,
        status=NotificationStatus.DELIVERED.value,
        channel=NotificationChannel.IN_APP.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        sent_at_utc=datetime.now(timezone.utc),
        idempotency_key=f"order-ready-{oi.id}",
    ))
    push_to_user(order.created_by_id, f"Order ready — {tab_ref}", body, "order_ready")


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
@require_clocked_in
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
    AuditLog.log(actor=actor.username, action="order_item.receive", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/ready")
@require_active_user
@require_clocked_in
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
        _notify_waiter_ready(oi)
        consume_order_item(oi, actor)   # auto-deduct recipe ingredients
    AuditLog.log(actor=actor.username, action="order_item.ready", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/serve")
@require_active_user
@require_clocked_in
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
    AuditLog.log(actor=actor.username, action="order_item.serve", target=oi_id)
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/cancel")
@require_active_user
@require_clocked_in
def cancel_item(oi_id):
    actor = db.session.get(User, get_jwt_identity())
    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404
    if not oi.can_transition_to(OrderItemStatus.CANCELLED):
        return jsonify({"error": f"This item is {oi.status} — it cannot be cancelled."}), 400
    # READY items were already consumed — only a manager can cancel (triggers stock reversal)
    if oi.status == OrderItemStatus.READY.value and actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Items that are ready to serve can only be cancelled by a manager."}), 403
    # RECEIVED: kitchen has started — only manager can cancel
    elif oi.status == OrderItemStatus.RECEIVED.value:
        if actor.role.level < MANAGER_LEVEL:
            return jsonify({"error": "This item is already being prepared. Ask a manager to cancel."}), 403
    # PENDING: waiter who owns the order OR manager+
    elif oi.status == OrderItemStatus.PENDING.value:
        if actor.role.level < MANAGER_LEVEL and (not oi.order or oi.order.created_by_id != actor.id):
            return jsonify({"error": "Only the waiter who took this order or a manager can cancel it."}), 403
    data = request.get_json(silent=True) or {}
    # "Was this consumed?" — NOT "did it reach READY?".
    #
    # Prep items consume at READY, so ready_at is the right signal for them.
    # Direct-service (NONE) items consume at SEND, when they are set SERVED, and
    # never get a ready_at. Note the status check is essential: a NONE item that
    # is still PENDING has NOT been consumed yet, and reversing it would invent
    # stock that was never deducted.
    was_ready = (
        oi.ready_at is not None
        or (oi.prep_station_snapshot == PrepStation.NONE.value
            and oi.status == OrderItemStatus.SERVED.value)
    )
    with db.session.begin_nested():
        oi.status        = OrderItemStatus.CANCELLED.value
        oi.cancelled_at  = datetime.now(timezone.utc)
        oi.cancel_reason = data.get("reason", "")
        _reverse_charge(oi, actor)
        if was_ready:
            reverse_consumption(oi, actor)  # undo ingredient deduction
        _maybe_complete_order(oi.order)
    AuditLog.log(actor=actor.username, action="order_item.cancel", target=oi_id,
                 details=f"{oi.cancel_reason} (charge reversed{', stock reversed' if was_ready else ''})")
    db.session.commit()
    return jsonify({"id": oi.id, "status": oi.status}), 200


@orders_bp.post("/order-items/<oi_id>/send-back")
@require_active_user
@require_clocked_in
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
        _reverse_charge(oi, actor)
        # No stock reversal for send-back: ingredients were consumed on READY and the dish was
        # already plated and served. The loss is real. Only money is reversed, not stock.
        _maybe_complete_order(oi.order)

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
    # REFUNDED is terminal: a served item reversed by a manager still counts as resolved
    terminal = {OrderItemStatus.SERVED.value, OrderItemStatus.CANCELLED.value,
                OrderItemStatus.REFUNDED.value}
    if all(oi.status in terminal for oi in order.items):
        order.status       = OrderStatus.FULLY_SERVED.value
        order.completed_at = datetime.now(timezone.utc)


# ── Refund endpoint ───────────────────────────────────────────────────────────

@orders_bp.post("/order-items/<oi_id>/refund")
@require_active_user
@require_clocked_in
def refund_item(oi_id):
    """
    Manager-only: reverse the charge on a SERVED order item.
    This bypasses the normal state machine — SERVED is otherwise terminal.
    The ledger stays append-only: _reverse_charge() writes a negative Charge row;
    the original positive Charge row is never touched.
    """
    actor = db.session.get(User, get_jwt_identity())

    # Only managers (level >= 5) can issue refunds
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Only a manager or above can process a refund."}), 403

    data = request.get_json(silent=True) or {}

    # idempotency_key is required — enforces the caller to think about retries
    idem_key = data.get("idempotency_key")
    if not idem_key:
        return jsonify({"error": "idempotency_key is required."}), 400

    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "A reason is required to process a refund."}), 400

    oi = db.session.get(OrderItem, oi_id)
    if not oi:
        return jsonify({"error": "Order item not found."}), 404

    # Idempotency: already refunded → return success without re-applying
    if oi.status == OrderItemStatus.REFUNDED.value:
        return jsonify({
            "order_item_id": oi_id,
            "status":        "REFUNDED",
            "message":       "Refund processed. Charge reversed on tab.",
            "duplicate":     True,
        }), 200

    # Only SERVED items can be refunded — all other statuses are wrong state
    if oi.status != OrderItemStatus.SERVED.value:
        return jsonify({
            "error": (
                f"Only served items can be refunded. "
                f"This item is currently {oi.status}. "
                f"Use the cancel endpoint for items that have not yet been served."
            )
        }), 409

    with db.session.begin_nested():
        # Append a negative Charge — append-only ledger stays intact
        _reverse_charge(oi, actor)
        # Move item to terminal REFUNDED state
        oi.status        = OrderItemStatus.REFUNDED.value
        oi.cancel_reason = reason   # reuse this field for the refund reason
        # If all remaining items on the order are terminal, auto-complete the order
        _maybe_complete_order(oi.order)

    AuditLog.log(
        actor=actor.username,
        action="order_item.refund",
        target=oi_id,
        details=f"reason={reason} amount reversed",
    )
    db.session.commit()

    return jsonify({
        "order_item_id": oi_id,
        "status":        "REFUNDED",
        "message":       "Refund processed. Charge reversed on tab.",
    }), 200
