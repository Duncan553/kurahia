"""
scripts/seed_realistic.py — Waterfront Country Club realistic seed.

Wipes ALL data, reseeds with realistic Kenyan resort data.
Idempotent: safe to re-run.

Run: .venv/bin/python scripts/seed_realistic.py
"""
import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date

# Make sure the kurahia package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db

app = create_app("development")

# ── Helper ────────────────────────────────────────────────────────────────────

def idem(prefix: str) -> str:
    """Stable idempotency key so repeated runs produce the same rows."""
    return f"seed-{prefix}"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def _yesterday() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

def _next_week() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


# ── Wipe ──────────────────────────────────────────────────────────────────────

def wipe_all():
    """Delete all business data. Preserves schema. Handles FK order via SQLAlchemy metadata sort."""
    print("  Wiping all data...")
    # Disable FK enforcement temporarily so we can delete in any order
    db.session.execute(db.text("PRAGMA foreign_keys = OFF"))
    db.session.commit()

    # Get all tables, sorted in reverse dependency order
    tables = list(reversed(db.metadata.sorted_tables))
    for table in tables:
        db.session.execute(table.delete())
    db.session.commit()

    # Re-enable FK enforcement
    db.session.execute(db.text("PRAGMA foreign_keys = ON"))
    db.session.commit()
    print("  Wipe complete.")


# ── Departments ───────────────────────────────────────────────────────────────

def seed_departments():
    from app.models.department import Department
    print("  Seeding departments...")
    dept_names = [
        "Management",
        "Kitchen",
        "Bar",
        "Restaurant",
        "Spa & Gym",
        "Water Activities",
        "Front Desk",
        "Gate",
        "Housekeeping",
        "Grounds",
        "General",      # catch-all / owner dept
    ]
    depts = {}
    for name in dept_names:
        d = Department(name=name)
        db.session.add(d)
        depts[name] = d
    db.session.flush()
    print(f"    Created {len(depts)} departments.")
    return depts


# ── Roles ─────────────────────────────────────────────────────────────────────

def seed_roles(depts: dict):
    from app.models.role import Role
    print("  Seeding roles...")
    # NOTE: Gate issue-band endpoint requires role.level >= 3 (GATE_LEVEL constant in
    # app/gate/core.py). Spec says gate staff is level 1, which conflicts. We create
    # Hassan at level 3 ("gate_lead") so the roleplay scenario works. Logged as a
    # discrepancy: the API gate level should be lowered to 1 for dedicated gate staff.
    roles_data = [
        {"name": "owner",           "level": 10, "dept": None},
        {"name": "manager",         "level": 5,  "dept": "Management"},
        {"name": "head_chef",       "level": 3,  "dept": "Kitchen"},
        {"name": "bar_lead",        "level": 3,  "dept": "Bar"},
        {"name": "front_desk",      "level": 3,  "dept": "Front Desk"},
        {"name": "gate_lead",       "level": 3,  "dept": "Gate"},      # level 3 required by /gate/issue-band
        {"name": "spa_attendant",   "level": 2,  "dept": "Spa & Gym"},
        {"name": "water_lead",      "level": 2,  "dept": "Water Activities"},
        {"name": "waiter",          "level": 1,  "dept": "Restaurant"},
        {"name": "housekeeping",    "level": 1,  "dept": "Housekeeping"},
        {"name": "grounds",         "level": 1,  "dept": "Grounds"},
        {"name": "staff",           "level": 1,  "dept": None},         # generic fallback
    ]
    roles = {}
    for rd in roles_data:
        dept_id = depts[rd["dept"]].id if rd["dept"] and rd["dept"] in depts else None
        r = Role(name=rd["name"], level=rd["level"], department_id=dept_id)
        db.session.add(r)
        roles[rd["name"]] = r
    db.session.flush()
    print(f"    Created {len(roles)} roles.")
    return roles


# ── Users ─────────────────────────────────────────────────────────────────────

