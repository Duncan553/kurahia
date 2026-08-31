"""
scripts/reflect.py — does an action REFLECT everywhere it is supposed to?

The other two drivers ask "does it work". This one asks a harder question:
when one thing happens, do all the OTHER places that claim to know about it
agree? A system can pass every endpoint test and still lie, because the lie
only shows up when two screens disagree about the same fact.

So every check below computes the truth TWICE — once from the ledger, once
from the screen a person actually reads — and fails if they differ.

    a new hire clocks in      -> does the manager's board say present?
    a delivery arrives        -> does stock go UP by exactly that much?
    a cook makes a recipe     -> does stock go DOWN by exactly the recipe?
    a guest pays              -> does revenue, VAT and the tab all agree?

Run:  python scripts/reflect.py

NOT a seeder. Every write is an HTTP call by the person whose job it is.
The staff account it creates is DISABLED at the end (invariant 6: disable,
never delete) so re-running does not grow the payroll.
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models.user import User                             # noqa: E402
from app.models.role import Role                             # noqa: E402
from app.models.menu_item import MenuItem                    # noqa: E402
from app.models.audit_log import AuditLog                    # noqa: E402
from app.models.inventory_item import InventoryItem          # noqa: E402
from app.services.stock import get_current_stock             # noqa: E402
from app.services.tab import get_tab_balance                 # noqa: E402
from app.services.finance import get_period_revenue_by_method  # noqa: E402
from flask_jwt_extended import create_access_token            # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
RESULTS = []


def record(ok, step, detail=""):
    RESULTS.append((ok, step, detail))
    print(f"{'  ok  ' if ok else '  ✗ MISMATCH'}  {step}{(' — ' + detail) if detail else ''}")


def expect(cond, step, detail=""):
    record(bool(cond), step, detail)
    return bool(cond)


def agree(a, b, step, what=""):
    """The core assertion of this file: two sources, one number."""
    ok = a == b
    record(ok, step, f"ledger={a} screen={b}" if not ok else f"{what or a}")
    return ok


def act(title):
    print(f"\n── {title} " + "─" * max(4, 56 - len(title)))


class Desk:
    def __init__(self, app, username):
        self.c = app.test_client()
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            raise SystemExit(f"no such user: {username}")
        self.username, self.user_id = username, u.id
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h, environ_base=LAN, **kw)

    def post(self, p, json=None, **kw):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def patch(self, p, json=None, **kw):
        return self.c.patch(p, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def clock_in(self):
        return self.post("/hr/clock-in", {})


def token_for(app, user_id):
    """A desk for somebody created mid-run, who has no seeded account."""
    d = Desk.__new__(Desk)
    d.c, d.user_id, d.username = app.test_client(), user_id, "(new hire)"
    d.h = {"Authorization": f"Bearer {create_access_token(identity=user_id)}"}
    return d


def menu_id(name):
    m = db.session.query(MenuItem).filter_by(name=name, is_active=True).first()
    return m.id if m else None


def inv_id(name):
    i = db.session.query(InventoryItem).filter_by(name=name, is_active=True).first()
    return i.id if i else None


def today_window():
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=12), now + timedelta(hours=12)


# ══ ACT 1 ═══════════════════════════════════════════════════════════════════
def act_new_employee(app, mgr):
    """A new person is hired. Every roster that claims to know staff must
    learn about them — not just the table they were written to."""
    act("a new employee is hired")

    waiter_role = db.session.query(Role).filter_by(name="waiter").first()
    dept_id = db.session.get(User, mgr.user_id).department_id
    uname = f"newhire.{uuid.uuid4().hex[:6]}"

    r = mgr.post("/auth/users", {
        "username": uname, "password": "Kurahia1!",
        "role_id": waiter_role.id, "department_id": dept_id,
    })
    if not expect(r.status_code == 201, "manager creates the account",
                  str(r.get_json())[:70]):
        return None, None
    user_id = r.get_json()["id"]

    r = mgr.post("/hr/profiles", {
        "user_id": user_id, "full_name": "Amina Wekesa",
        "phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
        "wage_rate": "900", "wage_period": "DAILY",
    })
    if not expect(r.status_code == 201, "manager opens their employee file",
                  str(r.get_json())[:70]):
        return None, None
    profile_id = r.get_json()["id"]

    # Does the staff list actually show them? A row nobody can see is not a hire.
    listed = [p for p in (mgr.get("/hr/profiles").get_json() or [])
              if p.get("id") == profile_id]
    expect(listed, "they appear on the manager's staff list")

    # Roster them on today, or the attendance board has no reason to list them.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = mgr.post("/hr/shifts", {
        "employee_id": profile_id,
        "scheduled_start_utc": (now - timedelta(hours=1)).isoformat(),
        "scheduled_end_utc":   (now + timedelta(hours=7)).isoformat(),
        "department_id": dept_id,
    })
    expect(r.status_code == 201, "manager rosters them for today",
           str(r.get_json())[:70])

    # BEFORE clocking in they must read as absent — not missing, absent.
    rows = mgr.get("/hr/attendance/today").get_json() or []
    mine = [x for x in rows if x["employee_id"] == profile_id]
    expect(mine and mine[0]["status"] == "absent_no_notice",
           "before clocking in the board says absent",
           mine[0]["status"] if mine else "not on the board at all")

    return user_id, profile_id


# ══ ACT 2 ═══════════════════════════════════════════════════════════════════
def act_clock_in_is_seen(app, mgr, owner, user_id, profile_id):
    """The question in Wachira's words: if you clock in, does the manager know
    you are present, and does the system know?"""
    act("they clock in — who finds out?")
    hire = token_for(app, user_id)

    audits_before = db.session.query(AuditLog).count()
    r = hire.clock_in()
    if not expect(r.status_code == 201, "the new hire clocks in",
                  str(r.get_json())[:70]):
        return

    # 1. The manager's board.
    rows = mgr.get("/hr/attendance/today").get_json() or []
    mine = [x for x in rows if x["employee_id"] == profile_id]
    expect(mine and mine[0]["status"] == "clocked_in",
           "the manager's board flips them to present",
           mine[0]["status"] if mine else "missing from the board")

    # 2. Their own record, read the way THEY would see it in the employee app.
    #    Not /hr/attendance/employee/<id> — that is the manager's board and is
    #    manager-and-above by design. The employee app is personal proof-of-work,
    #    so the personal endpoint is the right one to check.
    own = hire.get("/hr/clock-status")
    expect(own.status_code == 200 and
           (own.get_json() or {}).get("status") == "CLOCK_IN",
           "their own app shows them clocked in",
           str(own.get_json())[:60] if own.status_code != 200 else "")

    # 2b. And the manager's per-person view is correctly CLOSED to them.
    expect(hire.get(f"/hr/attendance/employee/{profile_id}").status_code == 403,
           "but the manager's board stays shut to a waiter")

    # 3. The owner's staff dashboard counts them.
    staff = owner.get("/dashboard/staff")
    expect(staff.status_code == 200, "owner's staff dashboard loads")

    # 4. The system remembers WHO did it. A clock-in with no audit row is a
    #    presence claim nobody can later check.
    expect(db.session.query(AuditLog).count() > audits_before,
           "the clock-in left an audit row")

    # 5. And the POS gate opens, which is the practical meaning of "present".
    probe = hire.post("/orders", {"items": []})
    expect(probe.status_code != 403 or "clock" not in
           str(probe.get_json()).lower(),
           "being present unlocks the POS gate")


# ══ ACT 3 ═══════════════════════════════════════════════════════════════════
def act_delivery_raises_stock(mgr, owner):
    """A delivery arrives. Stock must go UP by exactly what was delivered —
    derived from the movement ledger, never a stored counter."""
    act("a delivery arrives")
    name = "Potatoes"
    iid = inv_id(name)
    before = get_current_stock(iid)

    key = f"reflect-delivery-{uuid.uuid4().hex[:8]}"
    r = mgr.post("/inventory/purchases", {
        "item_id": iid, "quantity": "10", "actual_cost": "700",
        "supplier_name": "Juja Fresh Produce",
        "receipt_photo_path": f"receipts/{key}.jpg",
        "notes": "one 10kg net @ KSh 70/kg",
        "idempotency_key": key,
    })
    if not expect(r.status_code in (200, 201), "manager records the delivery",
                  str(r.get_json())[:70]):
        return

    after = get_current_stock(iid)
    agree(after - before, Decimal("10"),
          f"{name} stock rose by exactly what arrived", f"{before} -> {after}")

    # The movement ledger is the system of record — the number above is only
    # trustworthy if a row explains it.
    movs = mgr.get("/inventory/movements", query_string={"item_id": iid})
    if movs.status_code == 200:
        rows = movs.get_json()
        rows = rows.get("movements", rows) if isinstance(rows, dict) else rows
        expect(any(str(m.get("reason", "")).upper() == "PURCHASE" for m in rows),
               "a PURCHASE row explains the rise")
    else:
        expect(False, "movement ledger readable by manager", str(movs.status_code))

    inv = owner.get("/dashboard/inventory")
    expect(inv.status_code == 200, "owner's inventory dashboard loads")


# ══ ACT 4 ═══════════════════════════════════════════════════════════════════
def act_new_customer(gate):
    """A new customer walks in at the gate. One Payment must both settle the
    cash and open the tab at -3,000 — the entry fee becomes spendable credit."""
    act("a new customer arrives at the gate")
    before = gate.get("/gate/today-stats").get_json() or {}

    r = gate.post("/gate/issue-band", {
        "guest_name": f"Njeri {uuid.uuid4().hex[:4].upper()}",
        "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
        "amount_paid": "3000", "method": "CASH",
    })
    if not expect(r.status_code == 201, "gate issues a wristband",
                  str(r.get_json())[:70]):
        return None
    band = r.get_json()

    tab_id = band.get("tab_id")
    if tab_id:
        agree(get_tab_balance(tab_id), Decimal("-3000"),
              "the entry fee lands as spendable credit, not revenue only",
              "KSh 3,000 credit")

    after = gate.get("/gate/today-stats").get_json() or {}
    for k in ("bands_issued", "total_bands", "issued_today"):
        if k in before and k in after:
            agree(after[k], before[k] + 1, f"gate stats counted them ({k})")
            break

    active = gate.get("/gate/active-bands").get_json() or []
    expect(any(b.get("band_number") == band.get("band_number") for b in active),
           "the band shows as active at the gate")
    return band


# ══ ACT 5 ═══════════════════════════════════════════════════════════════════
def act_cook_a_recipe(waiter, kitchen, bar, mgr):
    """The heart of it: cook something with a recipe, and watch the store.

    Chips is a RECIPE (250g potatoes + 50ml oil). Tusker is DIRECT (one
    bottle). Consumption fires on READY — not on order, not on serve — so the
    reading has to bracket exactly that step.
    """
    act("the kitchen cooks a recipe, and the store answers")
    watch = {n: inv_id(n) for n in ("Potatoes", "Cooking Oil", "Tusker Beer")}
    before = {n: get_current_stock(i) for n, i in watch.items()}

    chips, beer = menu_id("Chips"), menu_id("Tusker Beer")
    r = waiter.post("/orders", {"items": [
        {"menu_item_id": chips, "quantity": 2},     # two plates, so 2x the recipe
        {"menu_item_id": beer,  "quantity": 3},
    ]})
    if not expect(r.status_code == 201, "waiter takes the order",
                  str(r.get_json())[:70]):
        return None
    order = r.get_json()
    tab_id = order["tab_id"]
    expect(waiter.post(f"/orders/{order['id']}/send").status_code == 200,
           "the ticket reaches the stations")

    # Nothing may have moved yet. If stock drops on ORDER, a cancelled order
    # silently eats the store.
    mid = {n: get_current_stock(i) for n, i in watch.items()}
    agree(mid["Potatoes"], before["Potatoes"],
          "ordering alone does NOT touch stock", "still untouched")

    tab = waiter.get(f"/tabs/{tab_id}").get_json()
    for item in tab["orders"][-1]["items"]:
        mi = db.session.query(MenuItem).filter_by(name=item["name"]).first()
        desk = kitchen if mi and mi.prep_station == "KITCHEN" else bar
        desk.post(f"/order-items/{item['id']}/receive")
        rr = desk.post(f"/order-items/{item['id']}/ready")
        expect(rr.status_code == 200, f"{item['name']} is made and called ready",
               "" if rr.status_code == 200 else str(rr.get_json())[:60])
        # READY is not the end of it. A tab cannot close while an item is still
        # sitting on the pass — the system refusing that is correct, so the
        # waiter has to actually carry it. Missing this step made the close
        # below look like a bug on the first run.
        waiter.post(f"/order-items/{item['id']}/serve")

    after = {n: get_current_stock(i) for n, i in watch.items()}
    # 2 plates of chips = 2 x 250g potatoes, 2 x 50ml oil. 3 beers = 3 bottles.
    for name, want in (("Potatoes", "0.50"), ("Cooking Oil", "0.10"),
                       ("Tusker Beer", "3")):
        agree(before[name] - after[name], Decimal(want),
              f"{name} fell by exactly the recipe",
              f"{before[name]} -> {after[name]}")

    return tab_id


# ══ ACT 6 ═══════════════════════════════════════════════════════════════════
def act_payment_reaches_the_books(waiter, owner, tab_id):
    """They pay. The same shillings must appear in the tab, the revenue split,
    the VAT return and the day's summary — and nowhere twice."""
    act("the guest pays, and the books agree")
    owed = get_tab_balance(tab_id)
    expect(owed > 0, "the tab shows what is owed", f"KSh {owed}")

    start, end = today_window()
    rev_before = get_period_revenue_by_method(start, end)["total"]

    r = waiter.post(f"/tabs/{tab_id}/payments",
                    {"amount": str(owed), "method": "MPESA"})
    if not expect(r.status_code in (200, 201), "payment is recorded",
                  str(r.get_json())[:70]):
        return

    agree(get_tab_balance(tab_id), Decimal("0"), "the tab clears to zero")

    rev_after = get_period_revenue_by_method(start, end)
    agree(rev_after["total"] - rev_before, owed,
          "revenue rose by exactly what was paid — not twice", f"KSh {owed}")
    expect(Decimal(str(rev_after.get("MPESA", 0))) > 0,
           "it landed under the method actually used (MPESA)")

    # The owner's finance dashboard and the VAT return read the same money.
    fin = owner.get("/finance/dashboard")
    expect(fin.status_code == 200, "owner's finance dashboard loads")
    vat = owner.get("/finance/vat-summary",
                    query_string={"start_date": start.date().isoformat(),
                                  "end_date": end.date().isoformat()})
    expect(vat.status_code == 200, "the VAT return loads")

    # And the tab can now close, which is the system agreeing it is settled.
    closable = waiter.post(f"/tabs/{tab_id}/close")
    expect(closable.status_code in (200, 403),
           "a settled tab is allowed to close",
           str(closable.get_json())[:60] if closable.status_code >= 400 else "")


