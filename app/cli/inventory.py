"""
CLI: flask inventory seed-items
Seeds a starter catalogue across Kitchen, Bar, Staff departments.
Run after `flask seed roles-depts` and `flask db upgrade`.
"""
import click
from flask import Blueprint
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.department import Department

inventory_cli_bp = Blueprint("inventory", __name__)

STARTER_ITEMS = [
    # (name, unit, dept_name, reorder_level, is_watch_list, is_staff_food)
    ("Cooking Oil",   "litre",  "Kitchen",        5.0,  True,  False),
    ("Onions",        "kg",     "Kitchen",       10.0,  False, False),
    ("Tomatoes",      "kg",     "Kitchen",       10.0,  False, False),
    ("Rice",          "kg",     "Kitchen",       20.0,  False, False),
    ("Chicken",       "kg",     "Kitchen",        5.0,  True,  False),
    ("Flour",         "kg",     "Kitchen",       10.0,  False, False),
    ("Salt",          "kg",     "Kitchen",        2.0,  False, False),
    ("Sugar",         "kg",     "Kitchen",        5.0,  False, False),
    ("Beer (Local)",  "bottle", "Bar",           24.0,  True,  False),
    ("Beer (Import)", "bottle", "Bar",           12.0,  True,  False),
    ("Whisky",        "litre",  "Bar",            2.0,  True,  False),
    ("Vodka",         "litre",  "Bar",            2.0,  True,  False),
    ("Wine (Red)",    "bottle", "Bar",            6.0,  False, False),
    ("Soda Water",    "crate",  "Bar",            2.0,  False, False),
    ("Staff Rice",    "kg",     "General",       10.0,  False, True),
    ("Staff Beans",   "kg",     "General",        5.0,  False, True),
    ("Staff Cabbage", "kg",     "General",        3.0,  False, True),
]


@inventory_cli_bp.cli.command("seed-items")
def seed_items():
    """Seed a starter inventory catalogue across departments."""
    # Cache dept lookups
    depts = {d.name: d for d in db.session.query(Department).all()}

    created = 0
    for name, unit, dept_name, reorder, watch, staff_food in STARTER_ITEMS:
        dept = depts.get(dept_name)
        if not dept:
            click.echo(f"  Skipping '{name}' — department '{dept_name}' not found.")
            continue
        exists = db.session.query(InventoryItem).filter_by(name=name, department_id=dept.id).first()
        if exists:
            click.echo(f"  Exists: {name}")
            continue
        item = InventoryItem(
            name=name, unit=unit, department_id=dept.id,
            reorder_level=str(reorder),
            is_watch_list=watch,
            is_staff_food=staff_food,
        )
        db.session.add(item)
        created += 1
        click.echo(f"  Created: {name} ({unit}) in {dept_name}")

    db.session.commit()
    click.echo(f"Done. {created} items created.")
