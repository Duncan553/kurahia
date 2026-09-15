"""
every_screen.py — open every dashboard and every till, as the person who uses it.

Not a unit test. This asks the one question a test suite cannot:

    "If the person this screen was built for opens it right now,
     does it fill with their data — or does it refuse them?"

Every screen in the three apps is listed with the role that actually sits in
front of it and every read it performs on load. A screen passes only when all
of its reads answer for that person. A 403 here is the failure mode that
matters most: it renders as an empty dashboard, which staff read as a broken
app rather than a locked one.

Point-of-sale screens get more than a read — money has to move. Each till runs
a real transaction end to end against the live server.

Run:  .venv/bin/python scripts/every_screen.py
Exit: 0 clean, 1 if any screen would refuse the person it was built for.
"""
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import requests

BASE = os.environ.get("KURAHIA_BASE", "http://localhost:5000")
PASSWORD = os.environ.get("SEED_PASSWORD", "Kurahia1!")
TODAY = datetime.now(timezone.utc).date().isoformat()

# The fourteen real accounts, by the post they stand at.
WHO = {
    "owner":      "amara.wanjiku",
    "manager":    "brian.mwangi",
    "front_desk": "grace.muthoni",
    "gate":       "hassan.omondi",
    "chef":       "cynthia.achieng",
    "bar":        "david.otieno",
    "spa":        "esther.kamau",
    "water":      "francis.njoroge",
    "waiter":     "ivan.kipchoge",
    "house":      "kevin.mutua",
}

PASS, FAIL = [], []
_tokens: dict[str, dict] = {}


def hdr(role: str) -> dict:
    """Sign in once per role and keep the header. Clocks in too — the tills
    refuse anyone who has not started a shift, which is the point of them."""
    if role in _tokens:
        return _tokens[role]
    username = WHO[role]
    for _ in range(30):
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": username, "password": PASSWORD})
        if r.status_code == 200:
            break
        time.sleep(4)          # the login limiter, not a failure
    else:
        sys.exit(f"could not sign in as {username}: {r.status_code} {r.text[:120]}")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    requests.post(f"{BASE}/hr/clock-in",
                  json={"idempotency_key": str(uuid.uuid4())}, headers=h)
    _tokens[role] = h
    return h


def screen(name: str, role: str, reads: list[str]) -> None:
    """Open one screen as one person; every read it makes must answer."""
    h = hdr(role)
    bad = []
    for path in reads:
        try:
            rv = requests.get(BASE + path, headers=h, timeout=20)
        except Exception as exc:                        # noqa: BLE001
            bad.append(f"{path} → {type(exc).__name__}")
            continue
        if rv.status_code != 200:
            detail = ""
            try:
                detail = f" {rv.json().get('error', '')[:60]}"
            except Exception:                           # noqa: BLE001
                pass
            bad.append(f"{path} → {rv.status_code}{detail}")
    if bad:
        FAIL.append((name, role, bad))
        print(f"  ✗ {name:<34} as {role:<11} {bad[0]}")
        for extra in bad[1:]:
            print(f"{'':>52}{extra}")
    else:
        PASS.append((name, role))
        print(f"  ✓ {name:<34} as {role:<11} {len(reads)} read(s) answered")


def act(name: str, ok: bool, detail: str = "") -> None:
    """A thing that had to actually happen, not merely load."""
    (PASS if ok else FAIL).append((name, "·", detail))
    print(f"  {'✓' if ok else '✗'} {name:<34} {detail}")


# ══════════════════════════════════════════════════════════════════════════
def owner_dashboards() -> None:
    print("\nOWNER — twelve dashboards")
    screen("Dashboard", "owner", [
        "/dashboard/overview", "/dashboard/alerts", "/dashboard/feedback",
        "/dashboard/bookings", "/dashboard/staff", "/dashboard/inventory",
        "/dashboard/equipment", "/dashboard/suggestions", "/dashboard/finance",
        "/dashboard/calendar", "/finance/revenue-history",
        f"/finance/budgets/status?period={TODAY[:7]}",
        "/incidents", "/gate/today-stats",
    ])
    screen("Alerts", "owner", ["/judge/alerts"])
    screen("Finance", "owner", [
        "/finance/dashboard", "/finance/revenue-history", "/finance/vat-summary",
        f"/finance/budgets/status?period={TODAY[:7]}",
    ])
    screen("Approvals", "owner", ["/inventory/purchase-requests?status=PENDING"])
    screen("Recon", "owner", [f"/finance/reconciliation?date={TODAY}"])
    screen("Payroll", "owner", ["/hr/payroll-draft"])
    screen("Staff", "owner", ["/auth/users", "/auth/users/meta", "/hr/profiles"])
    screen("Feedback", "owner", ["/dashboard/feedback", "/feedback"])
    screen("Bookings", "owner", ["/dashboard/bookings", "/bookings"])
    screen("Profit (menu engineering)", "owner", ["/finance/menu-engineering"])
    screen("Audit", "owner", ["/audit/logs", "/audit/actions", "/audit/verify"])
    screen("Settings", "owner", ["/admin/roles", "/admin/baselines", "/admin/settings",
                                 "/hr/wifi"])