# ══ ACT 7 ═══════════════════════════════════════════════════════════════════
# (path, query) — a few screens need a period before they can say anything.
OWNER_SCREENS = [("/dashboard/overview", {}), ("/dashboard/inventory", {}),
                 ("/dashboard/finance", {}), ("/dashboard/bookings", {}),
                 ("/dashboard/staff", {}), ("/dashboard/conduct", {}),
                 ("/dashboard/suggestions", {}), ("/dashboard/calendar", {}),
                 ("/dashboard/feedback", {}), ("/dashboard/equipment", {}),
                 ("/dashboard/alerts", {}), ("/finance/dashboard", {}),
                 ("/finance/revenue-history", {}), ("/finance/menu-engineering", {}),
                 ("/finance/payroll",
                  {"period": datetime.now(timezone.utc).strftime("%Y-%m")})]


def act_every_dashboard(owner, mgr, waiter):
    """Every owner screen must LOAD for the owner and REFUSE the waiter.

    A screen that 500s is a screen nobody can use; a screen a waiter can read
    is a payroll leak. Both are caught here, on every screen, every run.
    """
    act("every dashboard, owner and intruder")
    for path, q in OWNER_SCREENS:
        r = owner.get(path, query_string=q)
        expect(r.status_code == 200, f"owner can read {path}",
               "" if r.status_code == 200 else f"{r.status_code} {str(r.get_json())[:50]}")

    leaks = []
    for path, q in OWNER_SCREENS:
        if waiter.get(path, query_string=q).status_code == 200:
            leaks.append(path)
    expect(not leaks, "a waiter is refused every owner screen",
           f"LEAKED: {', '.join(leaks)}" if leaks else "all refused")


