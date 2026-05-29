"""
cli/gate.py — Gate maintenance commands.

flask gate close-day        → forfeit all ACTIVE bands (run after resort closes)
flask gate seed-bands       → create sample bands for today (testing only)
"""
import click
from datetime import datetime, timezone
from flask import Blueprint
from app.extensions import db

gate_cli_bp = Blueprint("gate", __name__)


@gate_cli_bp.cli.command("close-day")
@click.option("--date", default=None, help="YYYY-MM-DD (defaults to today)")
@click.option("--actor", default="system", help="Username to log as actor")
def close_day(date, actor):
    """EOD sweep: forfeit all ACTIVE bands and run gate judge signals."""
    from app.services.gate import forfeit_day, check_gate_signals
    from app.models.user import User

    date_str = date or datetime.now(timezone.utc).date().isoformat()
    user = db.session.query(User).filter_by(username=actor).first()
    actor_id = user.id if user else db.session.query(User).first().id

    count, total_unused = forfeit_day(date_str, actor_id)
    alerts = check_gate_signals(date_str)
    db.session.commit()
    click.echo(f"Forfeited {count} band(s). Unused credit: {total_unused} KSh. "
               f"Judge alerts fired: {alerts}.")


@gate_cli_bp.cli.command("seed-bands")
@click.option("--count", default=3, show_default=True, help="Number of bands to seed")
def seed_bands(count):
    """Seed sample bands for today (development / testing only)."""
    from app.services.gate import issue_band
    from app.models.user import User

    actor = db.session.query(User).filter_by(username="owner1").first()
    if not actor:
        click.echo("owner1 not found — run flask seed first.")
        return

    created = 0
    for i in range(count):
        idem = f"seed-band-{i+1}"
        try:
            band = issue_band(
                actor_id=actor.id,
                method="CASH",
                mpesa_code=None,
                card_ref=None,
                idem_key=idem,
            )
            db.session.commit()
            created += 1
        except Exception:
            db.session.rollback()

    click.echo(f"Seeded {created} band(s) for today.")