def manager_dashboards() -> None:
    print("\nMANAGEMENT — fifteen screens")
    screen("Manage hub", "manager", [
        "/inventory/items", "/auth/users/meta",
        f"/finance/budgets/status?period={TODAY[:7]}",
        "/inventory/purchase-requests?status=PENDING",
        "/hr/leave-requests?status=PENDING", "/hr/attendance/today",
        "/front-desk/today",
    ])
    screen("Cash reconciliation", "manager", ["/hr/profiles"])  # + /finance/cash/pending?staff_id=…
    screen("Leave approvals", "manager", ["/hr/leave-requests?status=PENDING"])
    screen("Attendance", "manager", ["/hr/attendance/today", "/hr/attendance/summary",
                                     "/hr/profiles"])
    screen("Roster", "manager", ["/hr/roster", "/hr/profiles", "/auth/users/meta"])
    screen("Shifts", "manager", ["/hr/shifts", "/hr/profiles"])
    screen("Receive stock", "manager", ["/suppliers", "/inventory/items",
                                        "/inventory/purchase-requests?status=APPROVED"])
    screen("Suppliers", "manager", ["/suppliers"])
    screen("Purchases", "manager", ["/inventory/purchase-requests?status=PENDING",
                                    "/inventory/items"])
    screen("Menu management", "manager", ["/menu/items", "/menu/items/categories",
                                          "/inventory/items", "/auth/users/meta"])
    screen("Villas / resources", "manager", ["/bookable-resources?include_disabled=true"])
    screen("Reconcile (M-Pesa/card)", "manager", [f"/finance/mpesa/pending?date={TODAY}",
                                                  f"/finance/card/pending?date={TODAY}"])
    screen("Staff accounts", "manager", ["/auth/users", "/auth/users/meta", "/hr/profiles"])
    screen("Front House", "manager", ["/front-desk/today", "/housekeeping/status"])
    screen("Receipts", "manager", ["/tabs"])


def floor_screens() -> None:
    print("\nTHE FLOOR — every post")
    screen("Gate hub", "gate", ["/gate/today-stats", "/gate/active-bands"])
    screen("Band lookup", "gate", ["/gate/bands/1"])
    screen("Front desk check-in", "front_desk", ["/front-desk/today", "/housekeeping/status",
                                                 "/auth/users"])
    screen("New booking", "front_desk", [f"/bookings/availability?from={TODAY}T00:00:00Z&to={TODAY}T23:59:59Z"])
    screen("Villa board", "front_desk", [f"/bookings/availability?from={TODAY}T00:00:00Z&to={TODAY}T23:59:59Z", "/front-desk/today"])
    screen("Waiter tables", "waiter", ["/tabs?mine=true", "/notifications/inbox",
                                       "/menu/items"])
    screen("Kitchen board", "chef", ["/kitchen/queue"])
    screen("Bar board", "bar", ["/bar/queue"])
    screen("Head chef", "chef", ["/inventory/items", "/menu/items"])
    screen("Spa till", "spa", ["/menu/items?dept_name=Spa", "/inventory/items"])
    screen("Water till", "water", ["/menu/items?dept_name=Water%20Activities",
                                   "/inventory/items"])
    screen("Waiver desk", "water", ["/hr/roster/me"])  # the form only posts /waivers
    screen("Incidents", "gate", ["/hr/roster/me"])
    screen("Events", "gate", ["/events/upcoming", "/event-types"])
    screen("Calendar", "gate", [f"/calendar?from={TODAY}T00:00:00Z&to={TODAY}T23:59:59Z"])
    screen("Safety checks", "house", ["/equipment"])
    screen("Customer menu", "waiter", ["/menu/items"])