def seed_users(roles: dict, depts: dict):
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile
    from app.models.audit_log import AuditLog
    print("  Seeding users...")

    PASSWORD = os.environ.get("SEED_PASSWORD", "Kurahia1!")

    users_data = [
        # username, full_name, role_key, dept_key, pin, phone
        ("amara.wanjiku",   "Amara Wanjiku",   "owner",         "General",          "1001", "+254711001001"),
        ("brian.mwangi",    "Brian Mwangi",    "manager",       "Management",       "2001", "+254711002001"),
        ("cynthia.achieng", "Cynthia Achieng", "head_chef",     "Kitchen",          "3001", "+254711003001"),
        ("david.otieno",    "David Otieno",    "bar_lead",      "Bar",              "4001", "+254711004001"),
        ("esther.kamau",    "Esther Kamau",    "spa_attendant", "Spa & Gym",        "5001", "+254711005001"),
        ("francis.njoroge", "Francis Njoroge", "water_lead",    "Water Activities", "6001", "+254711006001"),
        ("grace.muthoni",   "Grace Muthoni",   "front_desk",    "Front Desk",       "7001", "+254711007001"),
        ("hassan.omondi",   "Hassan Omondi",   "gate_lead",     "Gate",             "8001", "+254711008001"),
        ("ivan.kipchoge",   "Ivan Kipchoge",   "waiter",        "Restaurant",       "9001", "+254711009001"),
        ("joyce.wambua",    "Joyce Wambua",    "waiter",        "Restaurant",       "9002", "+254711009002"),
        ("kevin.mutua",     "Kevin Mutua",     "housekeeping",  "Housekeeping",     "9003", "+254711009003"),
        ("lillian.chebet",  "Lillian Chebet",  "grounds",       "Grounds",          "9004", "+254711009004"),
    ]

    users = {}
    for username, full_name, role_key, dept_key, pin, phone in users_data:
        u = User(
            username=username,
            role_id=roles[role_key].id,
            department_id=depts[dept_key].id,
            is_active=True,
        )
        u.set_password(PASSWORD)
        u.set_pin(pin)
        db.session.add(u)
        db.session.flush()

        profile = EmployeeProfile(
            user_id=u.id,
            full_name=full_name,
            phone=phone,
            hire_date=date(2024, 1, 15),
            wage_rate=Decimal("50000"),
            wage_period="MONTHLY",
        )
        db.session.add(profile)
        users[username] = u

    db.session.flush()

    # Audit log for owner creation (the anchor)
    owner = users["amara.wanjiku"]
    AuditLog.log(
        actor=owner.username,
        action="user.bulk_seed",
        target="all_staff",
        details="Realistic seed: Waterfront Country Club initial staff",
    )

    print(f"    Created {len(users)} users with profiles.")
    return users


# ── Villas (BookableResource) ─────────────────────────────────────────────────

def seed_villas(depts: dict, users: dict):
    from app.models.bookable_resource import BookableResource, ResourceType
    print("  Seeding villas...")

    # NOTE: BookableResource does not have a photo_url field.
    # Images would live at /images/villas/villa-{n}.jpg via the frontend.
    villas_data = [
        # name, price, capacity
        ("Villa 1",  Decimal("100000"), 8),
        ("Villa 2",  Decimal("100000"), 8),
        ("Villa 4",  Decimal("120000"), 8),
        ("Villa 6",  Decimal("140000"), 8),
        ("Villa 14", Decimal("65000"),  4),
        ("Villa 15", Decimal("65000"),  4),
    ]
    villas = {}
    for name, price, capacity in villas_data:
        v = BookableResource(
            name=name,
            resource_type=ResourceType.VILLA.value,
            capacity=capacity,
            base_price=price,
            department_id=None,
            is_active=True,
        )
        db.session.add(v)
        villas[name] = v
    db.session.flush()
    print(f"    Created {len(villas)} villas.")
    return villas


# ── Bookings ──────────────────────────────────────────────────────────────────

