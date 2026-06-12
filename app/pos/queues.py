"""
pos/queues.py — Kitchen and bar prep queues.
Returns PENDING + RECEIVED items, oldest first, with age in seconds.
Kitchen staff (Kitchen dept) or manager+ can see the kitchen queue.
Bar staff (Bar dept) or manager+ can see the bar queue.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.order import Order
from app.models.menu_item import PrepStation
from app.models.user import User

queues_bp = Blueprint("queues", __name__)

MANAGER_LEVEL = 5
ACTIVE_STATUSES = [OrderItemStatus.PENDING.value, OrderItemStatus.RECEIVED.value]


def _queue_for_station(station: str, actor: User):
    dept_name = actor.department.name if actor.department else ""
    if actor.role.level < MANAGER_LEVEL and dept_name.upper() != station:
        return None, (jsonify({"error": f"Only {station} staff or a manager can view the {station.lower()} queue."}), 403)

    now = datetime.now(timezone.utc)
    items = (
        db.session.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            OrderItem.prep_station_snapshot == station,
            OrderItem.status.in_(ACTIVE_STATUSES),
        )
        .order_by(OrderItem.created_at.asc())
        .all()
    )

    def _age(oi):
        ts = oi.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int((now - ts).total_seconds())

    return [
        {
            "order_item_id": oi.id,
            "order_id":      oi.order_id,
            "tab_reference": oi.order.tab.reference if oi.order and oi.order.tab else None,
            "menu_item":     oi.menu_item.name if oi.menu_item else None,
            "quantity":      str(oi.quantity),
            "status":        oi.status,
            "created_at":    oi.created_at.isoformat(),
            "age_seconds":   _age(oi),
            "ordered_by":    oi.order.created_by.username if oi.order and oi.order.created_by else None,
        }
        for oi in items
    ], None


@queues_bp.get("/kitchen/queue")
@require_active_user
def kitchen_queue():
    actor = db.session.get(User, get_jwt_identity())
    result, err = _queue_for_station(PrepStation.KITCHEN.value, actor)
    if err:
        return err
    return jsonify(result), 200


@queues_bp.get("/bar/queue")
@require_active_user
def bar_queue():
    actor = db.session.get(User, get_jwt_identity())
    result, err = _queue_for_station(PrepStation.BAR.value, actor)
    if err:
        return err
    return jsonify(result), 200