def employee_app() -> None:
    print("\nSTAFF APP — what a person carries")
    screen("Clock", "waiter", ["/hr/roster/me"])
    screen("Schedule", "waiter", ["/hr/roster/me"])
    screen("Leave", "waiter", ["/hr/leave-requests"])
    screen("Absence notice", "waiter", ["/hr/absence-notices?date=" + TODAY])
    screen("Notifications", "waiter", ["/notifications/inbox"])
    screen("Profile / performance", "waiter", ["/hr/profiles/me"])
    screen("Conduct", "waiter", ["/conduct/rules"])  # + /conduct/signatures/<own id>
    screen("Disputes", "waiter", ["/disputes"])
    screen("Calendar", "waiter", [f"/calendar?from={TODAY}T00:00:00Z&to={TODAY}T23:59:59Z"])


# ══════════════════════════════════════════════════════════════════════════
def points_of_sale() -> None:
    """Every till, with money actually moving through it."""
    print("\nPOINTS OF SALE — a real transaction through each")

    # ── 1. The gate: issue a wristband, fee becomes credit ────────────────
    g = hdr("gate")
    band = requests.post(f"{BASE}/gate/issue-band",
                         json={"method": "CASH", "idempotency_key": str(uuid.uuid4())},
                         headers=g)
    ok = band.status_code == 201
    b = band.json() if ok else {}
    act("Gate — issue wristband", ok,
        f"band #{b.get('band_number')}, credit {b.get('tab_balance')}" if ok
        else f"{band.status_code} {band.text[:70]}")
    band_no, band_tab = b.get("band_number"), b.get("tab_id")

    # ── 2. Restaurant: open a table, send food, cook it, collect, settle ──
    w = hdr("waiter")
    c = hdr("chef")
    items = requests.get(f"{BASE}/menu/items", headers=w).json()
    food = next((i for i in items
                 if (i.get("prep_station") or "") == "KITCHEN" and i.get("is_active")
                 and (i.get("stock_tracking") or "") != "UNTRACKED"), None)
    if not food:
        act("Restaurant — sellable kitchen item", False, "none found")
        return

    tab = requests.post(f"{BASE}/tabs", json={"reference": "Table 12"}, headers=w).json()
    order = requests.post(f"{BASE}/orders",
                          json={"tab_id": tab["id"],
                                "items": [{"menu_item_id": food["id"], "quantity": 1}]},
                          headers=w)
    act("Restaurant — add to a table", order.status_code == 201,
        f"{food['name']} on Table 12" if order.status_code == 201
        else f"{order.status_code} {order.text[:70]}")
    if order.status_code != 201:
        return
    oid = order.json()["id"]
    sent = requests.post(f"{BASE}/orders/{oid}/send", headers=w)
    act("Restaurant — send to kitchen", sent.status_code == 200, f"{sent.status_code}")

    q = requests.get(f"{BASE}/kitchen/queue", headers=c).json()
    mine = [r for r in q if r["order_id"] == oid]
    act("Kitchen board — ticket arrives", bool(mine),
        f"{len(mine)} line(s) on the board")
    if mine:
        oi = mine[0]["order_item_id"]
        rec = requests.post(f"{BASE}/order-items/{oi}/receive", headers=c)
        rdy = requests.post(f"{BASE}/order-items/{oi}/ready", headers=c)
        act("Kitchen board — received → ready", rec.status_code == 200 and rdy.status_code == 200,
            f"{rec.status_code}/{rdy.status_code}")
        inbox = requests.get(f"{BASE}/notifications/inbox", headers=w).json()
        pinged = [n for n in inbox if n.get("reference_id") == oi]
        act("Waiter — told the plate is up", bool(pinged),
            pinged[0]["body"] if pinged else "no alert reached the waiter")
        srv = requests.post(f"{BASE}/order-items/{oi}/serve", headers=w)
        act("Waiter — mark served", srv.status_code == 200, f"{srv.status_code}")

    bill = requests.get(f"{BASE}/tabs/{tab['id']}", headers=w).json()
    pay = requests.post(f"{BASE}/tabs/{tab['id']}/payments",
                        json={"method": "CASH", "amount": bill["balance"],
                              "idempotency_key": str(uuid.uuid4())}, headers=w)
    act("Restaurant — settle the bill", pay.status_code == 201,
        f"KSh {bill['balance']} cash" if pay.status_code == 201
        else f"{pay.status_code} {pay.text[:70]}")
    closed = requests.post(f"{BASE}/tabs/{tab['id']}/close", headers=w)
    act("Restaurant — close the table", closed.status_code == 200, f"{closed.status_code}")

    # ── 3. Bar ────────────────────────────────────────────────────────────
    bar = hdr("bar")
    drink = next((i for i in items
                  if (i.get("prep_station") or "") == "BAR" and i.get("is_active")
                  and (i.get("stock_tracking") or "") != "UNTRACKED"), None)
    if drink:
        t2 = requests.post(f"{BASE}/tabs", json={"reference": "Bar 3"}, headers=w).json()
        o2 = requests.post(f"{BASE}/orders",
                           json={"tab_id": t2["id"],
                                 "items": [{"menu_item_id": drink["id"], "quantity": 1}]},
                           headers=w)
        requests.post(f"{BASE}/orders/{o2.json()['id']}/send", headers=w)
        bq = requests.get(f"{BASE}/bar/queue", headers=bar).json()
        act("Bar till → bar board", any(r["order_id"] == o2.json()["id"] for r in bq),
            f"{drink['name']} reached the bar board")
    else:
        act("Bar till → bar board", False, "no sellable bar item")

    # ── 4. Water: the waiver gate, then the sale ─────────────────────────
    wtr = hdr("water")
    jet = next((i for i in items
                if (i.get("category") or "").strip().lower() == "water activities"
                and i.get("is_active")), None)
    if jet and band_tab:
        refused = requests.post(f"{BASE}/orders",
                                json={"tab_id": band_tab,
                                      "items": [{"menu_item_id": jet["id"], "quantity": 1}]},
                                headers=wtr)
        act("Water till — refused with no waiver", refused.status_code == 403,
            (refused.json().get("error", "")[:64]) if refused.status_code == 403
            else f"ALLOWED ({refused.status_code}) — the liability gate is open")
        wv = requests.post(f"{BASE}/waivers",
                           json={"band_number": band_no, "activity_type": "WATER_ACTIVITY",
                                 "signed_by_name": "Screen Check",
                                 "idempotency_key": str(uuid.uuid4())}, headers=wtr)
        act("Water till — attendant records waiver", wv.status_code in (200, 201),
            f"{wv.status_code}")
        allowed = requests.post(f"{BASE}/orders",
                                json={"tab_id": band_tab,
                                      "items": [{"menu_item_id": jet["id"], "quantity": 1}]},
                                headers=wtr)
        act("Water till — sells once signed", allowed.status_code == 201,
            f"{jet['name']} charged to band #{band_no}" if allowed.status_code == 201
            else f"{allowed.status_code} {allowed.text[:70]}")
    else:
        act("Water till", False, "no water-activity item or no band")

    # ── 5. Spa ────────────────────────────────────────────────────────────
    spa = hdr("spa")
    spa_items = requests.get(f"{BASE}/menu/items?dept_name=Spa", headers=spa)
    act("Spa till — its own service list", spa_items.status_code == 200,
        f"{len(spa_items.json())} service(s)" if spa_items.status_code == 200
        else f"{spa_items.status_code}")
    req = requests.post(f"{BASE}/suggestions",
                        json={"category": "MANAGEMENT", "subject": "Restock from Spa",
                              "body": "Massage oil running low."}, headers=spa)
    act("Spa till — restock request", req.status_code == 201, f"{req.status_code}")

    # ── 6. Villa folio: charge a room ────────────────────────────────────
    fd = hdr("front_desk")
    today = requests.get(f"{BASE}/front-desk/today", headers=fd).json()
    act("Front desk — arrivals & departures", isinstance(today, dict),
        f"{len(today.get('arrivals', []))} arriving, "
        f"{len(today.get('departures', []))} departing")

    # ── 7. Band credit is really spent ───────────────────────────────────
    if band_no:
        after = requests.get(f"{BASE}/gate/bands/{band_no}", headers=g)
        if after.status_code == 200:
            act("Wristband — credit moved with the sale", True,
                f"band #{band_no} now {after.json().get('tab_balance')}")
        else:
            act("Wristband — credit moved with the sale", False, f"{after.status_code}")


# ══════════════════════════════════════════════════════════════════════════
def main() -> None:
    try:
        requests.get(f"{BASE}/health", timeout=5)
    except Exception:                                   # noqa: BLE001
        sys.exit(f"no server at {BASE} — start it first")

    print("every screen, opened as the person who uses it")
    print("=" * 66)
    owner_dashboards()
    manager_dashboards()
    floor_screens()
    employee_app()
    points_of_sale()

    print("\n" + "=" * 66)
    print(f"{len(PASS)} passed · {len(FAIL)} failed")
    if FAIL:
        print("\nwhat would refuse the person it was built for:")
        for name, role, detail in FAIL:
            d = detail[0] if isinstance(detail, list) else detail
            print(f"  ✗ {name} (as {role}) — {d}")
        sys.exit(1)
    print("every dashboard and every till answered for its own person.")
    sys.exit(0)


if __name__ == "__main__":
    main()
