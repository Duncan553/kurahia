"""
cli/pos.py — POS seed commands.
`flask pos seed-menu` — seeds representative menu items across kitchen, bar, and services.
"""
import click
from flask import Blueprint
from app.extensions import db
from app.models.menu_item import MenuItem, PrepStation
from app.models.department import Department

pos_cli_bp = Blueprint("pos", __name__)


@pos_cli_bp.cli.command("seed-menu")
def seed_menu():
    """Seed demo menu items: kitchen food, bar drinks, spa & water services."""
    # Find or create a General department for items not tied to a specific dept
    dept = db.session.query(Department).filter_by(name="General").first()
    if not dept:
        dept = Department(name="General")
        db.session.add(dept)
        db.session.flush()

    items = [
        # Kitchen food — goes to KITCHEN prep queue
        {"name": "Grilled Tilapia",      "price": "1200", "category": "Mains",   "prep_station": PrepStation.KITCHEN.value},
        {"name": "Nyama Choma (500g)",    "price": "900",  "category": "Mains",   "prep_station": PrepStation.KITCHEN.value},
        {"name": "Ugali & Sukuma Wiki",   "price": "350",  "category": "Sides",   "prep_station": PrepStation.KITCHEN.value},
        {"name": "Chips & Kachumbari",    "price": "280",  "category": "Sides",   "prep_station": PrepStation.KITCHEN.value},
        {"name": "Breakfast Platter",     "price": "650",  "category": "Breakfast","prep_station": PrepStation.KITCHEN.value},

        # Bar drinks — goes to BAR prep queue
        {"name": "Tusker Lager",          "price": "300",  "category": "Beer",    "prep_station": PrepStation.BAR.value},
        {"name": "Dawa Cocktail",         "price": "550",  "category": "Cocktails","prep_station": PrepStation.BAR.value},
        {"name": "Fresh Mango Juice",     "price": "250",  "category": "Juices",  "prep_station": PrepStation.BAR.value},
        {"name": "Mineral Water (500ml)", "price": "100",  "category": "Soft",    "prep_station": PrepStation.BAR.value},
        {"name": "Cappuccino",            "price": "200",  "category": "Coffee",  "prep_station": PrepStation.BAR.value},

        # Services — immediate SERVED, no prep queue (NONE)
        {"name": "Pool Access (Day Pass)", "price": "500", "category": "Activities", "prep_station": PrepStation.NONE.value},
        {"name": "Boat Ride (30 min)",     "price": "800", "category": "Activities", "prep_station": PrepStation.NONE.value},
        {"name": "Spa Massage (60 min)",   "price": "2500","category": "Spa",        "prep_station": PrepStation.NONE.value},
    ]

    added = 0
    for item_data in items:
        exists = db.session.query(MenuItem).filter_by(
            name=item_data["name"], department_id=dept.id
        ).first()
        if not exists:
            mi = MenuItem(
                name=item_data["name"],
                price=item_data["price"],
                category=item_data.get("category"),
                prep_station=item_data["prep_station"],
                department_id=dept.id,
            )
            db.session.add(mi)
            added += 1

    db.session.commit()
    click.echo(f"seed-menu: {added} items added ({len(items) - added} already existed).")
