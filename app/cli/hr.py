"""
cli/hr.py — HR seed commands.

flask hr seed-wifi    → adds 127.0.0.0/8 (dev/test) to WiFi allow-list
flask hr seed-shifts  → creates sample shifts for all active employees (tomorrow)
"""
import uuid
from datetime import datetime, timezone, timedelta
import click
from flask import Blueprint
from app.extensions import db
from app.models.wifi_allow_list import WiFiAllowList
from app.models.employee_profile import EmployeeProfile
from app.models.shift import Shift, ShiftStatus
from app.models.user import User

hr_cli_bp = Blueprint("hr", __name__)


@hr_cli_bp.cli.command("seed-wifi")
def seed_wifi():
    """Add localhost CIDR to WiFi allow-list (dev / test use)."""
    existing = db.session.query(WiFiAllowList).filter_by(ip_cidr="127.0.0.0/8").first()
    if existing:
        click.echo("WiFi entry 127.0.0.0/8 already exists — skipped.")
        return

    entry = WiFiAllowList(
        ssid="staff-dev-net",
        ip_cidr="127.0.0.0/8",
        label="Localhost (dev/test)",
    )
    db.session.add(entry)
    db.session.commit()
    click.echo(f"Created WiFi entry: {entry.id}  127.0.0.0/8")


@hr_cli_bp.cli.command("seed-shifts")
@click.option("--days-ahead", default=1, show_default=True,
              help="Schedule shifts this many days from today.")
def seed_shifts(days_ahead):
    """Create morning + evening shifts for every active employee."""
    profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    if not profiles:
        click.echo("No active employee profiles found. Run 'flask hr seed-wifi' first, "
                   "and create profiles via the API.")
        return

    target_day = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)

    morning_start = datetime(target_day.year, target_day.month, target_day.day, 7, 0)
    morning_end   = datetime(target_day.year, target_day.month, target_day.day, 15, 0)
    evening_start = datetime(target_day.year, target_day.month, target_day.day, 15, 0)
    evening_end   = datetime(target_day.year, target_day.month, target_day.day, 23, 0)

    created = 0
    for i, p in enumerate(profiles):
        # Alternate: even index → morning, odd index → evening
        start, end = (morning_start, morning_end) if i % 2 == 0 else (evening_start, evening_end)
        idem = f"seed-shift-{p.id}-{target_day.isoformat()}"

        existing = db.session.query(Shift).filter_by(idempotency_key=idem).first()
        if existing:
            continue

        shift = Shift(
            employee_id=p.id,
            scheduled_start_utc=start,
            scheduled_end_utc=end,
            role_on_shift=p.full_name,
            status=ShiftStatus.SCHEDULED.value,
            idempotency_key=idem,
        )
        db.session.add(shift)
        created += 1

    db.session.commit()
    click.echo(f"Created {created} shift(s) for {target_day.isoformat()}.")
