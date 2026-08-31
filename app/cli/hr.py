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


# ── PIN resync ────────────────────────────────────────────────────────────────
#
# scripts/seed_realistic.py defines a PIN per staff account and prints all
# twelve at the end of a seed run. Eleven of those twelve did not actually open
# the door: the database was seeded by an earlier revision of that file and the
# PIN column was edited afterwards, so the script's own output became fiction
# while its password constant stayed correct.
#
# That is a documentation-vs-reality gap, the same shape as a cron entry naming
# a command that does not exist: everything looks right until somebody tries it.
# Re-running the seeder is NOT the fix — its first act is to wipe every table,
# and by now that means real bookings.
#
# This re-points the stored PINs at what the seed file says, so the two agree
# again. It changes credentials, so it is fenced hard: development only, staff
# only, never the owner.

# Owner PINs are deliberately excluded. The owner's account is the one that can
# see OWNER_PRIVATE data, and a convenience command must never be the thing that
# sets its credentials — even in dev, where habits are formed.
PIN_RESYNC_EXCLUDED_ROLES = {"owner"}


@hr_cli_bp.cli.command("resync-pins")
@click.option("--yes", is_flag=True, help="Confirm — this rewrites staff PINs.")
def resync_pins(yes):
    """DEV ONLY: reset staff PINs to the values in scripts/seed_realistic.py."""
    import os, re
    from flask import current_app

    # Guard 1: never outside development. A command that rewrites credentials to
    # values published in a checked-in script would be a backdoor in production.
    #
    # Gated on FLASK_ENV alone, NOT on DEBUG — this config runs with debug off
    # even in development (the dev server logs "Debug mode: off"), so requiring
    # DEBUG refused the one environment the command exists for.
    env = os.environ.get("FLASK_ENV", "")
    if env != "development":
        click.echo(f"Refused: resync-pins only runs with FLASK_ENV=development (got {env!r}).")
        raise SystemExit(1)

    # Guard 2: a development flag pointed at a production database is the case
    # guard 1 cannot see. Postgres here almost certainly means real data.
    db_url = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if db_url.startswith(("postgres://", "postgresql://")):
        click.echo("Refused: this is pointed at Postgres, which is the production database.")
        raise SystemExit(1)

    if not yes:
        click.echo("This rewrites staff PINs to the seed file's values.")
        click.echo("Re-run with --yes if that is what you want.")
        raise SystemExit(1)

    seed_path = "scripts/seed_realistic.py"
    if not os.path.exists(seed_path):
        click.echo(f"Refused: {seed_path} not found — nothing to resync from.")
        raise SystemExit(1)

    # The seed file is the source of truth for what the PIN *should* be.
    pairs = re.findall(
        r'\("([a-z.]+)",\s+"[^"]+",\s+"([a-z_]+)",\s+"[^"]+",\s+"(\d{4})"',
        open(seed_path).read(),
    )
    if not pairs:
        click.echo("Refused: could not read any accounts out of the seed file.")
        raise SystemExit(1)

    changed = ok = skipped = 0
    for username, role_key, pin in pairs:
        if role_key in PIN_RESYNC_EXCLUDED_ROLES:
            click.echo(f"  skip     {username} ({role_key} — excluded)")
            skipped += 1
            continue
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            click.echo(f"  absent   {username}")
            continue
        if u.check_pin(pin):
            click.echo(f"  already  {username}")
            ok += 1
            continue
        u.set_pin(pin)
        # A wrong PIN typed a few times leaves the account near lockout; clearing
        # the counter is part of making the account usable again, not cosmetic.
        if hasattr(u, "failed_attempts"):
            u.failed_attempts = 0
        click.echo(f"  RESET    {username} -> PIN now matches the seed file")
        changed += 1

    db.session.commit()
    click.echo(f"\nresync-pins: {changed} reset, {ok} already correct, {skipped} excluded.")
