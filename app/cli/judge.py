"""
judge CLI logic — shared baseline seed function.
CLI commands are registered on judge_bp in app/judge/routes.py (one blueprint = one CLI group).
"""
import click
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.judge_baseline import JudgeBaseline

BASELINES = [
    # (item_name, business_driver, expected_ratio, driver_unit, tolerance_pct)
    ("Cooking Oil",   "restaurant_revenue", "0.05",  "per KSh 10k revenue", "25"),
    ("Chicken",       "restaurant_revenue", "0.5",   "per KSh 10k revenue", "20"),
    ("Rice",          "restaurant_revenue", "0.3",   "per KSh 10k revenue", "20"),
    ("Beer (Local)",  "bar_revenue",        "2.0",   "per KSh 1k revenue",  "20"),
    ("Beer (Import)", "bar_revenue",        "0.5",   "per KSh 1k revenue",  "25"),
    ("Whisky",        "bar_revenue",        "0.05",  "per KSh 1k revenue",  "30"),
]


def _seed_baselines():
    """Called by `flask judge seed-baselines`. Also usable in tests."""
    created = 0
    for item_name, driver, ratio, unit, tol in BASELINES:
        item = db.session.query(InventoryItem).filter_by(name=item_name).first()
        if not item:
            click.echo(f"  Skipping '{item_name}' — not found. Run flask inventory seed-items first.")
            continue
        if db.session.query(JudgeBaseline).filter_by(item_id=item.id, business_driver=driver).first():
            click.echo(f"  Exists: {item_name} / {driver}")
            continue
        db.session.add(JudgeBaseline(
            item_id=item.id, business_driver=driver,
            expected_ratio=ratio, driver_unit=unit, tolerance_percent=tol,
        ))
        created += 1
        click.echo(f"  Baseline: {item_name} — {ratio} {unit}")
    db.session.commit()
    click.echo(f"Done. {created} baselines created.")
