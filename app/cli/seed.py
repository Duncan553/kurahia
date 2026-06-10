"""
seed.py — CLI commands for bootstrapping the database.

Usage:
  flask seed owner          → creates the first owner account interactively
  flask seed roles-depts    → seeds default roles and departments

Run once after `flask db upgrade` on a fresh database.
"""
import click
from flask import Blueprint
from app.extensions import db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.models.audit_log import AuditLog

seed_bp = Blueprint("seed", __name__)


@seed_bp.cli.command("roles-depts")
def seed_roles_departments():
    """Create default roles (owner/manager/staff) and departments."""
    # Roles: level=10 owner, level=5 manager, level=1 staff
    default_roles = [
        {"name": "owner",   "level": 10},
        {"name": "manager", "level": 5},
        {"name": "staff",   "level": 1},
    ]
    for r in default_roles:
        if not db.session.query(Role).filter_by(name=r["name"]).first():
            db.session.add(Role(name=r["name"], level=r["level"]))
            click.echo(f"  Created role: {r['name']} (level {r['level']})")
        else:
            click.echo(f"  Role already exists: {r['name']}")

    default_departments = [
        "General", "Kitchen", "Bar", "Front-of-House", "Finance",
        "Pool & Water Activities", "Housekeeping", "Maintenance",
    ]
    for d in default_departments:
        if not db.session.query(Department).filter_by(name=d).first():
            db.session.add(Department(name=d))
            click.echo(f"  Created department: {d}")
        else:
            click.echo(f"  Department already exists: {d}")

    db.session.commit()
    click.echo("Done.")


