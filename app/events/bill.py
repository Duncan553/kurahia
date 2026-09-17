"""
events/bill.py — an event's menu, buy list, and bill (HTTP only).

The rules are in app/services/event_menu.py. Every route here is manager and
above: planning an event's food and taking its money is the manager's job.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.utils.auth_decorators import require_active_user, require_clocked_in
from app.utils.money import parse_quantity
from app.models.user import User
from app.models.event import Event, EventStatus
from app.models.event_menu_line import EventMenuLine
from app.models.employee_profile import EmployeeProfile
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.audit_log import AuditLog
from app.services import event_menu as em
from app.pos.orders import sellable_error, sold_out_error, send_order_items
from app.events.core import events_bp

EDITABLE = (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value, EventStatus.IN_PROGRESS.value)


def _manager_and_event(event_id):
    """(actor, event, None) or (None, None, refusal)."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < em.MANAGER_LEVEL:
        return None, None, (jsonify({"error": "Manager or above required."}), 403)
    event = db.session.get(Event, event_id)
    if not event:
        return None, None, (jsonify({"error": "Event not found."}), 404)
    return actor, event, None


def _reannounce(event):
    """Once the kitchen has been told, a changed plan must reach it again."""
    if event.status in (EventStatus.CONFIRMED.value, EventStatus.IN_PROGRESS.value):
        db.session.flush()
        em.announce_menu(event)


def _open_line(event, line_id):
    line = db.session.get(EventMenuLine, line_id)
    if not line or line.event_id != event.id or not line.is_active:
        return None, (jsonify({"error": "Menu line not found."}), 404)
    if line.is_sent:
        return None, (jsonify({"error": "This line has gone to the kitchen and cannot be changed."}), 400)
    return line, None


