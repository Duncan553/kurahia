"""
cli/events.py — Events seed and maintenance commands.

flask events seed-types      → seed default event types
flask events seed-sample     → create a sample event with assignments + allocations
flask events deliver-due     → dispatch due QUEUED notifications
flask events flag-incomplete → flag IN_PROGRESS events past their end time
"""
import uuid
import click
from datetime import datetime, timezone, timedelta
from flask import Blueprint
from app.extensions import db

events_cli_bp = Blueprint("events", __name__)


@events_cli_bp.cli.command("seed-types")
def seed_types():
    """Seed the five default event types."""
    from app.models.event_type import EventType
    names = ["WEDDING", "CORPORATE_DAY", "CONFERENCE", "PARTY", "OTHER"]
    created = 0
    for name in names:
        if not db.session.query(EventType).filter_by(name=name).first():
            db.session.add(EventType(name=name))
            created += 1
    db.session.commit()
    click.echo(f"Seeded {created} event type(s) ({len(names)-created} already existed).")


@events_cli_bp.cli.command("seed-sample")
def seed_sample():
    """Create a sample WEDDING event with one staff assignment and one inventory allocation."""
    from app.models.event_type import EventType
    from app.models.event import Event, EventStatus
    from app.models.event_assignment import EventAssignment
    from app.models.event_inventory_allocation import EventInventoryAllocation
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile
    from app.models.inventory_item import InventoryItem
    from decimal import Decimal

    owner = db.session.query(User).filter_by(username="owner1").first()
    if not owner:
        click.echo("owner1 not found — run flask seed first.")
        return

    et = db.session.query(EventType).filter_by(name="WEDDING").first()
    if not et:
        click.echo("WEDDING type not found — run flask events seed-types first.")
        return

    idem = "seed-sample-event-wedding-1"
    if db.session.query(Event).filter_by(idempotency_key=idem).first():
        click.echo("Sample event already exists.")
        return

    now = datetime.now(timezone.utc)
    event = Event(
        title="Sample Wedding — Kamau & Wanjiru",
        event_type_id=et.id,
        starts_at_utc=now + timedelta(days=10),
        ends_at_utc=now + timedelta(days=10, hours=8),
        expected_guests=150,
        location="Event Field",
        notes="Sample event for testing.",
        created_by_id=owner.id,
        idempotency_key=idem,
    )
    db.session.add(event)
    db.session.flush()

    profile = db.session.query(EmployeeProfile).first()
    if profile:
        asgn = EventAssignment(
            event_id=event.id, employee_id=profile.id,
            role_on_event="Lead Waiter", created_by_id=owner.id,
        )
        db.session.add(asgn)

    item = db.session.query(InventoryItem).first()
    if item:
        alloc = EventInventoryAllocation(
            event_id=event.id, inventory_item_id=item.id,
            allocated_quantity=Decimal("50"), notes="Sample allocation",
            idempotency_key=f"seed-alloc-{event.id}",
            created_by_id=owner.id,
        )
        db.session.add(alloc)

    db.session.commit()
    click.echo(f"Created sample event: {event.id}")


@events_cli_bp.cli.command("deliver-due")
def deliver_due_cmd():
    """Dispatch all QUEUED notifications whose scheduled time has passed."""
    from app.services.notifications.dispatcher import deliver_due
    results = deliver_due()
    db.session.commit()
    click.echo(
        f"Processed {results['total']} notification(s): "
        f"{results['delivered']} delivered, {results['failed']} failed."
    )


@events_cli_bp.cli.command("flag-incomplete")
def flag_incomplete():
    """Flag IN_PROGRESS events that are past their planned end time."""
    from app.models.event import Event, EventStatus
    from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    events = db.session.query(Event).filter_by(
        status=EventStatus.IN_PROGRESS.value
    ).all()
    flagged = 0
    for ev in events:
        end = ev.ends_at_utc
        if end and end.tzinfo:
            end = end.replace(tzinfo=None)
        if end and end < now_naive:
            alert = JudgeAlert(
                item_id=None,
                alert_type="EVENT_NOT_CLOSED",
                severity=AlertSeverity.MEDIUM.value,
                description=(
                    f"Event '{ev.title}' (id={ev.id}) is still IN_PROGRESS "
                    f"but was scheduled to end at {ev.ends_at_utc}. "
                    "Please complete or cancel it."
                ),
                period_start=now,
                period_end=now,
                status=AlertStatus.OPEN.value,
            )
            db.session.add(alert)
            flagged += 1
    db.session.commit()
    click.echo(f"Flagged {flagged} incomplete event(s).")