def seed_bookings(villas: dict, users: dict):
    from app.models.bookable_resource import BookableResource
    from app.models.booking import Booking, BookingStatus
    from app.models.guest_record import GuestRecord
    from app.models.tab import Tab, TabType, TabStatus
    from app.models.audit_log import AuditLog
    print("  Seeding bookings...")

    manager = users["brian.mwangi"]
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    yesterday = today - timedelta(days=1)

    # Guest records
    guest_a = GuestRecord(
        name="Kariuki Ndungu",
        phone="+254722100001",
        id_number="A1234567",
        notes="VIP guest, repeat visitor",
    )
    guest_b = GuestRecord(
        name="Wanjiru Kamau",
        phone="+254733200002",
        id_number="B2345678",
    )
    db.session.add_all([guest_a, guest_b])
    db.session.flush()

    # Booking 1: Villa 1 — CHECKED_IN (yesterday)
    # Need a tab for checked-in villa
    villa1_tab = Tab(
        tab_type=TabType.VILLA.value,
        reference="Villa 1 — Kariuki Ndungu",
        opened_by_id=manager.id,
        status=TabStatus.OPEN.value,
    )
    db.session.add(villa1_tab)
    db.session.flush()

    booking1 = Booking(
        resource_id=villas["Villa 1"].id,
        guest_record_id=guest_a.id,
        guest_name="Kariuki Ndungu",
        guest_phone="+254722100001",
        guest_id_number="A1234567",
        number_of_guests=4,
        check_in_planned_utc=datetime(yesterday.year, yesterday.month, yesterday.day, 14, 0, tzinfo=timezone.utc),
        check_out_planned_utc=datetime(today.year, today.month, today.day, 11, 0, tzinfo=timezone.utc) + timedelta(days=2),
        base_total=Decimal("100000"),
        deposit_required=Decimal("30000"),
        status=BookingStatus.CHECKED_IN.value,
        tab_id=villa1_tab.id,
        notes="2 nights, 4 adults. Paid deposit via M-Pesa.",
        idempotency_key=idem("booking-villa1"),
        created_by_id=manager.id,
        check_in_actual_utc=datetime(yesterday.year, yesterday.month, yesterday.day, 15, 30, tzinfo=timezone.utc),
    )
    db.session.add(booking1)

    # Booking 2: Villa 6 — CONFIRMED (next week)
    next_week = today + timedelta(days=7)
    checkout = today + timedelta(days=10)
    booking2 = Booking(
        resource_id=villas["Villa 6"].id,
        guest_record_id=guest_b.id,
        guest_name="Wanjiru Kamau",
        guest_phone="+254733200002",
        guest_id_number="B2345678",
        number_of_guests=6,
        check_in_planned_utc=datetime(next_week.year, next_week.month, next_week.day, 14, 0, tzinfo=timezone.utc),
        check_out_planned_utc=datetime(checkout.year, checkout.month, checkout.day, 11, 0, tzinfo=timezone.utc),
        base_total=Decimal("420000"),  # 3 nights × 140,000
        deposit_required=Decimal("100000"),
        status=BookingStatus.CONFIRMED.value,
        notes="3 nights, 6 adults. Full payment expected on check-in.",
        idempotency_key=idem("booking-villa6"),
        created_by_id=manager.id,
    )
    db.session.add(booking2)
    db.session.flush()

    AuditLog.log(actor=manager.username, action="booking.create", target="Villa 1", details="seed: checked-in booking")
    AuditLog.log(actor=manager.username, action="booking.create", target="Villa 6", details="seed: confirmed upcoming booking")

    print("    Created 2 bookings (Villa 1 checked-in, Villa 6 upcoming).")
    return {"booking1": booking1, "booking2": booking2, "villa1_tab": villa1_tab}


# ── Water Activities menu items ───────────────────────────────────────────────

def seed_water_menu(depts: dict):
    from app.models.menu_item import MenuItem, PrepStation
    print("  Seeding water activities menu...")
    water_dept = depts["Water Activities"]
    items_data = [
        ("Jet Ski Ride (30 min)", Decimal("3500"), "Water Activities"),
        ("Kayaking (1 hr)",       Decimal("1500"), "Water Activities"),
        ("Boat Ride (30 min)",    Decimal("2500"), "Water Activities"),
        ("Fishing Trip (2 hr)",   Decimal("4000"), "Water Activities"),
        ("Swimming Pool Day Pass", Decimal("1000"), "Activities"),
        ("Nature Trail / Hiking", Decimal("800"),  "Activities"),
        ("Cycling Tour",          Decimal("600"),  "Activities"),
        ("Golf Cart Ride",        Decimal("500"),  "Activities"),
    ]
    items = {}
    for name, price, category in items_data:
        mi = MenuItem(
            name=name,
            price=price,
            category=category,
            prep_station=PrepStation.NONE.value,  # direct service, no queue
            department_id=water_dept.id,
            image_path=f"/images/water/{name.lower().replace(' ', '-').replace('/', '-')}.jpg",
            is_active=True,
        )
        db.session.add(mi)
        items[name] = mi
    db.session.flush()
    print(f"    Created {len(items)} water activity items.")
    return items


# ── Spa & Gym menu items ──────────────────────────────────────────────────────

def seed_spa_menu(depts: dict):
    from app.models.menu_item import MenuItem, PrepStation
    print("  Seeding spa & gym menu...")
    spa_dept = depts["Spa & Gym"]
    items_data = [
        ("Full Body Massage (60 min)", Decimal("5000"), "Massage"),
        ("Aromatherapy Session",       Decimal("4500"), "Treatments"),
        ("Beauty Ritual Package",      Decimal("6000"), "Packages"),
        ("Gym Day Pass",               Decimal("800"),  "Gym"),
        ("Personal Training Session (1 hr)", Decimal("2500"), "Gym"),
    ]
    items = {}
    for name, price, category in items_data:
        mi = MenuItem(
            name=name,
            price=price,
            category=category,
            prep_station=PrepStation.NONE.value,
            department_id=spa_dept.id,
            image_path=f"/images/spa/{name.lower().replace(' ', '-').replace('/', '-')}.jpg",
            is_active=True,
        )
        db.session.add(mi)
        items[name] = mi
    db.session.flush()
    print(f"    Created {len(items)} spa/gym items.")
    return items


