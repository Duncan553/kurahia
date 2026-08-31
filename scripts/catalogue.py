"""
scripts/catalogue.py — stock the resort's catalogue through the real endpoints.

NOT a seeder. Same rule as scripts/scenarios.py: nothing is written to the
database directly. Every supplier, purchase and recipe below is an HTTP call
made by the person whose job it actually is, through the same role checks a
tablet on the floor goes through. If the head chef is not allowed to price a
cocktail, this script fails on that line — which is the point.

Run:  python scripts/catalogue.py

Safe to re-run. Suppliers that exist are left alone (409 is a PASS), purchases
carry stable idempotency keys, and POST /menu/items/<id>/recipe REPLACES a
recipe rather than stacking a second one.

WHY THIS EXISTS. An UNTRACKED menu item cannot be sold — that block is
deliberate, and it means "nobody has decided how this deducts stock", not
"this consumes nothing". 15 real items were sitting UNTRACKED, so more than
half the menu was unsellable. Deciding each one is the work here.

THE THREE ANSWERS, and how to tell them apart:

  RECIPE   assembled from parts. Selling one deducts several ingredients in
           the quantities below. Chips, cocktails, ugali.
  DIRECT   one sale, one unit of one stock item. A bottle of Tusker leaves the
           fridge exactly as it arrived. The club selling beer is DIRECT — it
           is NOT a recipe just because it is a drink.
  SERVICE  a human has confirmed it consumes nothing tracked. A golf cart ride.
           This is a claim somebody signs for, not a shrug.

PRICES are real Kenyan wholesale, Aug 2026, for a resort buying in Juja/Thika.
They matter: cost_per_unit is DERIVED from purchases, so until real money is
recorded against an item, every margin and every shilling of stock variance
reads blank.
"""
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models.user import User                             # noqa: E402
from app.models.menu_item import MenuItem                    # noqa: E402
from app.models.inventory_item import InventoryItem          # noqa: E402
from flask_jwt_extended import create_access_token            # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}          # inside the WiFi allow-list
RESULTS = []


def record(ok, step, detail=""):
    RESULTS.append((ok, step, detail))
    print(f"{'  ok ' if ok else '  ✗ FAIL'}  {step}{(' — ' + detail) if detail else ''}")


def expect(cond, step, detail=""):
    record(bool(cond), step, detail)
    return bool(cond)


