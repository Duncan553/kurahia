"""
services/events.py — Event lifecycle, alert scheduling, inventory issuance.

Key decisions:
- schedule_event_alerts() is called on CONFIRMED and also on new assignments to a CONFIRMED event.
  This ensures staff assigned before or after confirmation all receive their alerts.
- cancel_event_notifications() flips QUEUED → FAILED (never deletes — history preserved).
- EVENT_ALLOCATION reason excludes judge ratio analysis automatically (not in CONSUMPTION_REASONS).
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.event import Event, EventStatus, VALID_EVENT_TRANSITIONS
from app.models.event_assignment import EventAssignment, AssignmentStatus, VALID_ASSIGNMENT_TRANSITIONS
from app.models.event_inventory_allocation import (
    EventInventoryAllocation, AllocationStatus, VALID_ALLOCATION_TRANSITIONS,
)
from app.models.event_stock_movement import EventStockMovement, EventMovementType
from app.models.stock_movement import StockMovement, MovementReason
from app.models.notification import (
    Notification, NotificationStatus, NotificationReferenceType,
)

# Alert offsets from event start
ALERT_OFFSETS = [
    (timedelta(days=7),   "[7 days]  "),
    (timedelta(days=3),   "[3 days]  "),
    (timedelta(days=1),   "[Tomorrow]"),
    (timedelta(hours=2),  "[2 hours] "),
]


# ── Event state machine ───────────────────────────────────────────────────────

def transition_event(event: Event, new_status: str) -> tuple[bool, str]:
    allowed = VALID_EVENT_TRANSITIONS.get(event.status, set())
    if new_status not in allowed:
        return False, (
            f"Cannot move event from {event.status} to {new_status}. "
            f"Allowed next states: {sorted(allowed) or 'none (terminal state)'}."
        )
    return True, ""


def transition_assignment(assignment: EventAssignment, new_status: str) -> tuple[bool, str]:
    allowed = VALID_ASSIGNMENT_TRANSITIONS.get(assignment.status, set())
    if new_status not in allowed:
        return False, (
            f"Cannot move assignment from {assignment.status} to {new_status}. "
            f"Allowed: {sorted(allowed) or 'none'}."
        )
    return True, ""


# ── Alert cascade ─────────────────────────────────────────────────────────────

def _alert_body(label: str, event: Event, assignment: EventAssignment) -> tuple[str, str]:
    """Generate (subject, body) for one alert tier."""
    date_str  = event.starts_at_utc.strftime("%d %b %Y %H:%M UTC")
    employee_name = assignment.employee.full_name if assignment.employee else "Staff"
    subject = f"{label} {event.title}"
    body = (
        f"Hi {employee_name}, "
        f"you are assigned as '{assignment.role_on_event}' at '{event.title}' "
        f"on {date_str}."
        + (f" Location: {event.location}." if event.location else "")
    )
    return subject, body


def schedule_event_alerts(event: Event, assignment: EventAssignment | None = None) -> int:
    """
    Create the 4-tier QUEUED notification cascade for:
      - one specific assignment (when a new assignment is added to a CONFIRMED event), OR
      - all active assignments (when the event reaches CONFIRMED).
    Returns number of notifications created.
    """
    targets = [assignment] if assignment else list(
        event.assignments.filter_by(status=AssignmentStatus.ASSIGNED.value).all()
        + list(event.assignments.filter_by(status=AssignmentStatus.ACKNOWLEDGED.value).all())
    )

    count = 0
    now = datetime.now(timezone.utc)
    for asgn in targets:
        if not asgn.employee or not asgn.employee.user_id:
            continue
        for offset, label in ALERT_OFFSETS:
            scheduled = event.starts_at_utc - offset
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            subject, body = _alert_body(label, event, asgn)
            idem = f"alert-{event.id}-{asgn.id}-{offset.total_seconds():.0f}"
            # Skip if already exists (idempotent on re-confirm)
            existing = db.session.query(Notification).filter_by(
                idempotency_key=idem
            ).first()
            if existing:
                continue
            notif = Notification(
                recipient_user_id=asgn.employee.user_id,
                reference_type=NotificationReferenceType.EVENT_ALERT.value,
                reference_id=event.id,
                subject=subject,
                body=body,
                status=NotificationStatus.QUEUED.value,
                scheduled_for_utc=scheduled,
                idempotency_key=idem,
            )
            db.session.add(notif)
            count += 1
    db.session.flush()
    return count


def cancel_event_notifications(event_id: str) -> int:
    """Flip all QUEUED notifications for this event to FAILED. Never deletes."""
    notifications = db.session.query(Notification).filter_by(
        reference_type=NotificationReferenceType.EVENT_ALERT.value,
        reference_id=event_id,
        status=NotificationStatus.QUEUED.value,
    ).all()
    for n in notifications:
        n.status = NotificationStatus.FAILED.value
        n.notes  = "event cancelled"
    count = len(notifications)
    db.session.flush()
    return count


def cancel_assignment_notifications(event_id: str, assignment_id: str) -> int:
    """Flip QUEUED alerts for a specific assignment to FAILED when reassigned/removed."""
    notifications = db.session.query(Notification).filter(
        Notification.reference_type == NotificationReferenceType.EVENT_ALERT.value,
        Notification.reference_id   == event_id,
        Notification.status         == NotificationStatus.QUEUED.value,
        Notification.idempotency_key.like(f"alert-{event_id}-{assignment_id}-%"),
    ).all()
    for n in notifications:
        n.status = NotificationStatus.FAILED.value
        n.notes  = "assignment cancelled"
    count = len(notifications)
    db.session.flush()
    return count


# ── Event inventory ───────────────────────────────────────────────────────────

def transition_allocation(alloc: EventInventoryAllocation,
                           new_status: str) -> tuple[bool, str]:
    allowed = VALID_ALLOCATION_TRANSITIONS.get(alloc.status, set())
    if new_status not in allowed:
        return False, (
            f"Cannot move allocation from {alloc.status} to {new_status}. "
            f"Allowed: {sorted(allowed) or 'none'}."
        )
    return True, ""


def issue_allocation(alloc: EventInventoryAllocation, actor_id: str) -> StockMovement:
    """
    Move PLANNED → ISSUED.
    Writes a StockMovement with reason=EVENT_ALLOCATION (excluded from judge ratios).
    """
    movement = StockMovement(
        item_id=alloc.inventory_item_id,
        change_amount=-alloc.allocated_quantity,   # leaving the main store
        reason=MovementReason.EVENT_ALLOCATION.value,
        actor_id=actor_id,
        idempotency_key=f"event-issue-{alloc.id}",
        notes=f"Event allocation issued for event {alloc.event_id}",
    )
    db.session.add(movement)
    db.session.flush()

    bridge = EventStockMovement(
        allocation_id=alloc.id,
        movement_id=movement.id,
        movement_type=EventMovementType.ISSUE.value,
    )
    db.session.add(bridge)

    alloc.status = AllocationStatus.ISSUED.value
    alloc.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    return movement


def return_allocation(alloc: EventInventoryAllocation,
                      return_qty: Decimal, actor_id: str) -> StockMovement:
    """
    Move ISSUED → RETURNED with a counter StockMovement (items back in the store).
    """
    movement = StockMovement(
        item_id=alloc.inventory_item_id,
        change_amount=return_qty,                  # positive → back into store
        reason=MovementReason.EVENT_ALLOCATION.value,
        actor_id=actor_id,
        idempotency_key=f"event-return-{alloc.id}",
        notes=f"Event allocation returned for event {alloc.event_id}",
    )
    db.session.add(movement)
    db.session.flush()

    bridge = EventStockMovement(
        allocation_id=alloc.id,
        movement_id=movement.id,
        movement_type=EventMovementType.RETURN.value,
    )
    db.session.add(bridge)

    alloc.status = AllocationStatus.RETURNED.value
    alloc.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    return movement


def get_event_inventory_reconciliation(event_id: str) -> list[dict]:
    """
    Per-event: allocated vs issued vs returned vs net consumed per item.
    Gaps (issued - returned < allocated) are flagged.
    """
    from app.services.stock import get_current_stock
    from decimal import Decimal as D
    from sqlalchemy import func

    allocations = db.session.query(EventInventoryAllocation).filter_by(
        event_id=event_id
    ).all()
    result = []
    for alloc in allocations:
        issued   = D("0")
        returned = D("0")
        for bridge in alloc.stock_movements.all():
            mv = db.session.get(StockMovement, bridge.movement_id)
            if mv:
                if bridge.movement_type == EventMovementType.ISSUE.value:
                    issued   += abs(D(str(mv.change_amount)))
                else:
                    returned += abs(D(str(mv.change_amount)))
        consumed = issued - returned
        result.append({
            "allocation_id":    alloc.id,
            "item_name":        alloc.inventory_item.name if alloc.inventory_item else None,
            "allocated":        str(alloc.allocated_quantity),
            "issued":           str(issued),
            "returned":         str(returned),
            "consumed":         str(consumed),
            "status":           alloc.status,
            "gap":              str(max(D(str(alloc.allocated_quantity)) - issued, D("0"))),
        })
    return result