# ── Restaurant / Bar menu items ───────────────────────────────────────────────

def seed_food_menu(depts: dict):
    from app.models.menu_item import MenuItem, PrepStation
    print("  Seeding restaurant & bar menu...")
    restaurant_dept = depts["Restaurant"]
    bar_dept = depts["Bar"]

    items_data = [
        # name, price, category, prep_station, dept_key, active
        ("Grilled Tilapia",      Decimal("1800"), "Mains",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Beef Burger",          Decimal("1400"), "Mains",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Nyama Choma (500g)",   Decimal("2200"), "Mains",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Chips Masala",         Decimal("700"),  "Mains",      PrepStation.KITCHEN.value, "Restaurant", False),  # sold-out
        ("Club Sandwich",        Decimal("1200"), "Mains",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Chips",                Decimal("400"),  "Sides",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Ugali & Sukuma",       Decimal("350"),  "Sides",      PrepStation.KITCHEN.value, "Restaurant", True),
        ("Soda (330ml)",         Decimal("150"),  "Soft Drinks",PrepStation.NONE.value,    "Restaurant", True),
        ("Fresh Juice",          Decimal("400"),  "Soft Drinks",PrepStation.NONE.value,    "Restaurant", True),
        ("Mineral Water",        Decimal("100"),  "Soft Drinks",PrepStation.NONE.value,    "Restaurant", True),
        ("Chocolate Cake",       Decimal("600"),  "Desserts",   PrepStation.KITCHEN.value, "Restaurant", True),
        ("Tusker Beer",          Decimal("350"),  "Beer",       PrepStation.BAR.value,     "Bar",        True),
        ("Guinness",             Decimal("400"),  "Beer",       PrepStation.BAR.value,     "Bar",        True),
        ("Dawa Cocktail",        Decimal("800"),  "Cocktails",  PrepStation.BAR.value,     "Bar",        True),
        ("Mojito",               Decimal("900"),  "Cocktails",  PrepStation.BAR.value,     "Bar",        True),
        ("Wine (glass)",         Decimal("1200"), "Wine",       PrepStation.BAR.value,     "Bar",        True),
    ]
    dept_map = {"Restaurant": restaurant_dept, "Bar": bar_dept}
    items = {}
    for name, price, category, station, dept_key, active in items_data:
        mi = MenuItem(
            name=name,
            price=price,
            category=category,
            prep_station=station,
            department_id=dept_map[dept_key].id,
            image_path=f"/images/menu/{name.lower().replace(' ', '-').replace('/', '-')}.jpg",
            is_active=active,
        )
        db.session.add(mi)
        items[name] = mi
    db.session.flush()
    sold_out_count = sum(1 for *_, active in items_data if not active)
    print(f"    Created {len(items)} food/bar items ({sold_out_count} marked sold-out).")
    return items


# ── Recipes ───────────────────────────────────────────────────────────────────

def seed_recipes(menu_items: dict, kitchen_inventory: dict):
    from app.models.recipe_line import RecipeLine
    print("  Seeding recipes...")

    def _add_line(menu_item_name, inv_item_name, qty, unit):
        mi = menu_items.get(menu_item_name)
        inv = kitchen_inventory.get(inv_item_name)
        if not mi or not inv:
            print(f"    SKIP recipe line: {menu_item_name} / {inv_item_name} not found")
            return
        rl = RecipeLine(
            menu_item_id=mi.id,
            inventory_item_id=inv.id,
            quantity=Decimal(str(qty)),
            unit=unit,
            is_active=True,
        )
        db.session.add(rl)

    # Grilled Tilapia
    _add_line("Grilled Tilapia", "Tilapia Fillet",  Decimal("0.350"), "kg")
    _add_line("Grilled Tilapia", "Cooking Oil",     Decimal("0.020"), "litre")
    _add_line("Grilled Tilapia", "Spices Mix",      Decimal("0.010"), "kg")
    _add_line("Grilled Tilapia", "Onions",          Decimal("0.050"), "kg")
    _add_line("Grilled Tilapia", "Tomatoes",        Decimal("0.100"), "kg")

    # Beef Burger
    _add_line("Beef Burger", "Beef Patties",  Decimal("0.200"), "kg")
    _add_line("Beef Burger", "Bread Loaves",  Decimal("0.100"), "kg")
    _add_line("Beef Burger", "Tomatoes",      Decimal("0.060"), "kg")
    _add_line("Beef Burger", "Onions",        Decimal("0.040"), "kg")
    _add_line("Beef Burger", "Cooking Oil",   Decimal("0.010"), "litre")

    # Nyama Choma
    _add_line("Nyama Choma (500g)", "Beef Patties",  Decimal("0.500"), "kg")
    _add_line("Nyama Choma (500g)", "Spices Mix",    Decimal("0.020"), "kg")
    _add_line("Nyama Choma (500g)", "Cooking Oil",   Decimal("0.015"), "litre")

    # Club Sandwich
    _add_line("Club Sandwich", "Bread Loaves",  Decimal("0.150"), "kg")
    _add_line("Club Sandwich", "Tomatoes",      Decimal("0.080"), "kg")
    _add_line("Club Sandwich", "Cooking Oil",   Decimal("0.005"), "litre")

    db.session.flush()
    print("    Recipes seeded for 4 menu items.")


# ── Inventory ─────────────────────────────────────────────────────────────────

def seed_inventory(depts: dict, users: dict):
    from app.models.inventory_item import InventoryItem
    from app.models.stock_movement import StockMovement, MovementReason
    print("  Seeding inventory...")

    manager = users["brian.mwangi"]

    # Inventory items by department
    # Format: (name, unit, initial_qty, reorder_level, is_watch_list)
    inventory_data = {
        "Kitchen": [
            ("Tilapia Fillet",  "kg",    10.0,  2.0,  True),
            ("Beef Patties",    "kg",     5.0,  1.0,  True),
            ("Tomatoes",        "kg",     8.0,  2.0,  False),
            ("Onions",          "kg",    10.0,  2.0,  False),
            ("Cooking Oil",     "litre",  0.5,  2.0,  True),   # LOW — near zero
            ("Spices Mix",      "kg",     2.0,  0.5,  False),
            ("Bread Loaves",    "kg",    20.0,  5.0,  False),
            ("Potatoes",        "kg",    15.0,  3.0,  False),
            ("Ugali Flour",     "kg",    10.0,  5.0,  False),
            ("Sukuma Wiki",     "kg",     5.0,  1.0,  False),
        ],
        "Bar": [
            ("Tusker Beer",    "bottle",  48.0, 12.0, True),
            ("Guinness",       "bottle",  24.0,  6.0, True),
            ("Vodka",          "bottle",   3.0,  1.0, True),
            ("White Rum",      "bottle",   2.0,  1.0, True),
            ("White Wine",     "bottle",   6.0,  2.0, True),
            ("Soda Mix",       "can",     24.0,  6.0, False),
            ("Lime",           "kg",       3.0,  0.5, False),
            ("Sugar Syrup",    "litre",    2.0,  0.5, False),
        ],
        "Spa & Gym": [
            ("Massage Oil",     "bottle",  5.0,  2.0, False),
            ("Aromatherapy Kit","set",      3.0,  1.0, False),
            ("Towels",          "piece",  20.0,  5.0, False),
            ("Face Creams",     "piece",  10.0,  3.0, False),
        ],
        "Water Activities": [
            ("Fuel",           "litre",    2.0, 20.0, True),   # LOW — will trigger alert
            ("Life Jackets",   "piece",    8.0,  4.0, False),
            ("Paddle Sets",    "set",      4.0,  2.0, False),
        ],
        "Housekeeping": [
            ("Cleaning Detergent", "bottle",  10.0,  3.0, False),
            ("Mop Heads",          "piece",    5.0,  2.0, False),
            ("Room Freshener",     "can",     12.0,  4.0, False),
            ("Toilet Paper",       "roll",    48.0, 20.0, True),
        ],
        "Grounds": [
            ("Fertilizer",    "kg",    25.0,  5.0, False),
            ("Grass Seed",    "kg",     5.0,  1.0, False),
            ("Gloves",        "pair",  10.0,  2.0, False),
        ],
    }

    all_items = {}
    dept_items = {}  # dept_name -> {item_name -> InventoryItem}
    for dept_name, items in inventory_data.items():
        dept = depts[dept_name]
        dept_items[dept_name] = {}
        for name, unit, qty, reorder, watch in items:
            item = InventoryItem(
                name=name,
                unit=unit,
                department_id=dept.id,
                reorder_level=Decimal(str(reorder)),
                is_watch_list=watch,
                is_active=True,
            )
            db.session.add(item)
            db.session.flush()

            # Seed the stock via a PURCHASE movement
            mv = StockMovement(
                item_id=item.id,
                change_amount=Decimal(str(qty)),
                reason=MovementReason.PURCHASE.value,
                actor_id=manager.id,
                idempotency_key=idem(f"stock-in-{dept_name}-{name}"),
                notes="Initial delivery — resort opening stock",
            )
            db.session.add(mv)
            all_items[name] = item
            dept_items[dept_name][name] = item

    db.session.flush()
    total_items = sum(len(v) for v in dept_items.values())
    print(f"    Created {total_items} inventory items with purchase movements.")
    return all_items, dept_items


# ── Wristbands & Live Activity ────────────────────────────────────────────────

def seed_live_activity(depts: dict, users: dict, menu_items: dict):
    """
    Seed realistic today/yesterday activity:
    - 4 wristbands issued today (2 with spending, 1 forfeited, 1 active)
    - 3 restaurant tabs (closed)
    - 1 spa sale (closed tab)
    - 1 water activity sale (closed tab)
    """
    from app.models.tab import Tab, TabType, TabStatus
    from app.models.payment import Payment, PaymentMethod
    from app.models.charge import Charge
    from app.models.order import Order, OrderStatus
    from app.models.order_item import OrderItem, OrderItemStatus
    from app.models.wristband import Wristband, WristbandStatus
    from app.models.wristband_counter import WristbandCounter
    from app.models.gate_entry import GateEntry
    from app.models.audit_log import AuditLog

    print("  Seeding live activity (wristbands, tabs, orders)...")
    gate_staff = users["hassan.omondi"]
    waiter_ivan = users["ivan.kipchoge"]
    waiter_joyce = users["joyce.wambua"]
    front_desk = users["grace.muthoni"]
    spa_staff = users["esther.kamau"]
    water_staff = users["francis.njoroge"]

    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    now = datetime.now(timezone.utc)

    # ── Band counter for today ────────────────────────────────────────────────
    counter = WristbandCounter(issue_date=today, next_number=5)  # start at 5 (4 already used)
    db.session.add(counter)
    db.session.flush()

    def _make_band(band_number, issue_date, issuer, method, notes=None, status=WristbandStatus.ACTIVE.value, spent=Decimal("0")):
        """Create a tab + payment + wristband, optionally add spending charges."""
        ikey = idem(f"band-{issue_date}-{band_number}")
        tab = Tab(
            tab_type=TabType.BAND.value,
            reference=f"Band #{band_number}",
            opened_by_id=issuer.id,
            status=TabStatus.OPEN.value if status == WristbandStatus.ACTIVE.value else TabStatus.CLOSED.value,
        )
        db.session.add(tab)
        db.session.flush()

        entry_payment = Payment(
            tab_id=tab.id,
            amount=Decimal("3000"),
            method=method,
            description=f"Entry fee — band #{band_number}",
            received_by_id=issuer.id,
            idempotency_key=idem(f"gate-credit-{ikey}"),
        )
        db.session.add(entry_payment)
        db.session.flush()

        band = Wristband(
            band_number=band_number,
            issue_date=issue_date,
            issued_by_id=issuer.id,
            entry_payment_id=entry_payment.id,
            tab_id=tab.id,
            status=status,
            notes=notes,
            idempotency_key=ikey,
        )
        db.session.add(band)
        db.session.flush()

        entry = GateEntry(wristband_id=band.id, head_count=1, created_by_id=issuer.id)
        db.session.add(entry)
        db.session.flush()

        # Add spending if requested
        if spent > 0:
            charge = Charge(
                tab_id=tab.id,
                amount=spent,
                description="Band spending — food & services",
                created_by_id=issuer.id,
            )
            db.session.add(charge)
            db.session.flush()

        AuditLog.log(
            actor=issuer.username,
            action="gate.issue_band",
            details=f"band={band_number} date={issue_date} method={method}",
        )
        return band, tab

    # Band 1: KSh 2,000 spent → still active (KSh 1,000 credit remaining)
    band1, tab_band1 = _make_band(1, today, gate_staff, PaymentMethod.CASH.value,
                                   notes="Customer A — morning entry", spent=Decimal("2000"))

    # Band 2: KSh 2,800 spent → still active (KSh 200 credit remaining)
    band2, tab_band2 = _make_band(2, today, gate_staff, PaymentMethod.MPESA.value,
                                   notes="Customer B — afternoon entry", spent=Decimal("2800"))

    # Band 3: forfeited (KSh 3,000 credit unused)
    band3, tab_band3 = _make_band(3, today, gate_staff, PaymentMethod.CASH.value,
                                   notes="Customer C — left early",
                                   status=WristbandStatus.FORFEITED.value,
                                   spent=Decimal("800"))
    band3.deactivated_at_utc = now - timedelta(hours=1)
    band3.deactivated_by_id = gate_staff.id

    # Band 4: active, no spending yet
    band4, tab_band4 = _make_band(4, today, gate_staff, PaymentMethod.CASH.value,
                                   notes="Customer D — recent entry")

    db.session.flush()

    # ── Restaurant tabs (yesterday + today) ──────────────────────────────────

    def _make_closed_tab(ref, opener, items_and_qtys, payment_method, payment_ref=None):
        """Create a closed tab with orders."""
        tab = Tab(
            tab_type=TabType.WALK_IN.value,
            reference=ref,
            opened_by_id=opener.id,
            status=TabStatus.CLOSED.value,
            closed_at_utc=now - timedelta(hours=2),
            closed_by_id=opener.id,
        )
        db.session.add(tab)
        db.session.flush()

        order = Order(
            tab_id=tab.id,
            status=OrderStatus.FULLY_SERVED.value,
            created_by_id=opener.id,
            idempotency_key=idem(f"order-{ref}"),
            sent_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2),
        )
        db.session.add(order)
        db.session.flush()

        total = Decimal("0")
        for item_name, qty in items_and_qtys:
            mi = menu_items.get(item_name)
            if not mi:
                continue
            price = Decimal(str(mi.price))
            oi = OrderItem(
                order_id=order.id,
                menu_item_id=mi.id,
                quantity=Decimal(str(qty)),
                unit_price_snapshot=price,
                prep_station_snapshot=mi.prep_station,
                status=OrderItemStatus.SERVED.value,
                served_at=now - timedelta(hours=2, minutes=30),
            )
            db.session.add(oi)
            db.session.flush()
            charge = Charge(
                tab_id=tab.id,
                order_item_id=oi.id,
                amount=price * Decimal(str(qty)),
                description=f"{item_name} × {qty}",
                created_by_id=opener.id,
            )
            db.session.add(charge)
            total += price * Decimal(str(qty))

        db.session.flush()

        # Payment
        mpesa_code = None
        if payment_method == PaymentMethod.MPESA.value:
            mpesa_code = payment_ref
        pay = Payment(
            tab_id=tab.id,
            amount=total,
            method=payment_method,
            mpesa_code=mpesa_code,
            description="Tab settlement",
            received_by_id=front_desk.id,
            idempotency_key=idem(f"payment-{ref}"),
        )
        db.session.add(pay)
        db.session.flush()
        return tab

    # Restaurant Tab 1 (yesterday, Ivan, cash)
    _make_closed_tab(
        "Table 3 — dinner",
        waiter_ivan,
        [("Grilled Tilapia", 2), ("Chips", 2), ("Tusker Beer", 2), ("Fresh Juice", 1)],
        PaymentMethod.CASH.value,
    )

    # Restaurant Tab 2 (yesterday, Joyce, band payment)
    _make_closed_tab(
        "Table 7 — lunch",
        waiter_joyce,
        [("Beef Burger", 1), ("Chips", 1), ("Soda (330ml)", 2), ("Chocolate Cake", 1)],
        PaymentMethod.MPESA.value,
        "QXY123456",
    )

    # Restaurant Tab 3 (today, Ivan, M-Pesa)
    _make_closed_tab(
        "Table 2 — breakfast",
        waiter_ivan,
        [("Club Sandwich", 2), ("Fresh Juice", 2), ("Dawa Cocktail", 1)],
        PaymentMethod.MPESA.value,
        "QAB789012",
    )

    # Spa Tab (today, Esther, band payment — tab type WALK_IN, method CASH)
    _make_closed_tab(
        "Spa — Full Body Massage",
        spa_staff,
        [("Full Body Massage (60 min)", 1)],
        PaymentMethod.CASH.value,
    )

    # Water Activity Tab (today, Francis, cash)
    _make_closed_tab(
        "Water — Jet Ski",
        water_staff,
        [("Jet Ski Ride (30 min)", 1)],
        PaymentMethod.CASH.value,
    )

    db.session.flush()
    print("    Seeded 4 wristbands, 5 closed tabs (3 restaurant, 1 spa, 1 water).")
    return {
        "band1": band1, "band2": band2, "band3": band3, "band4": band4,
        "tab_band1": tab_band1, "tab_band2": tab_band2,
        "tab_band3": tab_band3, "tab_band4": tab_band4,
    }


