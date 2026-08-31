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


# ── Correcting mis-keyed catalogue data ───────────────────────────────────────
#
# The seed created 33 inventory items and 29 menu items but never wired them
# together: 16 menu items sat UNTRACKED (unsellable — that block is deliberate)
# while the exact ingredients they needed sat unused in the store.
#
# This command fixes the parts that need no judgement call:
#   1. creates the handful of ingredients the seed forgot, so no recipe can
#      fail for want of a stock item to point at;
#   2. sets pack_size on the spirits, so a cocktail recipe can say "40 ml"
#      instead of "0.0533 bottles";
#   3. moves three drinks off prep_station NONE and onto BAR, so the bar is
#      actually told to pour them.
#
# It does NOT invent recipe quantities — those are the kitchen's real portions
# and belong to whoever runs it. Idempotent: safe to re-run.

# (name, unit, dept, reorder, pack_size, pack_unit, why)
MISSING_INGREDIENTS = [
    ("Passion Fruit",        "kg",     "Bar",     3.0,  None, None,
     "Fresh Juice — no fruit existed in the whole catalogue"),
    ("Mango",                "kg",     "Bar",     3.0,  None, None,
     "Fresh Juice — second common variety"),
    ("Mineral Water 500ml",  "bottle", "Bar",    24.0,  None, None,
     "sold as-is; DIRECT, not a recipe"),
    ("Soda 330ml",           "bottle", "Bar",    24.0,  None, None,
     "the guest drink — distinct from 'Soda Mix', which is a cocktail mixer"),
    ("Chocolate Cake (whole)","cake",  "Kitchen", 2.0,  10.0, "slice",
     "bought in whole, sold by the slice — 10 slices a cake"),
]

# Spirits are stocked by the bottle but poured by the millilitre. Without
# pack_size a recipe has to express a 40 ml tot as a fraction of a bottle.
SPIRIT_PACKS = [
    ("Vodka",      750.0, "ml"),
    ("White Rum",  750.0, "ml"),
    ("White Wine", 750.0, "ml"),
]

# Drinks keyed as NONE never enter the bar queue: they get sold, and nobody is
# ever told to pour them.
STATION_CORRECTIONS = [
    ("Fresh Juice",    PrepStation.BAR.value),
    ("Mineral Water",  PrepStation.BAR.value),
    ("Soda (330ml)",   PrepStation.BAR.value),
]


@pos_cli_bp.cli.command("fix-catalogue")
def fix_catalogue():
    """Create missing ingredients, set spirit pack sizes, fix drink stations."""
    from app.models.inventory_item import InventoryItem
    from app.models.audit_log import AuditLog

    depts = {d.name: d for d in db.session.query(Department).all()}
    created = packed = restationed = 0

    # 1. Ingredients the seed forgot
    for name, unit, dept_name, reorder, pack_size, pack_unit, why in MISSING_INGREDIENTS:
        dept = depts.get(dept_name)
        if not dept:
            click.echo(f"  SKIP {name} — no '{dept_name}' department")
            continue
        if db.session.query(InventoryItem).filter_by(name=name, department_id=dept.id).first():
            click.echo(f"  exists   {name}")
            continue
        db.session.add(InventoryItem(
            name=name, unit=unit, department_id=dept.id,
            reorder_level=str(reorder),
            pack_size=str(pack_size) if pack_size else None,
            pack_unit=pack_unit,
        ))
        AuditLog.log(actor="cli", action="inventory.item.create", target=name, details=why)
        click.echo(f"  CREATED  {name} ({unit}) — {why}")
        created += 1

    # 2. Pack sizes on spirits
    for name, size, unit in SPIRIT_PACKS:
        item = db.session.query(InventoryItem).filter_by(name=name).first()
        if not item:
            click.echo(f"  SKIP {name} — not in inventory")
            continue
        if item.pack_size:
            click.echo(f"  exists   {name} pack={item.pack_size}{item.pack_unit}")
            continue
        item.pack_size, item.pack_unit = str(size), unit
        AuditLog.log(actor="cli", action="inventory.item.edit", target=name,
                     details=f"pack_size -> {size}{unit}")
        click.echo(f"  PACKED   {name} = {size}{unit} per bottle")
        packed += 1

    # 3. Drinks that never reached the bar queue
    for name, station in STATION_CORRECTIONS:
        item = db.session.query(MenuItem).filter_by(name=name).first()
        if not item:
            click.echo(f"  SKIP {name} — not on the menu")
            continue
        if item.prep_station == station:
            click.echo(f"  exists   {name} -> {station}")
            continue
        old = item.prep_station
        item.prep_station = station
        AuditLog.log(actor="cli", action="menu.item.edit", target=name,
                     details=f"prep_station {old} -> {station}")
        click.echo(f"  STATION  {name}: {old} -> {station}")
        restationed += 1

    db.session.commit()
    click.echo(f"\nfix-catalogue: {created} ingredients created, "
               f"{packed} pack sizes set, {restationed} stations corrected.")


# Existing drinks predate the is_alcoholic column, so they all defaulted to
# False — which would have left the head chef able to reprice the whole bar.
# Categories are the seed's own labels and are only used HERE, once, to find
# the rows; the permission itself reads the column, never the category.
ALCOHOL_CATEGORIES = {"Beer", "Cocktails", "Wine", "Spirits"}


@pos_cli_bp.cli.command("flag-alcohol")
def flag_alcohol():
    """Mark existing beer/wine/cocktail menu items as alcoholic. Idempotent."""
    from app.models.audit_log import AuditLog

    flagged = 0
    for item in db.session.query(MenuItem).all():
        should_be = (item.category or "") in ALCOHOL_CATEGORIES
        if should_be and not item.is_alcoholic:
            item.is_alcoholic = True
            AuditLog.log(actor="cli", action="menu.item.edit", target=item.name,
                         details="is_alcoholic -> True (manager-authored from here on)")
            click.echo(f"  ALCOHOL  {item.name}  [{item.category}]")
            flagged += 1
        elif item.is_alcoholic:
            click.echo(f"  already  {item.name}")

    db.session.commit()
    click.echo(f"\nflag-alcohol: {flagged} items are now manager-only.")
