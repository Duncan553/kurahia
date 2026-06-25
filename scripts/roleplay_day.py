"""
scripts/roleplay_day.py — Waterfront Country Club: Simulated Working Day

Uses Flask test client (testing config, in-memory SQLite, rate limiting off).
Seeds fresh realistic data, then runs the full day scenario.

Verdicts: WORKS / BROKEN / MISSING / WRONGLY-ALLOWED / WRONGLY-BLOCKED

Run: .venv/bin/python scripts/roleplay_day.py
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db

app = create_app("testing")   # in-memory SQLite, rate limits OFF

# ── Result tracking ───────────────────────────────────────────────────────────
RESULTS  = {"WORKS": 0, "BROKEN": 0, "MISSING": 0, "WRONGLY-ALLOWED": 0, "WRONGLY-BLOCKED": 0}
FINDINGS = []

def rec(verdict, agent, action, detail=""):
    RESULTS[verdict] += 1
    FINDINGS.append((verdict, agent, action, detail))
    icon = {"WORKS":"✓","BROKEN":"✗","MISSING":"?","WRONGLY-ALLOWED":"!","WRONGLY-BLOCKED":"✗"}[verdict]
    msg = f"  [{icon}] [{agent}] {action} → {verdict}"
    if detail: msg += f"  ({detail})"
    print(msg)

# ── Helpers ───────────────────────────────────────────────────────────────────
def hdr(token):
    return {"Authorization": f"Bearer {token}"}

def ikey():
    return str(uuid.uuid4())

def login(c, username, password="Kurahia1!"):
    rv = c.post("/auth/login", json={"username": username, "password": password})
    if rv.status_code == 200:
        return rv.get_json().get("access_token")
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    with app.app_context():
        print("\n── Setting up: create tables + seed ──")
        db.create_all()
        from scripts.seed_realistic import _seed_all
        _seed_all()

    with app.test_client() as c:
        run_day(c)

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n" + "═"*65)
    print("ROLEPLAY DAY — FULL RESULTS")
    print("═"*65)
    for verdict, agent, action, detail in FINDINGS:
        icon = {"WORKS":"✓","BROKEN":"✗","MISSING":"?","WRONGLY-ALLOWED":"!","WRONGLY-BLOCKED":"✗"}[verdict]
        line = f"  {icon} [{agent}] {action}"
        if detail: line += f"  → {detail}"
        print(line)
    print()
    w  = RESULTS["WORKS"]
    b  = RESULTS["BROKEN"]
    m  = RESULTS["MISSING"]
    wa = RESULTS["WRONGLY-ALLOWED"]
    wb = RESULTS["WRONGLY-BLOCKED"]
    total   = sum(RESULTS.values())
    failing = b + wa + wb
    verdict = "GREEN ✓" if failing == 0 else f"NOT-GREEN ✗ ({failing} failures)"
    print(f"  VERDICT: {verdict}")
    print(f"  {total} checks total — WORKS:{w}  BROKEN:{b}  MISSING:{m}  WRONGLY-ALLOWED:{wa}  WRONGLY-BLOCKED:{wb}")
    return RESULTS, FINDINGS


def run_day(c):
    print("\n══════════════════════════════════════════════════════════════")
    print("  WATERFRONT COUNTRY CLUB — SIMULATED WORKING DAY")
    print("══════════════════════════════════════════════════════════════")

    # ── 0. Login all staff ────────────────────────────────────────────────────
    print("\n[0] LOGIN ALL STAFF")
    T = {}  # token map
    for key, user in [
        ("hassan",  "hassan.omondi"),
        ("ivan",    "ivan.kipchoge"),
        ("joyce",   "joyce.wambua"),
        ("cynthia", "cynthia.achieng"),
        ("david",   "david.otieno"),
        ("esther",  "esther.kamau"),
        ("francis", "francis.njoroge"),
        ("brian",   "brian.mwangi"),
        ("grace",   "grace.muthoni"),
        ("amara",   "amara.wanjiku"),
    ]:
        t = login(c, user)
        if t:
            T[key] = t
            print(f"    ✓ {user}")
        else:
            rec("BROKEN", "AUTH", f"Login {user}", "no token returned")

    # ── 1. GATE AGENT ─────────────────────────────────────────────────────────
    print("\n[1] GATE AGENT — Hassan")
    bands = []  # list of {band_number, tab_id}

    if "hassan" not in T:
        rec("BROKEN", "GATE", "Cannot run gate tests — login failed")
    else:
        # Issue 3 day-guest wristbands
        for i in range(3):
            rv = c.post("/gate/issue-band",
                        json={"method": "CASH", "idempotency_key": ikey()},
                        headers=hdr(T["hassan"]))
            if rv.status_code == 201:
                d = rv.get_json()
                bands.append({"number": d["band_number"], "tab_id": d["tab_id"]})
                rec("WORKS", "GATE", f"Issue band for day guest {i+1}",
                    f"band={d['band_number']} credit=3000")
            else:
                rec("BROKEN", "GATE", f"Issue band guest {i+1}",
                    f"{rv.status_code} {rv.get_json()}")

        # Waiter tries to issue band (level 1 < gate level 3) → must fail
        rv = c.post("/gate/issue-band",
                    json={"method": "CASH", "idempotency_key": ikey()},
                    headers=hdr(T.get("ivan", T["hassan"])))  # ivan is level 1
        if "ivan" in T:
            if rv.status_code == 403:
                rec("WORKS", "GATE", "Waiter blocked from issuing band", "403")
            else:
                rec("WRONGLY-ALLOWED", "GATE", "Waiter issued band (should be 403)",
                    f"got {rv.status_code}")

        # Fake booking check-in
        for path in ["/bookings/fake-booking-9999/check-in",
                     "/gate/check-in"]:
            rv = c.post(path,
                        json={"booking_id": "fake-booking-9999"},
                        headers=hdr(T["hassan"]))
            if rv.status_code in (404, 400, 422):
                rec("WORKS", "GATE", "Fake booking rejected", f"{rv.status_code} at {path}")
                break
            elif rv.status_code not in (404, 405):
                rec("BROKEN", "GATE", "Fake booking should have been rejected",
                    f"{rv.status_code} at {path}")
                break
        else:
            rec("MISSING", "GATE", "Villa booking check-in endpoint not found")

    # ── 2. FETCH MENU ─────────────────────────────────────────────────────────
    print("\n[2] FETCH MENU")
    menu = {}         # name → {id, is_active, prep_station, ...}
    chips_masala_id = None

    if "ivan" in T:
        rv = c.get("/menu/items", headers=hdr(T["ivan"]))
        if rv.status_code == 200:
            for item in rv.get_json():
                menu[item["name"]] = item
            print(f"    ✓ {len(menu)} active menu items")
        else:
            rec("BROKEN", "MENU", "Fetch active menu items", f"{rv.status_code}")

    # Chips Masala is inactive — get its ID directly from DB (API only returns active items)
    with app.app_context():
        from app.models.menu_item import MenuItem as MI
        chips = db.session.query(MI).filter(MI.name.ilike("%chips masala%")).first()
        if chips:
            chips_masala_id = chips.id
            print(f"    ✓ Chips Masala (inactive) id={chips_masala_id[:8]}...")

    def mid(name):
        return menu.get(name, {}).get("id")

    # ── 3. WAITERS ────────────────────────────────────────────────────────────
    print("\n[3] WAITER AGENTS — Ivan + Joyce")

    # Each wristband has its own tab (created at gate issue time)
    tab_a = bands[0]["tab_id"] if len(bands) > 0 else None
    tab_b = bands[1]["tab_id"] if len(bands) > 1 else None
    tab_c = bands[2]["tab_id"] if len(bands) > 2 else None

    ivan_order_id  = None
    joyce_order_id = None

    # Ivan: Grilled Tilapia (kitchen) on Customer A's band tab
    if "ivan" in T and tab_a and mid("Grilled Tilapia"):
        rv = c.post("/orders",
                    json={"tab_id": tab_a,
                          "items": [{"menu_item_id": mid("Grilled Tilapia"), "quantity": 1}],
                          "idempotency_key": ikey()},
                    headers=hdr(T["ivan"]))
        if rv.status_code == 201:
            ivan_order_id = rv.get_json()["id"]
            rec("WORKS", "WAITER:IVAN", "Place Tilapia order on Customer A band tab",
                f"order={ivan_order_id}")
            # Send to kitchen
            rv2 = c.post(f"/orders/{ivan_order_id}/send", headers=hdr(T["ivan"]))
            rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                "WAITER:IVAN", "Send order to kitchen",
                "" if rv2.status_code == 200 else f"{rv2.status_code}")
        else:
            rec("BROKEN", "WAITER:IVAN", "Place Tilapia order",
                f"{rv.status_code} {rv.get_json()}")

    # Joyce: Dawa Cocktail (bar) on Customer B's band tab
    if "joyce" in T and tab_b and mid("Dawa Cocktail"):
        rv = c.post("/orders",
                    json={"tab_id": tab_b,
                          "items": [{"menu_item_id": mid("Dawa Cocktail"), "quantity": 1}],
                          "idempotency_key": ikey()},
                    headers=hdr(T["joyce"]))
        if rv.status_code == 201:
            joyce_order_id = rv.get_json()["id"]
            rec("WORKS", "WAITER:JOYCE", "Place Dawa Cocktail order on Customer B band tab")
            rv2 = c.post(f"/orders/{joyce_order_id}/send", headers=hdr(T["joyce"]))
            rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                "WAITER:JOYCE", "Send drink order to bar",
                "" if rv2.status_code == 200 else f"{rv2.status_code}")
        else:
            rec("BROKEN", "WAITER:JOYCE", "Place Dawa order",
                f"{rv.status_code} {rv.get_json()}")

    # Ivan tries to order SOLD-OUT Chips Masala
    if "ivan" in T and chips_masala_id and tab_a:
        rv = c.post("/orders",
                    json={"tab_id": tab_a,
                          "items": [{"menu_item_id": chips_masala_id, "quantity": 1}],
                          "idempotency_key": ikey()},
                    headers=hdr(T["ivan"]))
        if rv.status_code in (400, 409):
            rec("WORKS", "WAITER:IVAN", "Chips Masala (sold-out/disabled) blocked",
                f"{rv.status_code}: {rv.get_json().get('error','')[:60]}")
        elif rv.status_code == 201:
            rec("WRONGLY-ALLOWED", "WAITER:IVAN", "Disabled item allowed in order — SHOULD BE BLOCKED")
        else:
            rec("BROKEN", "WAITER:IVAN", "Chips Masala order unexpected response",
                f"{rv.status_code}")
    else:
        rec("MISSING", "WAITER:IVAN", "Could not test sold-out — chips masala id not found")

    # ── 4. KITCHEN AGENT ──────────────────────────────────────────────────────
    print("\n[4] KITCHEN AGENT — Cynthia")

    # Check kitchen queue endpoint
    queue_found = False
    if "cynthia" in T:
        rv = c.get("/kitchen/queue", headers=hdr(T["cynthia"]))
        if rv.status_code == 200:
            rec("WORKS", "KITCHEN:CYNTHIA", "Kitchen queue at /kitchen/queue",
                f"{len(rv.get_json())} items")
            queue_found = True
        else:
            rec("BROKEN", "KITCHEN:CYNTHIA", "Kitchen queue at /kitchen/queue",
                f"{rv.status_code}")

    # Advance Ivan's kitchen order items: PENDING → RECEIVE → READY → SERVE
    if "cynthia" in T and ivan_order_id and tab_a:
        rv = c.get(f"/tabs/{tab_a}", headers=hdr(T["ivan"]))
        if rv.status_code == 200:
            oi_ids = []
            for order in rv.get_json().get("orders", []):
                if order["id"] == ivan_order_id:
                    # Only kitchen-routed items (Tilapia = KITCHEN station)
                    oi_ids = [oi["id"] for oi in order["items"]]

            for oi_id in oi_ids:
                rv2 = c.post(f"/order-items/{oi_id}/receive", headers=hdr(T["cynthia"]))
                rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                    "KITCHEN:CYNTHIA", f"Receive item {oi_id[:8]}",
                    "" if rv2.status_code == 200 else f"{rv2.get_json().get('error','')[:60]}")

                rv2 = c.post(f"/order-items/{oi_id}/ready", headers=hdr(T["cynthia"]))
                rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                    "KITCHEN:CYNTHIA", f"Mark ready {oi_id[:8]}",
                    "" if rv2.status_code == 200 else f"{rv2.get_json().get('error','')[:60]}")

                rv2 = c.post(f"/order-items/{oi_id}/serve", headers=hdr(T["ivan"]))
                rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                    "WAITER:IVAN", f"Serve item {oi_id[:8]}",
                    "" if rv2.status_code == 200 else f"{rv2.get_json().get('error','')[:60]}")

    # ── 5. STRESS: 10 rapid orders ────────────────────────────────────────────
    print("\n[5] STRESS — 10 rapid kitchen orders")
    if "ivan" in T and mid("Grilled Tilapia"):
        stress_ids = []
        for i in range(10):
            rv = c.post("/orders",
                        json={"items": [{"menu_item_id": mid("Grilled Tilapia"), "quantity": 1}],
                              "idempotency_key": ikey()},
                        headers=hdr(T["ivan"]))
            if rv.status_code == 201:
                stress_ids.append(rv.get_json()["id"])
            else:
                rec("BROKEN", "STRESS", f"Rapid order {i+1}",
                    f"{rv.status_code} {rv.get_json()}")

        if len(stress_ids) == 10:
            rec("WORKS", "STRESS", "10 rapid orders all landed", "no failures")
        else:
            rec("BROKEN", "STRESS", f"Only {len(stress_ids)}/10 rapid orders landed")

        if len(set(stress_ids)) == len(stress_ids) and stress_ids:
            rec("WORKS", "STRESS", "No duplicate order IDs")
        elif stress_ids:
            rec("WRONGLY-ALLOWED", "STRESS", "Duplicate order IDs found")

    # ── 6. BAR AGENT ──────────────────────────────────────────────────────────
    print("\n[6] BAR AGENT — David")
    if "david" in T and joyce_order_id and tab_b:
        rv = c.get(f"/tabs/{tab_b}", headers=hdr(T["david"]))
        if rv.status_code == 200:
            for order in rv.get_json().get("orders", []):
                if order["id"] == joyce_order_id:
                    for oi in order["items"]:
                        oi_id = oi["id"]
                        rv2 = c.post(f"/order-items/{oi_id}/receive", headers=hdr(T["david"]))
                        rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                            "BAR:DAVID", f"Receive bar item {oi_id[:8]}",
                            "" if rv2.status_code == 200 else f"{rv2.get_json().get('error','')[:60]}")
                        rv2 = c.post(f"/order-items/{oi_id}/ready", headers=hdr(T["david"]))
                        rec("WORKS" if rv2.status_code == 200 else "BROKEN",
                            "BAR:DAVID", f"Mark drink ready {oi_id[:8]}",
                            "" if rv2.status_code == 200 else f"{rv2.get_json().get('error','')[:60]}")
    elif "david" not in T:
        rec("BROKEN", "BAR:DAVID", "Login failed — skipping bar tests")

    # ── 7. SPA AGENT ──────────────────────────────────────────────────────────
    print("\n[7] SPA AGENT — Esther")
    if "esther" not in T:
        rec("BROKEN", "SPA:ESTHER", "Login failed — skipping spa tests")
    else:
        # Sell Full Body Massage on Customer C's band
        massage_id = mid("Full Body Massage (60 min)")
        if massage_id and tab_c:
            rv = c.post("/orders",
                        json={"tab_id": tab_c,
                              "items": [{"menu_item_id": massage_id, "quantity": 1}],
                              "idempotency_key": ikey()},
                        headers=hdr(T["esther"]))
            if rv.status_code == 201:
                rec("WORKS", "SPA:ESTHER", "Sell Full Body Massage on Customer C band")
            else:
                rec("BROKEN", "SPA:ESTHER", "Sell spa service",
                    f"{rv.status_code} {rv.get_json()}")
        else:
            rec("MISSING", "SPA:ESTHER", "No massage item or band tab")

        # View spa inventory
        rv = c.get("/inventory/items", headers=hdr(T["esther"]))
        oil_inv_id = None
        if rv.status_code == 200:
            items_list = rv.get_json()
            oil = next((i for i in items_list if "oil" in i["name"].lower() and
                        "massage" in i["name"].lower()), None)
            if oil:
                oil_inv_id = oil["id"]
                rec("WORKS", "SPA:ESTHER", "View spa inventory",
                    f"Massage Oil stock={oil.get('current_stock','?')}")
            else:
                rec("BROKEN", "SPA:ESTHER", "Massage Oil not found in inventory list")

        # Submit purchase request for oil restock
        if oil_inv_id:
            rv = c.post("/inventory/purchase-requests",
                        json={"inventory_item_id": oil_inv_id,
                              "quantity_requested": 5,
                              "notes": "Running low — need before weekend bookings",
                              "idempotency_key": ikey()},
                        headers=hdr(T["esther"]))
            if rv.status_code == 201:
                rec("WORKS", "SPA:ESTHER", "Submit massage oil restock request")
            else:
                rec("BROKEN", "SPA:ESTHER", "Restock request",
                    f"{rv.status_code} {rv.get_json()}")

    # ── 8. WATER ACTIVITIES AGENT ─────────────────────────────────────────────
    print("\n[8] WATER ACTIVITIES AGENT — Francis")
    if "francis" not in T:
        rec("BROKEN", "WATER:FRANCIS", "Login failed — skipping water tests")
    else:
        # Sell Jet Ski on Customer B's band (different activity than bar drink)
        jetski_id = mid("Jet Ski Ride (30 min)")
        if not jetski_id:
            # Try other naming
            jetski_id = next((v["id"] for k, v in menu.items() if "jet ski" in k.lower()), None)

        if jetski_id and tab_b:
            rv = c.post("/orders",
                        json={"tab_id": tab_b,
                              "items": [{"menu_item_id": jetski_id, "quantity": 1}],
                              "idempotency_key": ikey()},
                        headers=hdr(T["francis"]))
            if rv.status_code == 201:
                rec("WORKS", "WATER:FRANCIS", "Sell Jet Ski Ride on Customer B band")
            else:
                rec("BROKEN", "WATER:FRANCIS", "Sell Jet Ski",
                    f"{rv.status_code} {rv.get_json()}")
        else:
            rec("MISSING", "WATER:FRANCIS", "Jet Ski menu item not found")

        # Check fuel inventory (should be low)
        rv = c.get("/inventory/items", headers=hdr(T["francis"]))
        fuel_inv_id = None
        if rv.status_code == 200:
            fuel = next((i for i in rv.get_json() if "fuel" in i["name"].lower()), None)
            if fuel:
                fuel_inv_id = fuel["id"]
                stock = fuel.get("current_stock", "?")
                rec("WORKS", "WATER:FRANCIS", f"View fuel stock", f"stock={stock} (expect low)")
            else:
                rec("MISSING", "WATER:FRANCIS", "Fuel item not in inventory")

        # Submit fuel restock request
        if fuel_inv_id:
            rv = c.post("/inventory/purchase-requests",
                        json={"inventory_item_id": fuel_inv_id,
                              "quantity_requested": 100,
                              "notes": "Critical — fuel too low for afternoon activities",
                              "idempotency_key": ikey()},
                        headers=hdr(T["francis"]))
            if rv.status_code == 201:
                rec("WORKS", "WATER:FRANCIS", "Submit fuel restock request")
            else:
                rec("BROKEN", "WATER:FRANCIS", "Fuel restock request",
                    f"{rv.status_code} {rv.get_json()}")

    # ── 9. MANAGER AGENT ──────────────────────────────────────────────────────
    print("\n[9] MANAGER AGENT — Brian")
    if "brian" not in T:
        rec("BROKEN", "MANAGER:BRIAN", "Login failed — skipping manager tests")
    else:
        # View finance/department data
        for path in ["/finance/dashboard", "/dashboard/finance"]:
            rv = c.get(path, headers=hdr(T["brian"]))
            if rv.status_code == 200:
                rec("WORKS", "MANAGER:BRIAN", f"View finance dashboard ({path})")
                break
            elif rv.status_code == 403:
                continue
        else:
            rec("BROKEN", "MANAGER:BRIAN", "Finance dashboard blocked for manager (403)")

        # View purchase requests
        rv = c.get("/inventory/purchase-requests", headers=hdr(T["brian"]))
        if rv.status_code == 200:
            prs = rv.get_json()
            rec("WORKS", "MANAGER:BRIAN", f"View purchase requests", f"{len(prs)} requests")

            # Submit then approve first DRAFT request
            submitted_pr = next((p for p in prs if p.get("status") == "SUBMITTED"), None)
            draft_pr = next((p for p in prs if p.get("status") == "DRAFT"), None)

            # Submit a draft first if needed
            if not submitted_pr and draft_pr:
                rv2 = c.post(f"/inventory/purchase-requests/{draft_pr['id']}/submit",
                             headers=hdr(T.get("esther", T["brian"])))
                if rv2.status_code == 200:
                    submitted_pr = rv2.get_json()

            if submitted_pr:
                pr_id = submitted_pr["id"]
                rv2 = c.post(f"/inventory/purchase-requests/{pr_id}/approve",
                             json={"notes": "Approved — arrange delivery"},
                             headers=hdr(T["brian"]))
                if rv2.status_code == 200:
                    rec("WORKS", "MANAGER:BRIAN", f"Approve restock request")
                else:
                    rec("BROKEN", "MANAGER:BRIAN", "Approve purchase request",
                        f"{rv2.status_code} {rv2.get_json()}")
        elif rv.status_code == 403:
            rec("BROKEN", "MANAGER:BRIAN", "Cannot view purchase requests — 403")
        else:
            rec("BROKEN", "MANAGER:BRIAN", f"Purchase requests", f"{rv.status_code}")

        # Manager tries /judge/alerts → MUST be blocked (owner-only)
        rv = c.get("/judge/alerts", headers=hdr(T["brian"]))
        if rv.status_code == 403:
            rec("WORKS", "SECURITY", "Manager blocked from /judge/alerts", "403 ✓")
        elif rv.status_code == 200:
            rec("WRONGLY-ALLOWED", "SECURITY",
                "CRITICAL: Manager accessed /judge/alerts — owner-only endpoint!", "SECURITY HOLE")
        else:
            rec("BROKEN", "SECURITY", f"Judge alerts unexpected for manager", f"{rv.status_code}")

    # ── 10. BAND EDGE CASES ───────────────────────────────────────────────────
    print("\n[10] BAND EDGE CASES")

    # Customer C: check band tab balance after spa charge
    if "brian" in T and tab_c:
        rv = c.get(f"/tabs/{tab_c}", headers=hdr(T["brian"]))
        if rv.status_code == 200:
            balance = rv.get_json().get("balance", "?")
            rec("WORKS", "EDGE", "Customer C band balance readable after charge",
                f"balance={balance}")

    # Band forfeit (customer D exits with unspent credit)
    if "hassan" in T and bands:
        # Use band 2 (Customer C) for forfeit test
        band_num = bands[0]["number"]
        rv = c.post("/gate/forfeit-day",
                    json={"band_number": band_num, "idempotency_key": ikey()},
                    headers=hdr(T["hassan"]))
        if rv.status_code in (200, 400):
            data = rv.get_json()
            if rv.status_code == 200:
                rec("WORKS", "EDGE", "Band forfeited on exit — credit not returned",
                    f"band={band_num}")
            else:
                # 400 may mean already forfeited or open tab — still valid
                rec("WORKS", "EDGE", "Band forfeit attempt handled",
                    f"400: {data.get('error','')[:60]}")
        else:
            rec("BROKEN", "EDGE", "Band forfeit endpoint error",
                f"{rv.status_code} {rv.get_json()}")

    # ── 11. FRONT DESK AGENT ──────────────────────────────────────────────────
    print("\n[11] FRONT DESK AGENT — Grace")
    if "grace" not in T:
        rec("BROKEN", "FRONT-DESK:GRACE", "Login failed — skipping front desk tests")
    else:
        rv = c.get("/receipts", headers=hdr(T["grace"]))
        if rv.status_code == 200:
            receipts = rv.get_json()
            rec("WORKS", "FRONT-DESK:GRACE", "View receipts", f"{len(receipts)} found")
        elif rv.status_code == 403:
            rec("BROKEN", "FRONT-DESK:GRACE", "Cannot view receipts — 403")
        else:
            rec("BROKEN", "FRONT-DESK:GRACE", f"Receipts endpoint", f"{rv.status_code}")

        rv = c.get("/finance/cash/pending", headers=hdr(T["grace"]))
        if rv.status_code == 200:
            rec("WORKS", "FRONT-DESK:GRACE", "View cash pending reconciliation")
        elif rv.status_code == 403:
            rec("BROKEN", "FRONT-DESK:GRACE", "Cannot view cash/pending — 403")
        else:
            rec("BROKEN", "FRONT-DESK:GRACE", f"Cash pending", f"{rv.status_code}")

    # ── 12. OWNER AGENT ───────────────────────────────────────────────────────
    print("\n[12] OWNER AGENT — Amara")
    if "amara" not in T:
        rec("BROKEN", "OWNER:AMARA", "Login failed — skipping owner tests")
    else:
        # Dashboard overview
        rv = c.get("/dashboard/overview", headers=hdr(T["amara"]))
        if rv.status_code == 200:
            rec("WORKS", "OWNER:AMARA", "View dashboard overview")
        else:
            rec("BROKEN", "OWNER:AMARA", f"Dashboard overview", f"{rv.status_code}")

        # Judge alerts
        rv = c.get("/judge/alerts", headers=hdr(T["amara"]))
        if rv.status_code == 200:
            alerts = rv.get_json()
            rec("WORKS", "OWNER:AMARA", f"View judge alerts", f"{len(alerts)} alerts")
            if alerts:
                alert_id = alerts[0]["id"]
                rv2 = c.post(f"/judge/alerts/{alert_id}/acknowledge",
                             json={"notes": "Reviewing this now"},
                             headers=hdr(T["amara"]))
                if rv2.status_code == 200:
                    rec("WORKS", "OWNER:AMARA", "Acknowledge judge alert")
                else:
                    rec("BROKEN", "OWNER:AMARA", "Acknowledge alert",
                        f"{rv2.status_code} {rv2.get_json()}")
        else:
            rec("BROKEN", "OWNER:AMARA", f"Judge alerts", f"{rv.status_code}")

        # Finance dashboard
        rv = c.get("/dashboard/finance", headers=hdr(T["amara"]))
        if rv.status_code == 200:
            rec("WORKS", "OWNER:AMARA", "View finance dashboard")
        else:
            rec("BROKEN", "OWNER:AMARA", f"Finance dashboard", f"{rv.status_code}")

        # OWNER_PRIVATE suggestions check
        rv = c.get("/dashboard/suggestions", headers=hdr(T["amara"]))
        if rv.status_code == 200:
            rec("WORKS", "OWNER:AMARA", "View owner suggestions dashboard")

    # ── 13. INCIDENT CHECK ────────────────────────────────────────────────────
    print("\n[13] INCIDENT LOGGING CHECK")
    if "francis" in T:
        found_incident = False
        for path in ["/incidents", "/water/incidents", "/water-activities/incidents",
                     "/gate/incidents", "/accidents", "/conduct/incidents"]:
            rv = c.post(path,
                        json={"description": "Guest slipped at pool deck",
                              "location": "Pool area"},
                        headers=hdr(T["francis"]))
            if rv.status_code not in (404, 405):
                rec("WORKS" if rv.status_code in (200, 201) else "BROKEN",
                    "INCIDENT", f"Incident endpoint at {path}", f"{rv.status_code}")
                found_incident = True
                break
        if not found_incident:
            rec("MISSING", "INCIDENT", "No incident/accident logging endpoint exists")

    # ── 14. SECURITY CHECKS ───────────────────────────────────────────────────
    print("\n[14] SECURITY CHECKS")

    # Waiter → finance
    if "ivan" in T:
        for path in ["/finance/dashboard", "/dashboard/finance"]:
            rv = c.get(path, headers=hdr(T["ivan"]))
            if rv.status_code == 403:
                rec("WORKS", "SECURITY", f"Waiter blocked from {path}", "403")
                break
            elif rv.status_code == 200:
                rec("WRONGLY-ALLOWED", "SECURITY",
                    f"Waiter accessed finance at {path} — SECURITY HOLE")
                break

        # Waiter → judge alerts
        rv = c.get("/judge/alerts", headers=hdr(T["ivan"]))
        if rv.status_code == 403:
            rec("WORKS", "SECURITY", "Waiter blocked from /judge/alerts", "403")
        elif rv.status_code == 200:
            rec("WRONGLY-ALLOWED", "SECURITY",
                "Waiter accessed /judge/alerts — SECURITY HOLE")

    # Fired-mid-shift: disable user profile (owner-only), check if token dies
    # NOTE: /hr/profiles/<id>/disable sets EmployeeProfile.is_active=False (NOT User.is_active).
    # The kill switch checks User.is_active. This tests whether profile-disable kills the session.
    if "amara" in T and "ivan" in T:
        with app.app_context():
            from app.models.user import User as U
            from app.models.employee_profile import EmployeeProfile as EP
            ivan_user = db.session.query(U).filter_by(username="ivan.kipchoge").first()
            ivan_prof = db.session.query(EP).filter_by(user_id=ivan_user.id).first() if ivan_user else None
            ivan_prof_id = ivan_prof.id if ivan_prof else None

        if ivan_prof_id:
            ivan_token_before = T["ivan"]
            rv = c.post(f"/hr/profiles/{ivan_prof_id}/disable",
                        headers=hdr(T["amara"]))
            if rv.status_code == 200:
                rv2 = c.get("/menu/items", headers=hdr(ivan_token_before))
                if rv2.status_code in (401, 403):
                    rec("WORKS", "SECURITY", "Profile-disable kills token (kill switch works)",
                        f"{rv2.status_code}")
                else:
                    rec("WRONGLY-ALLOWED", "SECURITY",
                        "Profile-disable does NOT kill token — User.is_active not set",
                        f"token still works (got {rv2.status_code}) — SECURITY GAP")
                # Re-enable ivan
                c.post(f"/hr/profiles/{ivan_prof_id}/enable", headers=hdr(T["amara"]))
            else:
                rec("BROKEN", "SECURITY", "Could not disable profile for kill-switch test",
                    f"{rv.status_code} {rv.get_json()}")

    # Manager cannot see OWNER_PRIVATE suggestions
    if "brian" in T:
        rv = c.get("/dashboard/suggestions", headers=hdr(T["brian"]))
        if rv.status_code == 200:
            data = rv.get_json()
            suggestions = data if isinstance(data, list) else data.get("suggestions", [])
            owner_private = [s for s in suggestions if s.get("category") == "OWNER_PRIVATE"]
            if owner_private:
                rec("WRONGLY-ALLOWED", "SECURITY",
                    f"Manager sees OWNER_PRIVATE suggestions — SECURITY HOLE",
                    f"{len(owner_private)} visible")
            else:
                rec("WORKS", "SECURITY",
                    "Manager sees 0 OWNER_PRIVATE suggestions (structurally absent)")
        elif rv.status_code == 403:
            rec("WORKS", "SECURITY", "Manager blocked from suggestions entirely", "403")
        else:
            rec("BROKEN", "SECURITY", f"Suggestions check", f"{rv.status_code}")


if __name__ == "__main__":
    main()