# ── Judge Alert (low stock) ───────────────────────────────────────────────────

def seed_judge_alert(inv_items: dict):
    """Seed a low-stock judge alert for Fuel (Water Activities)."""
    from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
    print("  Seeding judge alert for low fuel stock...")
    fuel_item = inv_items.get("Fuel")
    if not fuel_item:
        print("    SKIP — Fuel item not found")
        return

    alert = JudgeAlert(
        item_id=fuel_item.id,
        alert_type="VARIANCE",
        severity=AlertSeverity.HIGH.value,
        description=(
            "Fuel (Water Activities) is critically low: 2.0 litres remaining vs "
            "reorder level of 20.0 litres. Jet ski and boat operations may be disrupted. "
            "Please raise a restock request immediately."
        ),
        status=AlertStatus.OPEN.value,
    )
    db.session.add(alert)

    # Also add low cooking oil alert
    oil_item = inv_items.get("Cooking Oil")
    if oil_item:
        alert2 = JudgeAlert(
            item_id=oil_item.id,
            alert_type="VARIANCE",
            severity=AlertSeverity.HIGH.value,
            description=(
                "Cooking Oil (Kitchen) is critically low: 0.5 litres remaining vs "
                "reorder level of 2.0 litres. Kitchen operations may be disrupted."
            ),
            status=AlertStatus.OPEN.value,
        )
        db.session.add(alert2)

    db.session.flush()
    print("    Seeded 2 judge alerts (Fuel low, Cooking Oil low).")


