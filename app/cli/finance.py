"""
cli/finance.py — Finance CLI commands.
`flask finance seed-budgets` — seeds starter monthly budgets for each active dept.
"""
import click
from datetime import datetime, timezone
from flask import Blueprint
from app.extensions import db
from app.models.budget import Budget
from app.models.department import Department
from app.models.user import User

finance_cli_bp = Blueprint("finance", __name__)

DEFAULT_BUDGET = "50000"   # KES 50,000 per department per month


@finance_cli_bp.cli.command("seed-budgets")
@click.option("--period", default=None, help="YYYY-MM period to seed (default: current month).")
def seed_budgets(period):
    """Seed default monthly budgets for all active departments."""
    if not period:
        period = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        click.echo(f"Invalid period '{period}'. Use YYYY-MM format.", err=True)
        return

    # Use the first owner user as the setter
    owner = db.session.query(User).join(User.role).filter(
        User.is_active == True
    ).order_by(User.id).first()
    if not owner:
        click.echo("No active user found. Run 'flask seed owner' first.", err=True)
        return

    depts = db.session.query(Department).filter_by(is_active=True).all()
    added = 0
    for dept in depts:
        exists = db.session.query(Budget).filter_by(
            department_id=dept.id, period=period
        ).first()
        if not exists:
            budget = Budget(
                department_id=dept.id,
                period=period,
                amount=DEFAULT_BUDGET,
                set_by_id=owner.id,
            )
            db.session.add(budget)
            added += 1

    db.session.commit()
    click.echo(f"seed-budgets: {added} budgets added for {period} "
               f"({len(depts) - added} already existed).")
