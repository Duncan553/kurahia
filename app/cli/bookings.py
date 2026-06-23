"""
cli/bookings.py — Bookings seed and maintenance commands.

flask bookings seed-resources         → villas + event field + water activities
flask bookings seed-sample            → sample bookings spanning past/present/future
flask bookings flag-no-shows          → sweep HELD/CONFIRMED past check-in → NO_SHOW
flask bookings release-holds          → auto-cancel HELD bookings > 24h old
flask bookings send-checkin-reminders → WhatsApp/SMS reminder to today's arrivals
"""
import uuid
from datetime import datetime, timezone, timedelta
import click
from flask import Blueprint
from app.extensions import db
from app.models.bookable_resource import BookableResource, ResourceType
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services.booking import flag_no_shows, release_expired_holds, compute_base_total

bookings_cli_bp = Blueprint("bookings", __name__)


@bookings_cli_bp.cli.command("seed-resources")
def seed_resources():
    """Seed the resort's bookable inventory: 3 villas, 1 event field, 2 water activities."""
    resources = [
        {"name": "Villa 1",    "resource_type": ResourceType.VILLA.value,          "base_price": "12000", "capacity": 4},
        {"name": "Villa 2",    "resource_type": ResourceType.VILLA.value,          "base_price": "15000", "capacity": 6},
        {"name": "Villa 3",    "resource_type": ResourceType.VILLA.value,          "base_price": "20000", "capacity": 8},
        {"name": "Event Field","resource_type": ResourceType.EVENT_VENUE.value,    "base_price": "50000", "capacity": 200},
        {"name": "Jetski A",   "resource_type": ResourceType.WATER_ACTIVITY.value, "base_price": "3000",  "capacity": 2},
        {"name": "Jetski B",   "resource_type": ResourceType.WATER_ACTIVITY.value, "base_price": "3000",  "capacity": 2},
    ]
    created = 0
    for r in resources:
        existing = db.session.query(BookableResource).filter_by(name=r["name"]).first()
        if existing:
            continue
        resource = BookableResource(
            name=r["name"],
            resource_type=r["resource_type"],
            base_price=r["base_price"],
            capacity=r.get("capacity"),
        )
        db.session.add(resource)
        created += 1

    db.session.commit()
    click.echo(f"Created {created} resource(s). ({len(resources) - created} already existed.)")


@bookings_cli_bp.cli.command("seed-sample")
def seed_sample():
    """Create sample bookings: past (checked-out), current (checked-in), future (confirmed)."""
    owner = db.session.query(User).filter_by(username="owner1").first()
    if not owner:
        click.echo("owner1 user not found — run flask seed first.")
        return

    villa = db.session.query(BookableResource).filter_by(
        resource_type=ResourceType.VILLA.value
    ).first()
    if not villa:
        click.echo("No villa resources found — run flask bookings seed-resources first.")
        return

    now = datetime.now(timezone.utc)
    samples = [
        {
            "guest_name": "Alice Kamau", "guest_phone": "+254711000001",
            "check_in_planned_utc": now - timedelta(days=5),
            "check_out_planned_utc": now - timedelta(days=2),
            "status": BookingStatus.CHECKED_OUT.value,
        },
        {
            "guest_name": "Bob Odhiambo", "guest_phone": "+254711000002",
            "check_in_planned_utc": now - timedelta(hours=12),
            "check_out_planned_utc": now + timedelta(days=2),
            "status": BookingStatus.CONFIRMED.value,
        },
        {
            "guest_name": "Carol Wanjiru", "guest_phone": "+254711000003",
            "check_in_planned_utc": now + timedelta(days=3),
            "check_out_planned_utc": now + timedelta(days=6),
            "status": BookingStatus.HELD.value,
        },
    ]
    created = 0
    for s in samples:
        idem = f"seed-booking-{s['guest_phone']}"
        if db.session.query(Booking).filter_by(idempotency_key=idem).first():
            continue
        base_total = compute_base_total(
            villa, s["check_in_planned_utc"], s["check_out_planned_utc"], 2
        )
        from decimal import Decimal
        b = Booking(
            resource_id=villa.id,
            guest_name=s["guest_name"],
            guest_phone=s["guest_phone"],
            number_of_guests=2,
            check_in_planned_utc=s["check_in_planned_utc"],
            check_out_planned_utc=s["check_out_planned_utc"],
            base_total=base_total,
            deposit_required=(base_total * Decimal("0.30")).quantize(Decimal("0.01")),
            status=s["status"],
            idempotency_key=idem,
            created_by_id=owner.id,
        )
        db.session.add(b)
        created += 1

    db.session.commit()
    click.echo(f"Created {created} sample booking(s).")


@bookings_cli_bp.cli.command("flag-no-shows")
def cli_flag_no_shows():
    """Sweep HELD/CONFIRMED past-check-in bookings → NO_SHOW."""
    count = flag_no_shows()
    db.session.commit()
    click.echo(f"Flagged {count} booking(s) as NO_SHOW.")


@bookings_cli_bp.cli.command("release-holds")
@click.option("--hours", default=24, show_default=True,
              help="Cancel HELD bookings older than this many hours.")
def cli_release_holds(hours):
    """Auto-cancel HELD bookings that exceeded their hold window."""
    count = release_expired_holds(window_hours=hours)
    db.session.commit()
    click.echo(f"Released {count} expired hold(s).")


@bookings_cli_bp.cli.command("send-checkin-reminders")
def cli_send_checkin_reminders():
    """Send CHECKIN_REMINDER to guests with confirmed bookings checking in today.

    Run daily via cron (e.g. 7 AM EAT):
      flask bookings send-checkin-reminders
    """
    from app.services.notifications.guest_notify import notify_guest, MessageType

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    # Find CONFIRMED bookings with check-in planned today
    bookings = db.session.query(Booking).filter(
        Booking.status == BookingStatus.CONFIRMED.value,
        Booking.check_in_planned_utc >= today_start,
        Booking.check_in_planned_utc < today_end,
    ).all()

    sent = 0
    for b in bookings:
        if not b.guest_phone:
            continue
        resource_name = "your room"
        if b.resource_id:
            res = db.session.get(BookableResource, b.resource_id)
            if res:
                resource_name = res.name
        channel, _ = notify_guest(b.guest_phone, MessageType.CHECKIN_REMINDER, {
            "resource": resource_name,
        })
        sent += 1
        click.echo(f"  {b.guest_name} ({b.guest_phone}) → {channel}")

    db.session.commit()
    click.echo(f"Sent {sent} check-in reminder(s) for {len(bookings)} booking(s).")
