"""
events/core.py — Event lifecycle, assignments, inventory allocations.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.event_type import EventType
from app.models.event import Event, EventStatus
from app.models.event_assignment import EventAssignment, AssignmentStatus
from app.models.event_inventory_allocation import EventInventoryAllocation, AllocationStatus
from app.models.inventory_item import InventoryItem
from app.models.employee_profile import EmployeeProfile
from app.models.audit_log import AuditLog
from app.services.events import (
    transition_event, transition_assignment, transition_allocation,
    schedule_event_alerts, cancel_event_notifications, cancel_assignment_notifications,
    issue_allocation, return_allocation, get_event_inventory_reconciliation,
)

events_bp = Blueprint("events_core", __name__, url_prefix="/events")

MANAGER_LEVEL   = 5
STAFF_LEVEL     = 1


def _event_dict(e: Event) -> dict:
    return {
        "id":             e.id,
        "title":          e.title,
        "event_type":     e.event_type.name if e.event_type else None,
        "booking_id":     e.booking_id,
        "starts_at":      e.starts_at_utc.isoformat(),
        "ends_at":        e.ends_at_utc.isoformat(),
        "expected_guests": e.expected_guests,
        "location":       e.location,
        "notes":          e.notes,
        "status":         e.status,
    }


def _assignment_dict(a: EventAssignment) -> dict:
    return {
        "id":           a.id,
        "event_id":     a.event_id,
        "employee_id":  a.employee_id,
        "employee_name": a.employee.full_name if a.employee else None,
        "role_on_event": a.role_on_event,
        "status":       a.status,
    }


def _alloc_dict(a: EventInventoryAllocation) -> dict:
    return {
        "id":                 a.id,
        "event_id":           a.event_id,
        "inventory_item_id":  a.inventory_item_id,
        "item_name":          a.inventory_item.name if a.inventory_item else None,
        "allocated_quantity": str(a.allocated_quantity),
        "notes":              a.notes,
        "status":             a.status,
    }


def _parse_dt(val: str) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── Event Types ───────────────────────────────────────────────────────────────

event_types_bp = Blueprint("event_types", __name__, url_prefix="/event-types")


@event_types_bp.get("")
@jwt_required()
def list_event_types():
    types = db.session.query(EventType).filter_by(is_active=True).all()
    return jsonify([{"id": t.id, "name": t.name} for t in types]), 200


@event_types_bp.post("")
@jwt_required()
def create_event_type():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required."}), 400
    if db.session.query(EventType).filter_by(name=name).first():
        return jsonify({"error": f"Event type '{name}' already exists."}), 409
    et = EventType(name=name)
    db.session.add(et)
    db.session.commit()
    return jsonify({"id": et.id, "name": et.name}), 201


@event_types_bp.post("/<type_id>/disable")
@jwt_required()
def disable_event_type(type_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    et = db.session.get(EventType, type_id)
    if not et:
        return jsonify({"error": "Event type not found."}), 404
    et.is_active = False
    db.session.commit()
    return jsonify({"id": et.id, "is_active": False}), 200


# ── Events ────────────────────────────────────────────────────────────────────

@events_bp.post("")
@jwt_required()
def create_event():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to create events."}), 403

    data    = request.get_json(silent=True) or {}
    title   = (data.get("title") or "").strip()
    type_id = data.get("event_type_id")
    idem    = data.get("idempotency_key") or str(uuid.uuid4())

    if not title:
        return jsonify({"error": "title is required."}), 400
    if not type_id:
        return jsonify({"error": "event_type_id is required."}), 400

    existing = db.session.query(Event).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify({**_event_dict(existing), "duplicate": True}), 200

    et = db.session.get(EventType, type_id)
    if not et or not et.is_active:
        return jsonify({"error": "Event type not found or disabled."}), 404

    starts = _parse_dt(data.get("starts_at_utc"))
    ends   = _parse_dt(data.get("ends_at_utc"))
    if not starts or not ends:
        return jsonify({"error": "starts_at_utc and ends_at_utc are required (ISO 8601)."}), 400
    if ends <= starts:
        return jsonify({"error": "ends_at_utc must be after starts_at_utc."}), 400

    event = Event(
        title=title, event_type_id=type_id,
        booking_id=data.get("booking_id"),
        starts_at_utc=starts, ends_at_utc=ends,
        expected_guests=int(data.get("expected_guests", 1)),
        location=data.get("location"),
        notes=data.get("notes"),
        created_by_id=actor.id,
        idempotency_key=idem,
    )
    db.session.add(event)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.create", target=event.id,
                 details=title)
    db.session.commit()
    return jsonify(_event_dict(event)), 201


@events_bp.patch("/<event_id>")
@jwt_required()
def edit_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    if event.status not in (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value):
        return jsonify({"error": "Only PLANNED or CONFIRMED events can be edited."}), 400

    data = request.get_json(silent=True) or {}
    if "title" in data:          event.title = data["title"].strip()
    if "location" in data:       event.location = data["location"]
    if "notes" in data:          event.notes = data["notes"]
    if "expected_guests" in data: event.expected_guests = int(data["expected_guests"])
    event.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(_event_dict(event)), 200


def _lifecycle_transition(event_id, new_status, actor, post_hook=None):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    ok, err = transition_event(event, new_status)
    if not ok:
        return jsonify({"error": err}), 400
    event.status = new_status
    event.updated_at_utc = datetime.now(timezone.utc)
    count = 0
    if post_hook:
        count = post_hook(event)
    db.session.commit()
    AuditLog.log(actor=actor.username, action=f"event.{new_status.lower()}", target=event_id)
    db.session.commit()
    resp = _event_dict(event)
    if count:
        resp["notifications_scheduled"] = count
    return jsonify(resp), 200


@events_bp.post("/<event_id>/confirm")
@jwt_required()
def confirm_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    # Idempotent: already confirmed → return current state, no new notifications
    if event.status == EventStatus.CONFIRMED.value:
        return jsonify(_event_dict(event)), 200
    return _lifecycle_transition(event_id, EventStatus.CONFIRMED.value, actor,
                                  post_hook=schedule_event_alerts)


@events_bp.post("/<event_id>/start")
@jwt_required()
def start_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    return _lifecycle_transition(event_id, EventStatus.IN_PROGRESS.value, actor)


@events_bp.post("/<event_id>/complete")
@jwt_required()
def complete_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    return _lifecycle_transition(event_id, EventStatus.COMPLETED.value, actor)


@events_bp.post("/<event_id>/cancel")
@jwt_required()
def cancel_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    ok, err = transition_event(event, EventStatus.CANCELLED.value)
    if not ok:
        return jsonify({"error": err}), 400

    event.status = EventStatus.CANCELLED.value
    event.updated_at_utc = datetime.now(timezone.utc)
    flipped = cancel_event_notifications(event_id)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.cancel", target=event_id)
    db.session.commit()
    return jsonify({**_event_dict(event), "notifications_cancelled": flipped}), 200


@events_bp.get("")
@jwt_required()
def list_events():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required."}), 403
    status = (request.args.get("status") or "").upper() or None
    from_s = request.args.get("from")
    to_s   = request.args.get("to")
    q = db.session.query(Event)
    if status:
        q = q.filter_by(status=status)
    if from_s:
        dt = _parse_dt(from_s)
        if dt:
            q = q.filter(Event.starts_at_utc >= dt)
    if to_s:
        dt = _parse_dt(to_s)
        if dt:
            q = q.filter(Event.starts_at_utc <= dt)
    return jsonify([_event_dict(e) for e in q.order_by(Event.starts_at_utc).all()]), 200


@events_bp.get("/upcoming")
@jwt_required()
def upcoming_events():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required."}), 403
    now = datetime.now(timezone.utc)
    events = db.session.query(Event).filter(
        Event.starts_at_utc >= now,
        Event.status.in_([EventStatus.PLANNED.value, EventStatus.CONFIRMED.value]),
    ).order_by(Event.starts_at_utc).limit(20).all()
    return jsonify([_event_dict(e) for e in events]), 200


@events_bp.get("/<event_id>")
@jwt_required()
def get_event(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required."}), 403
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    return jsonify(_event_dict(event)), 200


# ── Assignments ───────────────────────────────────────────────────────────────

@events_bp.post("/<event_id>/assignments")
@jwt_required()
def assign_employee(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    if event.status not in (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value):
        return jsonify({"error": "Can only assign staff to PLANNED or CONFIRMED events."}), 400

    data        = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    role_txt    = (data.get("role_on_event") or "").strip()
    if not employee_id or not role_txt:
        return jsonify({"error": "employee_id and role_on_event are required."}), 400

    profile = db.session.get(EmployeeProfile, employee_id)
    if not profile or not profile.is_active:
        return jsonify({"error": "Employee not found or inactive."}), 404

    assignment = EventAssignment(
        event_id=event_id, employee_id=employee_id,
        role_on_event=role_txt, notes=data.get("notes"),
        created_by_id=actor.id,
    )
    db.session.add(assignment)
    db.session.flush()

    notif_count = 0
    if event.status == EventStatus.CONFIRMED.value:
        notif_count = schedule_event_alerts(event, assignment)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.assign",
                 target=event_id, details=f"emp={employee_id} role={role_txt}")
    db.session.commit()
    resp = _assignment_dict(assignment)
    if notif_count:
        resp["notifications_scheduled"] = notif_count
    return jsonify(resp), 201


@events_bp.post("/<event_id>/assignments/<assignment_id>/acknowledge")
@jwt_required()
def acknowledge_assignment(event_id, assignment_id):
    actor = db.session.get(User, get_jwt_identity())
    assignment = db.session.get(EventAssignment, assignment_id)
    if not assignment or assignment.event_id != event_id:
        return jsonify({"error": "Assignment not found."}), 404

    # Employee can acknowledge their own; manager can acknowledge anyone's
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
    is_own = profile and profile.id == assignment.employee_id
    if not is_own and actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "You can only acknowledge your own assignment."}), 403

    ok, err = transition_assignment(assignment, AssignmentStatus.ACKNOWLEDGED.value)
    if not ok:
        return jsonify({"error": err}), 400
    assignment.status = AssignmentStatus.ACKNOWLEDGED.value
    assignment.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(_assignment_dict(assignment)), 200


@events_bp.post("/<event_id>/assignments/<assignment_id>/cancel")
@jwt_required()
def cancel_assignment(event_id, assignment_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    assignment = db.session.get(EventAssignment, assignment_id)
    if not assignment or assignment.event_id != event_id:
        return jsonify({"error": "Assignment not found."}), 404
    ok, err = transition_assignment(assignment, AssignmentStatus.CANCELLED.value)
    if not ok:
        return jsonify({"error": err}), 400
    assignment.status = AssignmentStatus.CANCELLED.value
    assignment.updated_at_utc = datetime.now(timezone.utc)
    cancel_assignment_notifications(event_id, assignment_id)
    db.session.commit()
    return jsonify(_assignment_dict(assignment)), 200


@events_bp.get("/<event_id>/assignments")
@jwt_required()
def list_assignments(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required."}), 403
    assignments = db.session.query(EventAssignment).filter_by(event_id=event_id).all()
    return jsonify([_assignment_dict(a) for a in assignments]), 200


# ── Inventory allocations ─────────────────────────────────────────────────────

@events_bp.post("/<event_id>/inventory/allocate")
@jwt_required()
def allocate_inventory(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    if event.status not in (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value):
        return jsonify({"error": "Can only allocate inventory for PLANNED or CONFIRMED events."}), 400

    data    = request.get_json(silent=True) or {}
    item_id = data.get("inventory_item_id")
    idem    = data.get("idempotency_key") or str(uuid.uuid4())

    existing = db.session.query(EventInventoryAllocation).filter_by(
        idempotency_key=idem
    ).first()
    if existing:
        return jsonify({**_alloc_dict(existing), "duplicate": True}), 200

    if not item_id:
        return jsonify({"error": "inventory_item_id is required."}), 400
    item = db.session.get(InventoryItem, item_id)
    if not item or not item.is_active:
        return jsonify({"error": "Inventory item not found or disabled."}), 404

    try:
        qty = Decimal(str(data.get("allocated_quantity", 0)))
        if qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return jsonify({"error": "allocated_quantity must be a positive number."}), 400

    alloc = EventInventoryAllocation(
        event_id=event_id, inventory_item_id=item_id,
        allocated_quantity=qty, notes=data.get("notes"),
        idempotency_key=idem, created_by_id=actor.id,
    )
    db.session.add(alloc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.inventory.allocate",
                 target=event_id, details=f"item={item_id} qty={qty}")
    db.session.commit()
    return jsonify(_alloc_dict(alloc)), 201


@events_bp.post("/<event_id>/inventory/<alloc_id>/issue")
@jwt_required()
def issue_inventory(event_id, alloc_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    alloc = db.session.get(EventInventoryAllocation, alloc_id)
    if not alloc or alloc.event_id != event_id:
        return jsonify({"error": "Allocation not found."}), 404
    ok, err = transition_allocation(alloc, AllocationStatus.ISSUED.value)
    if not ok:
        return jsonify({"error": err}), 400
    movement = issue_allocation(alloc, actor.id)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.inventory.issue",
                 target=alloc_id, details=f"movement={movement.id}")
    db.session.commit()
    return jsonify({**_alloc_dict(alloc), "movement_id": movement.id}), 200


@events_bp.post("/<event_id>/inventory/<alloc_id>/return")
@jwt_required()
def return_inventory(event_id, alloc_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    alloc = db.session.get(EventInventoryAllocation, alloc_id)
    if not alloc or alloc.event_id != event_id:
        return jsonify({"error": "Allocation not found."}), 404
    ok, err = transition_allocation(alloc, AllocationStatus.RETURNED.value)
    if not ok:
        return jsonify({"error": err}), 400

    data = request.get_json(silent=True) or {}
    try:
        return_qty = Decimal(str(data.get("return_quantity", alloc.allocated_quantity)))
        if return_qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return jsonify({"error": "return_quantity must be a positive number."}), 400

    movement = return_allocation(alloc, return_qty, actor.id)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="event.inventory.return",
                 target=alloc_id, details=f"qty={return_qty}")
    db.session.commit()
    return jsonify({**_alloc_dict(alloc), "return_movement_id": movement.id}), 200


@events_bp.post("/<event_id>/inventory/<alloc_id>/consume")
@jwt_required()
def consume_inventory(event_id, alloc_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    alloc = db.session.get(EventInventoryAllocation, alloc_id)
    if not alloc or alloc.event_id != event_id:
        return jsonify({"error": "Allocation not found."}), 404
    ok, err = transition_allocation(alloc, AllocationStatus.CONSUMED.value)
    if not ok:
        return jsonify({"error": err}), 400
    alloc.status = AllocationStatus.CONSUMED.value
    alloc.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(_alloc_dict(alloc)), 200


@events_bp.get("/<event_id>/inventory")
@jwt_required()
def list_inventory(event_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    allocs = db.session.query(EventInventoryAllocation).filter_by(event_id=event_id).all()
    recon  = get_event_inventory_reconciliation(event_id)
    return jsonify({"allocations": [_alloc_dict(a) for a in allocs],
                    "reconciliation": recon}), 200