# ── System Settings ───────────────────────────────────────────────────────────

def seed_system_settings():
    from app.models.system_setting import SystemSetting
    print("  Seeding system settings...")
    settings = [
        ("business_day_start_hour", "6"),
        ("business_day_timezone", "Africa/Nairobi"),
        ("resort_name", "Waterfront Country Club"),
        ("currency", "KES"),
        ("wristband_entry_fee", "3000"),
    ]
    for key, value in settings:
        existing = db.session.query(SystemSetting).filter_by(key=key).first()
        if not existing:
            db.session.add(SystemSetting(key=key, value=value))
    db.session.flush()
    print("    System settings seeded.")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    with app.app_context():
        print("\n=== Waterfront Country Club — Realistic Seed ===\n")

        # 1. Wipe
        wipe_all()

        # 2. Core structure
        depts = seed_departments()
        roles = seed_roles(depts)
        users = seed_users(roles, depts)

        # 3. System settings
        seed_system_settings()

        # 4. Villas & Bookings
        villas = seed_villas(depts, users)
        bookings = seed_bookings(villas, users)

        # 5. Menu
        water_items = seed_water_menu(depts)
        spa_items = seed_spa_menu(depts)
        food_items = seed_food_menu(depts)
        all_menu = {**water_items, **spa_items, **food_items}

        # 6. Inventory
        inv_items, dept_inv = seed_inventory(depts, users)

        # 7. Recipes (uses kitchen inventory items)
        seed_recipes(food_items, dept_inv.get("Kitchen", {}))

        # 8. Live activity
        seed_live_activity(depts, users, all_menu)

        # 9. Judge alerts for low stock
        seed_judge_alert(inv_items)

        # Final commit
        db.session.commit()

        print("\n=== Seed complete ===")
        print(f"Users created (all password: {PASSWORD}):")
        print("  amara.wanjiku   (owner, PIN 1001)")
        print("  brian.mwangi    (manager, PIN 2001)")
        print("  cynthia.achieng (head chef, PIN 3001)")
        print("  david.otieno    (bar lead, PIN 4001)")
        print("  esther.kamau    (spa attendant, PIN 5001)")
        print("  francis.njoroge (water lead, PIN 6001)")
        print("  grace.muthoni   (front desk, PIN 7001)")
        print("  hassan.omondi   (gate lead level 3, PIN 8001)")
        print("  ivan.kipchoge   (waiter, PIN 9001)")
        print("  joyce.wambua    (waiter, PIN 9002)")
        print("  kevin.mutua     (housekeeping, PIN 9003)")
        print("  lillian.chebet  (grounds, PIN 9004)")
        print("\nNOTE: Hassan is level 3 (gate_lead) — gate/issue-band requires level 3.")
        print("Spec says level 1; this is a code/spec conflict, fixed to level 3 for roleplay.\n")


def _seed_all():
    """Run all seed steps inside an existing app context (no wipe, no outer context)."""
    print("\n=== Waterfront Country Club — Realistic Seed ===\n")
    depts = seed_departments()
    roles = seed_roles(depts)
    users = seed_users(roles, depts)
    seed_system_settings()
    villas = seed_villas(depts, users)
    seed_bookings(villas, users)
    water_items = seed_water_menu(depts)
    spa_items = seed_spa_menu(depts)
    food_items = seed_food_menu(depts)
    inv_items, dept_inv = seed_inventory(depts, users)
    seed_recipes(food_items, dept_inv.get("Kitchen", {}))
    seed_live_activity(depts, users, {**water_items, **spa_items, **food_items})
    seed_judge_alert(inv_items)
    db.session.commit()
    print("=== Seed complete ===\n")


if __name__ == "__main__":
    run()
