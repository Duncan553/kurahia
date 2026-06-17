"""
CLI: flask inventory seed-items / flask inventory auto-draft
Seeds a starter catalogue across Kitchen, Bar, Staff departments.
Auto-draft creates DRAFT purchase requests for items below reorder level.
Run after `flask seed roles-depts` and `flask db upgrade`.
"""
import click
from decimal import Decimal
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


@inventory_cli_bp.cli.command("auto-draft")
def auto_draft():
    """Create DRAFT purchase requests for items below reorder level.

    Runs nightly via cron (23:00 Africa/Nairobi). Skips items that already
    have an open DRAFT or PENDING request. Suggested qty = (reorder × 2) − current.
    """
    from app.models.purchase_request import PurchaseRequest, RequestStatus
    from app.models.audit_log import AuditLog
    from app.services.stock import get_current_stock

    items = db.session.query(InventoryItem).filter_by(is_active=True).all()
    drafted = 0

    for item in items:
        if item.reorder_level <= Decimal("0"):
            continue
        current = get_current_stock(item.id)
        if current >= item.reorder_level:
            continue

        existing = db.session.query(PurchaseRequest).filter(
            PurchaseRequest.item_id == item.id,
            PurchaseRequest.status.in_([RequestStatus.DRAFT.value, RequestStatus.PENDING.value]),
        ).first()
        if existing:
            continue

        suggested_qty = (item.reorder_level * Decimal("2")) - current
        if suggested_qty <= Decimal("0"):
            continue

        with db.session.begin_nested():
            pr = PurchaseRequest(
                item_id=item.id,
                quantity=suggested_qty,
                status=RequestStatus.DRAFT.value,
                system_generated=True,
                requested_by_id=None,
            )
            db.session.add(pr)

        AuditLog.log(actor="system", action="purchase_request.auto_draft",
                     target=item.name, details=f"qty={suggested_qty}")
        drafted += 1

    db.session.commit()
    click.echo(f"Auto-draft: {drafted} DRAFT request(s) created.")