class Desk:
    """A signed-in person. Tokens are minted server-side so no password is
    handled; every request still passes through the real role checks."""

    def __init__(self, app, username):
        self.c = app.test_client()
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            raise SystemExit(f"no such user: {username}")
        self.username = username
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, path, **kw):
        return self.c.get(path, headers=self.h, environ_base=LAN, **kw)

    def post(self, path, json=None, **kw):
        return self.c.post(path, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def patch(self, path, json=None, **kw):
        return self.c.patch(path, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def clock_in(self):
        """POS actions are gated by require_clocked_in — nobody sells off shift."""
        return self.post("/hr/clock-in", {})


# ── Lookups: name → id, so the data below reads like the real world ───────────

def inv_id(name):
    i = db.session.query(InventoryItem).filter_by(name=name, is_active=True).first()
    return i.id if i else None


def menu_id(name):
    m = db.session.query(MenuItem).filter_by(name=name, is_active=True).first()
    return m.id if m else None


# ── 1. Suppliers ──────────────────────────────────────────────────────────────
# Who the resort actually buys from. A purchase can name a supplier, and without
# these there is nobody to name — which is why 0 suppliers and 1 purchase went
# together.

SUPPLIERS = [
    ("Juja Fresh Produce",        "Mwangi Kariuki",  "+254722410551",
     "Vegetables, fruit, potatoes", "Cash on delivery"),
    ("Thika Road Beverages",      "Alice Wanjiru",   "+254733820114",
     "Beer, spirits, sodas, bottled water", "14 days"),
    ("Naivas Wholesale Thika",    "Peter Gitau",     "+254720337905",
     "Maize flour, cooking oil, sugar, spices", "30 days"),
    ("Lakeview Fish Suppliers",   "Odhiambo Owuor",  "+254711604238",
     "Tilapia, fish fillet", "Cash on delivery"),
    ("Nairobi Spa Essentials",    "Faith Njeri",     "+254701558743",
     "Massage oil, face creams, aromatherapy kits", "30 days"),
    ("TotalEnergies Juja",        "Station Manager", "+254709112000",
     "Outboard petrol, generator fuel", "Prepaid account"),
]


def stock_suppliers(mgr):
    print("\n── suppliers " + "─" * 46)
    for name, contact, tel, supplies, terms in SUPPLIERS:
        r = mgr.post("/suppliers", {
            "name": name, "contact_person": contact, "phone": tel,
            "items_supplied": supplies, "payment_terms": terms,
        })
        # 409 = already on file from an earlier run. Re-running must not fail.
        expect(r.status_code in (201, 409), f"supplier: {name}",
               "already on file" if r.status_code == 409 else "")


# ── 2. Purchases ──────────────────────────────────────────────────────────────
# (inventory item, quantity, total KSh paid, supplier, what the delivery IS)
#
# The last column is the part that gets lost. The system stores a unit — "kg",
# "bottle" — but the lorry arrives in crates, trays and 50kg gunias. Writing
# the real pack next to the number is how the person at the delivery door
# checks the maths instead of guessing.

PURCHASES = [
    ("Potatoes",              "50",  "3500",  "Juja Fresh Produce",      "one 50kg gunia @ KSh 70/kg"),
    ("Tomatoes",              "20",  "2400",  "Juja Fresh Produce",      "two crates @ KSh 120/kg"),
    ("Onions",                "20",  "2000",  "Juja Fresh Produce",      "one 20kg net @ KSh 100/kg"),
    ("Sukuma Wiki",           "20",  "1000",  "Juja Fresh Produce",      "bundles @ KSh 50/kg"),
    ("Mango",                 "10",  "1200",  "Juja Fresh Produce",      "one crate @ KSh 120/kg"),
    ("Passion Fruit",          "5",  "1250",  "Juja Fresh Produce",      "one crate @ KSh 250/kg"),
    ("Lime",                   "3",   "600",  "Juja Fresh Produce",      "one net @ KSh 200/kg"),
    ("Ugali Flour",           "50",  "5000",  "Naivas Wholesale Thika",  "25 x 2kg packs @ KSh 100/kg"),
    ("Cooking Oil",           "20",  "5600",  "Naivas Wholesale Thika",  "one 20L jerrican @ KSh 280/L"),
    ("Spices Mix",             "2",  "1600",  "Naivas Wholesale Thika",  "2kg @ KSh 800/kg"),
    ("Sugar Syrup",            "5",  "2000",  "Naivas Wholesale Thika",  "5L @ KSh 400/L"),
    ("Bread Loaves",           "5",   "800",  "Naivas Wholesale Thika",  "12 x 400g loaves @ KSh 65 each"),
    ("Beef Patties",          "10",  "6000",  "Naivas Wholesale Thika",  "10kg @ KSh 600/kg"),
    ("Chocolate Cake (whole)", "2",  "5000",  "Naivas Wholesale Thika",  "2 whole cakes @ KSh 2,500"),
    ("Tilapia Fillet",        "10",  "7000",  "Lakeview Fish Suppliers", "10kg on ice @ KSh 700/kg"),
    ("Tusker Beer",           "25",  "3000",  "Thika Road Beverages",    "one crate of 25 @ KSh 120/bottle"),
    ("Guinness",              "24",  "3600",  "Thika Road Beverages",    "one crate of 24 @ KSh 150/bottle"),
    ("Soda 330ml",            "24",  "1200",  "Thika Road Beverages",    "one crate of 24 @ KSh 50/bottle"),
    ("Mineral Water 500ml",   "24",   "600",  "Thika Road Beverages",    "one shrink-pack of 24 @ KSh 25"),
    ("Soda Mix",              "24",  "1920",  "Thika Road Beverages",    "one tray of 24 cans @ KSh 80"),
    ("Vodka",                  "6", "10800",  "Thika Road Beverages",    "6 x 750ml @ KSh 1,800"),
    ("White Rum",              "6",  "9600",  "Thika Road Beverages",    "6 x 750ml @ KSh 1,600"),
    ("White Wine",            "12", "18000",  "Thika Road Beverages",    "one case of 12 @ KSh 1,500"),
    ("Massage Oil",            "6",  "7200",  "Nairobi Spa Essentials",  "6 bottles @ KSh 1,200"),
    ("Face Creams",           "10", "15000",  "Nairobi Spa Essentials",  "10 jars @ KSh 1,500"),
    ("Aromatherapy Kit",       "2",  "7000",  "Nairobi Spa Essentials",  "2 sets @ KSh 3,500"),
    ("Petrol (outboard)",    "100", "19500",  "TotalEnergies Juja",      "100L @ KSh 195/L"),
]


def record_purchases(mgr):
    print("\n── purchases (this is what gives ingredients a cost) " + "─" * 7)
    for name, qty, cost, supplier, pack in PURCHASES:
        iid = inv_id(name)
        if not expect(iid is not None, f"stock item exists: {name}"):
            continue
        r = mgr.post("/inventory/purchases", {
            "item_id": iid, "quantity": qty, "actual_cost": cost,
            "supplier_name": supplier,
            # Every purchase needs a receipt — a deliberate control, not a field
            # to work around. A real delivery gets a photo; this names the file
            # the same way the tablet would.
            "receipt_photo_path": f"receipts/opening-stock-{name.lower().replace(' ', '-')[:24]}.jpg",
            "notes": pack,
            # Stable key: re-running the script must not buy the stock twice.
            "idempotency_key": f"catalogue-open-{name}",
        })
        ok = r.status_code in (200, 201)
        dup = r.status_code == 200 and (r.get_json() or {}).get("duplicate")
        unit_cost = (Decimal(cost) / Decimal(qty)).quantize(Decimal("0.01"))
        expect(ok, f"{name}: {qty} for KSh {cost}",
               "already recorded" if dup else f"KSh {unit_cost}/unit — {pack}")


# ── 3. Recipes ────────────────────────────────────────────────────────────────
# Real recipes, cut to what the store actually holds. Where a genuine
# ingredient is missing the note says so rather than pretending.
#
# Bar measures are the standard ones: a 45ml cocktail tot is 0.06 of a 750ml
# bottle; a 150ml glass of wine is 0.2 of the bottle.

CHEF_RECIPES = {          # head chef authors food and the non-alcoholic bar
    "Chips": ([
        ("Potatoes", "0.25"),
        ("Cooking Oil", "0.05"),
    ], "250g potatoes, deep fried"),

    "Ugali & Sukuma": ([
        ("Ugali Flour", "0.2"),
        ("Sukuma Wiki", "0.15"),
        ("Onions", "0.03"),
        ("Tomatoes", "0.05"),
        ("Cooking Oil", "0.02"),
    ], "200g maize meal; sukuma fried with onion and tomato"),

    "Fresh Juice": ([
        ("Mango", "0.2"),
        ("Passion Fruit", "0.1"),
        ("Sugar Syrup", "0.02"),
    ], "mango-passion, the standard house blend"),

    "Chocolate Cake": ([
        ("Chocolate Cake (whole)", "0.0833"),
    ], "one slice = 1/12 of a whole cake"),
}

MANAGER_RECIPES = {       # alcohol and every service belong to the manager
    "Dawa Cocktail": ([
        ("Vodka", "0.06"),
        ("Lime", "0.04"),
        ("Sugar Syrup", "0.02"),
    ], "45ml vodka, lime, sweetener — honey is the real one, not stocked yet"),

    "Mojito": ([
        ("White Rum", "0.06"),
        ("Lime", "0.05"),
        ("Sugar Syrup", "0.02"),
        ("Soda Mix", "0.5"),
    ], "45ml white rum, lime, sugar, soda — mint not stocked yet"),

    "Wine (glass)": ([
        ("White Wine", "0.2"),
    ], "150ml pour from a 750ml bottle"),

    "Boat Ride (30 min)": ([
        ("Petrol (outboard)", "4"),
    ], "outboard burns about 8L/hour"),

    "Fishing Trip (2 hr)": ([
        ("Petrol (outboard)", "12"),
    ], "2 hours out, slower trolling speed"),

    "Full Body Massage (60 min)": ([
        ("Massage Oil", "0.08"),
    ], "about 60ml of oil per hour-long massage"),

    "Aromatherapy Session": ([
        ("Massage Oil", "0.05"),
        ("Aromatherapy Kit", "0.05"),
    ], "carrier oil plus essential oils from the kit"),

    "Beauty Ritual Package": ([
        ("Face Creams", "0.15"),
        ("Massage Oil", "0.05"),
    ], "facial plus a short massage"),
}


def set_recipes(desk, recipes, who):
    print(f"\n── recipes authored by the {who} " + "─" * (28 - len(who)))
    for item_name, (lines, note) in recipes.items():
        mid = menu_id(item_name)
        if not expect(mid is not None, f"menu item exists: {item_name}"):
            continue
        payload = []
        missing = []
        for ing_name, qty in lines:
            iid = inv_id(ing_name)
            (payload if iid else missing).append(
                {"inventory_item_id": iid, "quantity": qty} if iid else ing_name)
        if missing:
            expect(False, f"{item_name}: missing ingredients", ", ".join(missing))
            continue
        # 201 — writing a recipe CREATES the lines (and flips the item to
        # RECIPE tracking). Asserting 200 here was my own bug on the first run.
        r = desk.post(f"/menu/items/{mid}/recipe", {"lines": payload})
        expect(r.status_code == 201, f"{item_name} — {note}",
               f"{len(payload)} ingredient(s)" if r.status_code == 201
               else str(r.get_json())[:70])


# ── 4. Direct links ───────────────────────────────────────────────────────────
# Sell one, deduct one. The club selling a beer is THIS, not a recipe — there is
# nothing to assemble. Tusker and Guinness were already linked; these are the
# non-alcoholic bottles the chef owns.

DIRECT_LINKS = [
    ("Soda (330ml)",  "Soda 330ml"),
    ("Mineral Water", "Mineral Water 500ml"),
]


def link_direct(chef):
    print("\n── direct one-to-one links " + "─" * 32)
    for item_name, stock_name in DIRECT_LINKS:
        mid, iid = menu_id(item_name), inv_id(stock_name)
        if not expect(mid and iid, f"both sides exist: {item_name}"):
            continue
        r = chef.patch(f"/menu/items/{mid}", {
            "inventory_item_id": iid, "stock_tracking": "DIRECT",
        })
        expect(r.status_code == 200, f"{item_name} -> one {stock_name}",
               "" if r.status_code == 200 else str(r.get_json())[:70])


# ── 5. Services ───────────────────────────────────────────────────────────────
# SERVICE is a claim a person signs: "I checked, this consumes nothing we
# track." It is not the same as UNTRACKED, which means nobody has looked yet.

SERVICES = [
    ("Golf Cart Ride", "electric cart, charged off the mains — no stock moves"),
]


def mark_services(mgr):
    print("\n── services that truly consume nothing " + "─" * 20)
    for item_name, why in SERVICES:
        mid = menu_id(item_name)
        if not expect(mid is not None, f"menu item exists: {item_name}"):
            continue
        r = mgr.patch(f"/menu/items/{mid}", {"stock_tracking": "SERVICE"})
        expect(r.status_code == 200, f"{item_name} — {why}",
               "" if r.status_code == 200 else str(r.get_json())[:70])


# ── 6. Retire the litter ──────────────────────────────────────────────────────

def retire_junk(chef):
    """Disable the "Juice XXXXX" rows earlier scenario runs left behind.

    Disabled, never deleted (invariant 6) — audit rows still name them. They
    were more than half of everything that could not be sold, so leaving them
    makes the menu's real state impossible to read at a glance.
    """
    print("\n── retire test litter " + "─" * 37)
    junk = db.session.query(MenuItem).filter(
        MenuItem.is_active == True,                                  # noqa: E712
        MenuItem.name.like("Juice %"),
    ).all()
    if not junk:
        record(True, "no test litter on the menu")
        return
    for m in junk:
        r = chef.post(f"/menu/items/{m.id}/disable")
        expect(r.status_code == 200, f"retired {m.name}")


# ── 7. Prove it ───────────────────────────────────────────────────────────────

def prove_a_sale_moves_stock(waiter, bar, kitchen):
    """Sell one RECIPE item and one DIRECT item, and check the store.

    Configuring the catalogue is not the same as it WORKING. This sells for
    real — open a tab, order, send, receive, ready — and reads the stock ledger
    either side of it. Consumption fires on READY, not on order or serve, so a
    check taken any earlier proves nothing.

    Chips proves the RECIPE path: one sale must remove 250g of potatoes and
    50ml of oil. Tusker proves the DIRECT path: one sale, one bottle, no
    assembly. Those are the two different answers the club needs.
    """
    print("\n── does a sale actually move the store? " + "─" * 19)
    from app.services.stock import get_current_stock

    watch = {n: inv_id(n) for n in ("Potatoes", "Cooking Oil", "Tusker Beer")}
    before = {n: get_current_stock(i) for n, i in watch.items()}

    chips_id, beer_id = menu_id("Chips"), menu_id("Tusker Beer")
    if not expect(chips_id and beer_id, "both test items are on the menu"):
        return

    # Everyone who touches a POS action has to be on shift — require_clocked_in.
    for d in (waiter, bar, kitchen):
        d.clock_in()

    r = waiter.post("/orders", {"items": [
        {"menu_item_id": chips_id, "quantity": 1},
        {"menu_item_id": beer_id,  "quantity": 1},
    ]})
    if not expect(r.status_code == 201, "waiter opens a tab and orders",
                  str(r.get_json())[:70]):
        return
    order = r.get_json()
    expect(waiter.post(f"/orders/{order['id']}/send").status_code == 200,
           "order goes to the bar and kitchen")

    # receive + ready are STATION actions and the waiter cannot do them, so each
    # ticket goes to the desk that actually makes it: chips to the kitchen, beer
    # to the bar. Sending both to one desk would 403 on the other station's
    # ticket — that is _can_operate_station working, not an obstacle to route
    # around.
    tab = waiter.get(f"/tabs/{order['tab_id']}").get_json()
    for item in tab["orders"][-1]["items"]:
        # Route by the MENU ITEM's station, read from the catalogue. The tab
        # payload does not carry prep_station, and defaulting to the bar sent
        # the chips to the wrong counter — which the station check then refused,
        # correctly. Ask the thing that actually knows.
        mi = db.session.query(MenuItem).filter_by(name=item["name"]).first()
        desk = kitchen if mi and mi.prep_station == "KITCHEN" else bar
        desk.post(f"/order-items/{item['id']}/receive")
        rr = desk.post(f"/order-items/{item['id']}/ready")
        expect(rr.status_code == 200,
               f"{item['name']} made at the {mi.prep_station.lower()} and marked ready",
               "" if rr.status_code == 200 else str(rr.get_json())[:60])

    after = {n: get_current_stock(i) for n, i in watch.items()}
    for name, want in (("Potatoes", "0.25"), ("Cooking Oil", "0.05"),
                       ("Tusker Beer", "1")):
        moved = before[name] - after[name]
        expect(moved == Decimal(want),
               f"{name}: {before[name]} -> {after[name]}",
               f"took {moved}, expected {want}")


def show_margins(mgr):
    """What the owner could never see before: the shilling behind each plate."""
    print("\n── margins, now that ingredients have costs " + "─" * 15)
    rows = mgr.get("/menu/items").get_json()
    priced = [i for i in rows if i.get("food_cost") is not None]
    priced.sort(key=lambda i: Decimal(i["food_cost_pct"]), reverse=True)
    print(f"     {'item':30} {'price':>8} {'cost':>8} {'margin':>9}  cost%")
    for i in priced[:12]:
        print(f"     {i['name'][:29]:30} {i['price']:>8} {i['food_cost']:>8} "
              f"{i['gross_margin']:>9}  {i['food_cost_pct']}%")
    expect(len(priced) > 0, f"{len(priced)} item(s) now show a real margin")


# ── Report ────────────────────────────────────────────────────────────────────

def report():
    print("\n── where the catalogue stands now " + "─" * 25)
    rows = db.session.execute(db.text(
        "SELECT stock_tracking, COUNT(*) FROM menu_items "
        "WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC")).all()
    total = sum(c for _, c in rows)
    sellable = sum(c for t, c in rows if t != "UNTRACKED")
    for t, c in rows:
        print(f"     {t:11} {c}")
    pct = (sellable * 100 // total) if total else 0
    print(f"     {'':11} → {sellable}/{total} sellable ({pct}%)")

    costed = db.session.execute(db.text(
        "SELECT COUNT(*), SUM(CASE WHEN cost_per_unit > 0 THEN 1 ELSE 0 END) "
        "FROM inventory_items WHERE is_active=1")).first()
    print(f"\n     ingredients with a known cost: {costed[1]}/{costed[0]}")

    still_dark = db.session.execute(db.text(
        "SELECT name FROM menu_items WHERE is_active=1 AND stock_tracking='UNTRACKED' "
        "ORDER BY name")).all()
    if still_dark:
        print("\n     still UNTRACKED (cannot be sold):")
        for (n,) in still_dark:
            print(f"       • {n}")


def run(app):
    with app.app_context():
        mgr    = Desk(app, "brian.mwangi")      # manager: alcohol + services
        chef   = Desk(app, "cynthia.achieng")   # head chef: food + soft drinks
        waiter = Desk(app, "peter.mwendwa")     # sells it
        bar    = Desk(app, "david.otieno")      # makes it, marks it ready

        stock_suppliers(mgr)
        record_purchases(mgr)
        set_recipes(chef, CHEF_RECIPES, "head chef")
        set_recipes(mgr, MANAGER_RECIPES, "manager")
        link_direct(chef)
        mark_services(mgr)
        retire_junk(chef)
        prove_a_sale_moves_stock(waiter, bar, chef)
        show_margins(mgr)
        report()


if __name__ == "__main__":
    run(create_app("development"))

    failed = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} steps passed")
    if failed:
        print(f"\n{len(failed)} FAILED:")
        for _, step, detail in failed:
            print(f"  • {step}  {detail}")
    sys.exit(1 if failed else 0)