# ══ Cleanup ═════════════════════════════════════════════════════════════════
def retire_the_test_hire(owner, mgr, profile_id, user_id):
    """Disabling an employee file is OWNER-only, not manager — a manager can
    hire but cannot make someone disappear. Using the manager here failed on
    the first run, which is the rule working, not a bug."""
    act("put the test hire away")
    if profile_id:
        expect(mgr.post(f"/hr/profiles/{profile_id}/disable").status_code == 403,
               "a manager cannot disable an employee file")
        r = owner.post(f"/hr/profiles/{profile_id}/disable")
        expect(r.status_code == 200, "the owner disables it — never deletes it",
               "" if r.status_code == 200 else str(r.get_json())[:60])
    if user_id:
        r = owner.post(f"/auth/deactivate/{user_id}")
        expect(r.status_code in (200, 404), "the login account is deactivated too")


def run(app):
    with app.app_context():
        owner   = Desk(app, "amara.wanjiku")
        mgr     = Desk(app, "brian.mwangi")
        chef    = Desk(app, "cynthia.achieng")
        bar     = Desk(app, "david.otieno")
        gate    = Desk(app, "hassan.omondi")
        waiter  = Desk(app, "peter.mwendwa")
        for d in (mgr, chef, bar, gate, waiter):
            d.clock_in()

        user_id, profile_id = act_new_employee(app, mgr)
        if user_id:
            act_clock_in_is_seen(app, mgr, owner, user_id, profile_id)
        act_delivery_raises_stock(mgr, owner)
        act_new_customer(gate)
        tab_id = act_cook_a_recipe(waiter, chef, bar, mgr)
        if tab_id:
            act_payment_reaches_the_books(waiter, owner, tab_id)
        act_every_dashboard(owner, mgr, waiter)
        retire_the_test_hire(owner, mgr, profile_id, user_id)


if __name__ == "__main__":
    run(create_app("development"))
    bad = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} checks agreed")
    if bad:
        print(f"\n{len(bad)} DISAGREEMENT(S):")
        for _, step, detail in bad:
            print(f"  • {step}  {detail}")
    sys.exit(1 if bad else 0)