@seed_bp.cli.command("owner")
@click.option("--username", prompt="Owner username", help="Username for the first owner")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Owner password")
def seed_owner(username, password):
    """Create the first owner account. Run this once on a fresh DB."""
    owner_role = db.session.query(Role).filter_by(name="owner").first()
    if not owner_role:
        click.echo("Run `flask seed roles-depts` first to create roles.")
        return

    existing = db.session.query(User).filter_by(username=username.strip().lower()).first()
    if existing:
        click.echo(f"User '{username}' already exists.")
        return

    general_dept = db.session.query(Department).filter_by(name="General").first()

    user = User(
        username=username.strip().lower(),
        role_id=owner_role.id,
        department_id=general_dept.id if general_dept else None,
        is_active=True,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()  # get the user.id before AuditLog references it

    AuditLog.log(actor=user.username, action="user.create", target=user.username, details="initial owner seed")
    db.session.commit()

    click.echo(f"Owner '{user.username}' created successfully.")
    click.echo("Log in via POST /auth/login and set your PIN via POST /auth/set-pin.")


@seed_bp.cli.command("kurahia-inventory")
def seed_kurahia_inventory():
    """Seed real Waterfront Country Club inventory: bar, kitchen, pool, housekeeping."""
    from app.models.inventory_item import InventoryItem

    def _get_dept(name: str):
        d = db.session.query(Department).filter_by(name=name).first()
        if not d:
            click.echo(f"  SKIP — department '{name}' not found. Run `flask seed roles-depts` first.")
        return d

    def _add(dept, name: str, unit: str, reorder: str = "0", watch: bool = False, staff_food: bool = False):
        existing = db.session.query(InventoryItem).filter_by(name=name, department_id=dept.id).first()
        if existing:
            return
        item = InventoryItem(
            name=name, unit=unit, department_id=dept.id,
            reorder_level=reorder, is_watch_list=watch, is_staff_food=staff_food,
        )
        db.session.add(item)

    bar = _get_dept("Bar")
    kitchen = _get_dept("Kitchen")
    pool = _get_dept("Pool & Water Activities")
    hk = _get_dept("Housekeeping")

    if bar:
        click.echo("  Seeding Bar...")
        # Beers (crate = 24 bottles)
        for beer in ["Tusker Lager", "Tusker Malt", "Tusker Cider", "Pilsner Ice",
                     "White Cap", "Guinness", "Heineken", "Smirnoff Ice", "Balozi", "Manyatta"]:
            _add(bar, beer, "crate of 24", "2", watch=True)
        # Spirits (bottle = 750ml)
        for spirit in ["Smirnoff Vodka", "Gilbey's Gin", "Kenya Cane (KC)", "Konyagi",
                       "Captain Morgan", "Johnnie Walker Red", "Johnnie Walker Black",
                       "Hennessy VS", "Jameson", "Jagermeister"]:
            _add(bar, spirit, "bottle (750ml)", "2", watch=True)
        # Wines
        for wine in ["Four Cousins Red", "Four Cousins White", "Drostdy-Hof", "Robertson", "Nederburg"]:
            _add(bar, wine, "bottle (750ml)", "1", watch=True)
        # Soft drinks
        for soda in ["Coca-Cola", "Fanta Orange", "Fanta Passion", "Sprite",
                     "Stoney Tangawizi", "Krest Bitter Lemon", "Schweppes Tonic", "Schweppes Soda"]:
            _add(bar, soda, "crate of 24", "1", watch=True)
        # Water & juices
        for w in ["Keringet 500ml", "Keringet 1L", "Dasani", "Aquamist", "Minute Maid", "Del Monte Juice"]:
            _add(bar, w, "crate of 24", "1")
        # Energy / mixers
        for e in ["Red Bull", "Monster Energy", "Predator"]:
            _add(bar, e, "can", "6", watch=True)

    if kitchen:
        click.echo("  Seeding Kitchen...")
        # Proteins
        _add(kitchen, "Beef", "kg", "5", watch=True)
        _add(kitchen, "Goat (Mbuzi)", "kg", "5", watch=True)
        _add(kitchen, "Chicken", "kg", "5", watch=True)
        _add(kitchen, "Tilapia", "kg", "3", watch=True)
        _add(kitchen, "Mbuta (Nile Perch)", "kg", "3", watch=True)
        _add(kitchen, "Prawns", "kg", "2", watch=True)
        _add(kitchen, "Sausages", "pack", "2")
        # Starches
        _add(kitchen, "Maize Flour (Unga)", "kg", "10")
        _add(kitchen, "Basmati Rice", "kg", "5")
        _add(kitchen, "Pishori Rice", "kg", "5")
        _add(kitchen, "Spaghetti", "pack", "4")
        _add(kitchen, "Chapati Flour", "kg", "5")
        _add(kitchen, "Potatoes", "kg", "10")
        # Produce
        for veg in ["Sukuma Wiki", "Cabbage", "Onions", "Tomatoes", "Capsicums",
                    "Carrots", "Garlic", "Ginger", "Dhania (Coriander)",
                    "Avocados", "Lemons", "Watermelon", "Pineapple", "Mangoes"]:
            _add(kitchen, veg, "kg", "2")
        # Pantry
        _add(kitchen, "Cooking Oil (Sunflower)", "litre", "5")
        _add(kitchen, "Salt", "kg", "2")
        _add(kitchen, "Sugar", "kg", "3")
        _add(kitchen, "Royco", "pack", "3")
        _add(kitchen, "Knorr Cubes", "pack", "2")
        _add(kitchen, "Peri-Peri Sauce", "bottle", "2")
        _add(kitchen, "Mchuzi Mix", "pack", "3")
        _add(kitchen, "Vinegar", "litre", "1")
        _add(kitchen, "Soy Sauce", "bottle", "2")
        _add(kitchen, "Tomato Paste", "tin", "4")
        # Staff food items
        _add(kitchen, "Staff Ugali Flour", "kg", "10", staff_food=True)
        _add(kitchen, "Staff Sukuma Wiki", "kg", "3", staff_food=True)
        _add(kitchen, "Staff Beans", "kg", "5", staff_food=True)

    if pool:
        click.echo("  Seeding Pool & Water Activities...")
        _add(pool, "Chlorine Tablets", "kg", "5", watch=True)
        _add(pool, "Pool Test Strips", "pack", "2", watch=True)
        _add(pool, "pH Down (Sodium Bisulphate)", "kg", "3")
        _add(pool, "pH Up (Sodium Carbonate)", "kg", "3")
        _add(pool, "Life Jackets", "piece", "10")
        _add(pool, "Jetski Fuel", "litre", "20", watch=True)
        _add(pool, "Motorboat Fuel", "litre", "30", watch=True)
        _add(pool, "Inflatable Ring Buoys", "piece", "5")
        _add(pool, "Pool Brushes", "piece", "2")
        _add(pool, "Pool Noodles", "piece", "10")
        _add(pool, "Snorkel Kits", "piece", "5")

    if hk:
        click.echo("  Seeding Housekeeping...")
        _add(hk, "Toilet Paper", "roll", "50", watch=True)
        _add(hk, "Hand Soap (Liquid)", "litre", "5")
        _add(hk, "Bleach", "litre", "10")
        _add(hk, "Laundry Detergent", "kg", "10")
        _add(hk, "Floor Cleaner", "litre", "5")
        _add(hk, "Bathroom Cleaner", "litre", "5")
        _add(hk, "Air Freshener", "can", "10")
        _add(hk, "Guest Towels", "piece", "20")
        _add(hk, "Bath Towels", "piece", "20")
        _add(hk, "Bedsheets (Single)", "piece", "10")
        _add(hk, "Bedsheets (Double)", "piece", "10")
        _add(hk, "Pillow Cases", "piece", "20")
        _add(hk, "Garbage Bags (Large)", "roll", "5")
        _add(hk, "Gloves (Rubber)", "pair", "10")
        _add(hk, "Mops", "piece", "3")
        _add(hk, "Brooms", "piece", "3")

    db.session.commit()
    click.echo("Kurahia inventory seeded successfully. Run `flask seed kurahia-inventory` again safely — duplicates are skipped.")