@events_bp.get("/<event_id>/menu")
@require_active_user
def get_menu(event_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    lines = em.active_lines(event.id)
    return jsonify({"lines": [em.line_dict(l) for l in lines],
                    "totals": em.totals(lines),
                    "stock": em.stock_check(event)}), 200


@events_bp.post("/<event_id>/menu")
@require_active_user
def add_menu_line(event_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    if event.status not in EDITABLE:
        return jsonify({"error": f"This event is {event.status.lower()}; its menu is closed."}), 400
    data = request.get_json(silent=True) or {}
    qty, err = parse_quantity(data.get("quantity"), "Plates")
    if err:
        return jsonify({"error": err}), 400
    mi = db.session.get(MenuItem, data.get("menu_item_id"))
    if not mi:
        return jsonify({"error": "Menu item not found."}), 404
    not_sellable = sellable_error(mi)
    if not_sellable:
        return jsonify({"error": not_sellable}), 400
    discount = em.parse_discount(data.get("discount_per_unit"))
    if discount is None:
        return jsonify({"error": "Discount must be a number of shillings, 0 or more."}), 400
    reason = (data.get("discount_reason") or "").strip() or None
    no = em.discount_refusal(actor, Decimal(str(mi.price)), discount, reason)
    if no:
        return jsonify({"error": no[0]}), no[1]

    line = EventMenuLine(event_id=event.id, menu_item_id=mi.id, quantity=qty,
                         menu_price=mi.price, discount_per_unit=discount,
                         discount_reason=reason if discount else None,
                         discount_by_id=actor.id if discount else None,
                         created_by_id=actor.id)
    db.session.add(line)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="event.menu.add", target=line.id,
                 details=f"{event.title}: {em.plates(qty)} × {mi.name}, discount {em.money(discount)}")
    _reannounce(event)
    db.session.commit()
    return jsonify(em.line_dict(line)), 201


@events_bp.patch("/<event_id>/menu/<line_id>")
@require_active_user
def edit_menu_line(event_id, line_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    line, refused = _open_line(event, line_id)
    if refused:
        return refused
    data = request.get_json(silent=True) or {}
    if "quantity" in data:
        qty, err = parse_quantity(data["quantity"], "Plates")
        if err:
            return jsonify({"error": err}), 400
        line.quantity = qty
    if "discount_per_unit" in data or "discount_reason" in data:
        discount = em.parse_discount(data.get("discount_per_unit", line.discount_per_unit))
        if discount is None:
            return jsonify({"error": "Discount must be a number of shillings, 0 or more."}), 400
        reason = (data.get("discount_reason", line.discount_reason) or "").strip() or None
        no = em.discount_refusal(actor, Decimal(str(line.menu_price)), discount, reason)
        if no:
            return jsonify({"error": no[0]}), no[1]
        line.discount_per_unit = discount
        line.discount_reason = reason if discount else None
        line.discount_by_id = actor.id if discount else None
    line.updated_at_utc = datetime.now(timezone.utc)
    AuditLog.log(actor=actor.username, action="event.menu.edit", target=line.id,
                 details=f"qty={line.quantity} discount={line.discount_per_unit}")
    _reannounce(event)
    db.session.commit()
    return jsonify(em.line_dict(line)), 200


@events_bp.post("/<event_id>/menu/<line_id>/remove")
@require_active_user
def remove_menu_line(event_id, line_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    line, refused = _open_line(event, line_id)
    if refused:
        return refused
    line.is_active = False   # disabled, never deleted
    line.updated_at_utc = datetime.now(timezone.utc)
    AuditLog.log(actor=actor.username, action="event.menu.remove", target=line.id)
    _reannounce(event)
    db.session.commit()
    return jsonify({"id": line.id, "is_active": False}), 200


@events_bp.post("/<event_id>/buy-list")
@require_active_user
def buy_list(event_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    written = em.write_buy_list(event, actor)
    db.session.commit()
    return jsonify({"written": len(written), "stock": em.stock_check(event)}), 200


@events_bp.get("/<event_id>/bill")
@require_active_user
def get_bill(event_id):
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    return jsonify(em.bill_dict(event)), 200


@events_bp.post("/<event_id>/send")
@require_active_user
@require_clocked_in
def send_menu(event_id):
    """Send planned lines to the kitchen and bar as real orders on the event's bill."""
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    if event.status not in (EventStatus.CONFIRMED.value, EventStatus.IN_PROGRESS.value):
        return jsonify({"error": "Confirm the event before sending its menu to the kitchen."}), 400
    wanted = (request.get_json(silent=True) or {}).get("line_ids")
    lines = [l for l in em.active_lines(event.id, unsent_only=True)
             if not wanted or l.id in wanted]
    if not lines:
        return jsonify({"error": "Nothing left to send for this event."}), 400

    # The shelf alone is not enough: dishes already on the board have not taken
    # their stock yet. Same check the manager saw on the plan.
    short = [i for i in em.stock_check(event)["items"] if Decimal(i["short"]) > 0]
    if short:
        listing = ", ".join(f"{em.plates(i['short'])} {i['unit']} {i['name']}" for i in short)
        return jsonify({"error": f"Not enough in the store yet: {listing}. "
                                 f"Record the delivery, then send."}), 409

    for line in lines:
        mi = line.menu_item
        no = sellable_error(mi)
        if no:
            return jsonify({"error": no}), 400
        no = sold_out_error(mi, Decimal(str(line.quantity)))
        if no:
            return jsonify({"error": no}), 409

    tab = em.open_bill(event, actor)
    order = Order(tab_id=tab.id, created_by_id=actor.id,
                  idempotency_key=f"event-send-{uuid.uuid4()}")
    db.session.add(order)
    db.session.flush()
    for line in lines:
        oi = OrderItem(order_id=order.id, menu_item_id=line.menu_item_id, quantity=line.quantity,
                       unit_price_snapshot=line.charged_per_unit,
                       prep_station_snapshot=line.menu_item.prep_station,
                       notes=f"Event: {event.title}"[:200])
        db.session.add(oi)
        db.session.flush()
        line.order_item_id = oi.id
    db.session.flush()
    db.session.refresh(order)
    no = send_order_items(order, actor)
    if no:
        db.session.rollback()
        return jsonify({"error": no}), 400
    AuditLog.log(actor=actor.username, action="event.menu.send", target=order.id,
                 details=f"{event.title}: {len(lines)} line(s)")
    db.session.commit()
    return jsonify({"order_id": order.id, "lines_sent": len(lines), "bill": em.bill_dict(event)}), 200


@events_bp.get("/prep")
@require_active_user
def station_prep():
    """Upcoming confirmed events and what they will need from one station.

    Feeds the Events tab on the kitchen/bar board — the same tablet as counter
    orders, never the same list — so a station sees a wedding coming days
    before any dish is sent.
    """
    from datetime import timedelta
    from app.models.menu_item import PrepStation
    actor = db.session.get(User, get_jwt_identity())
    station = (request.args.get("station") or "").upper()
    if station not in (PrepStation.KITCHEN.value, PrepStation.BAR.value):
        return jsonify({"error": "station must be KITCHEN or BAR."}), 400
    dept = actor.department.name.upper() if actor.department else ""
    if actor.role.level < em.MANAGER_LEVEL and dept != station:
        return jsonify({"error": f"Only {station.lower()} staff or a manager can see this."}), 403

    horizon = datetime.now(timezone.utc) + timedelta(days=14)
    events = db.session.query(Event).filter(
        Event.status.in_((EventStatus.CONFIRMED.value, EventStatus.IN_PROGRESS.value)),
        Event.starts_at_utc <= horizon,
    ).order_by(Event.starts_at_utc).all()
    job = "KITCHEN" if station == PrepStation.KITCHEN.value else "BAR"
    rows = []
    for event in events:
        planned = [l for l in em.active_lines(event.id, unsent_only=True)
                   if l.menu_item.prep_station == station]
        rows.append({
            "event": em.board_event(event),
            "crew": [name for (name,) in db.session.query(EmployeeProfile.full_name).filter(
                         EmployeeProfile.user_id.in_([u.id for u in em.crew(event, job)]))],
            "planned": [{"name": l.menu_item.name, "plates": em.plates(l.quantity)} for l in planned],
        })
    return jsonify(rows), 200


@events_bp.post("/<event_id>/booking-fee")
@require_active_user
@require_clocked_in
def take_booking_fee(event_id):
    """Take the booking fee: opens the event's bill, then records the money
    through the ordinary payment endpoint — one payment path, not two."""
    from app.pos.payments import record_payment
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    if event.status not in (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value):
        return jsonify({"error": f"This event is {event.status.lower()}."}), 400
    em.open_bill(event, actor)
    db.session.commit()
    return record_payment(event.tab_id)


@events_bp.get("/<event_id>/cost-sheet")
@require_active_user
def get_cost_sheet(event_id):
    """What the event used, what it cost, and what it billed. Manager and above."""
    actor, event, refused = _manager_and_event(event_id)
    if refused:
        return refused
    return jsonify(em.cost_sheet(event)), 200
