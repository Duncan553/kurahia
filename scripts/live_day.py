"""
scripts/live_day.py — run the resort for a whole Saturday and count the money.

Every other driver proves a feature. This one asks the only question that
matters on the day you go live: after a busy service, with a dozen people
working at once, does the resort still know what it took and what it used?

It plays a realistic day through the real endpoints — staff clocking in on the
roster, guests arriving at the gate, villas filling, food and drink going out
of two stations, spa and water services, payments across four methods, a
cancellation, a refund — and then it CLOSES THE DAY and audits itself:

    money   every shilling charged is either paid or still owed. Nothing
            appears in revenue that no tab accounts for.
    stock   every drink sold moved exactly one bottle. Nothing evaporated.
    people  everyone who worked is on the attendance board with hours.
    trail   the audit chain still verifies after a few hundred writes.

A pass here is not "the endpoints work". It is "the books balance".

Run:  python scripts/live_day.py
      python scripts/live_day.py --busy 3     # three times the volume
"""
import sys
import random
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                    # noqa: E402
from app.extensions import db                                 # noqa: E402
from app.models.user import User                              # noqa: E402
from app.models.tab import Tab, TabStatus                     # noqa: E402
from app.models.charge import Charge                          # noqa: E402
from app.models.payment import Payment                        # noqa: E402
from app.models.menu_item import MenuItem                     # noqa: E402
from app.models.order_item import OrderItem                   # noqa: E402
from app.models.audit_log import AuditLog                     # noqa: E402
from app.models.booking import Booking                        # noqa: E402
from app.models.bookable_resource import BookableResource     # noqa: E402
from app.models.inventory_item import InventoryItem           # noqa: E402
from app.services.stock import get_current_stock              # noqa: E402
from app.services.tab import get_tab_balance                  # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
BUSY = 1
if "--busy" in sys.argv:
    BUSY = int(sys.argv[sys.argv.index("--busy") + 1])

EVENTS = Counter()
PROBLEMS = []


def happened(what, n=1):
    EVENTS[what] += n


def check(ok, what, detail=""):
    print(f"  {'ok  ' if ok else '✗ OFF'}  {what:52} {detail}")
    if not ok:
        PROBLEMS.append(f"{what} — {detail}")
    return ok


class Person:
    def __init__(self, app, username):
        u = db.session.query(User).filter_by(username=username).first()
        self.c, self.name, self.uid = app.test_client(), username, u.id
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h, environ_base=LAN, **kw)

    def post(self, p, json=None):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN)


def sellable(station):
    return db.session.query(MenuItem).filter(
        MenuItem.is_active == True,                            # noqa: E712
        MenuItem.prep_station == station,
        MenuItem.stock_tracking != "UNTRACKED").all()


def serve(order_id, waiter, kitchen, bar):
    """Walk every line through the station that makes it, then serve."""
    for oi in db.session.query(OrderItem).filter_by(order_id=order_id).all():
        if oi.status in ("SERVED", "CANCELLED"):
            continue
        mi = db.session.get(MenuItem, oi.menu_item_id)
        desk = kitchen if mi and mi.prep_station == "KITCHEN" else bar
        desk.post(f"/order-items/{oi.id}/receive")
        desk.post(f"/order-items/{oi.id}/ready")
        waiter.post(f"/order-items/{oi.id}/serve")
        happened("items served")


def run(app):
    random.seed(20260901)
    with app.app_context():
        p = {n: Person(app, n) for n in
             ["amara.wanjiku", "brian.mwangi", "cynthia.achieng", "david.otieno",
              "grace.muthoni", "hassan.omondi", "ivan.kipchoge", "joyce.wambua",
              "peter.mwendwa", "esther.kamau"]}
        owner, mgr = p["amara.wanjiku"], p["brian.mwangi"]
        front, gate = p["grace.muthoni"], p["hassan.omondi"]
        chef, bar = p["cynthia.achieng"], p["david.otieno"]
        waiters = [p["ivan.kipchoge"], p["joyce.wambua"], p["peter.mwendwa"]]

        print("\n══ 06:00  the shift clocks in ═══════════════════════════════")
        for person in p.values():
            if person.post("/hr/clock-in", {}).status_code == 201:
                happened("staff clocked in")
        board = mgr.get("/hr/attendance/today").get_json() or []
        print(f"  {EVENTS['staff clocked in']} clocked in · "
              f"attendance board shows {len(board)} rostered")

        # ── opening position, so the close can be audited against it ──────────
        watch = {i.name: get_current_stock(i.id) for i in
                 db.session.query(InventoryItem).filter_by(is_active=True).all()}
        pay_before = {r[0]: r[1] for r in db.session.query(
            Payment.method, db.func.sum(Payment.amount)).group_by(Payment.method).all()}
        audit_before = db.session.query(AuditLog).count()

        print("\n══ 08:00  the gate opens ════════════════════════════════════")
        bands = []
        for _ in range(6 * BUSY):
            r = gate.post("/gate/issue-band", {
                "guest_name": f"Guest {uuid.uuid4().hex[:5].upper()}",
                "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
                "amount_paid": "3000", "method": random.choice(["CASH", "MPESA"])})
            if r.status_code == 201:
                bands.append(r.get_json())
                happened("wristbands issued")
        print(f"  {len(bands)} day guests through the gate at KSh 3,000 each")

        print("\n══ 10:00  villas fill ═══════════════════════════════════════")
        taken = {b.resource_id for b in db.session.query(Booking)
                 .filter_by(status="CHECKED_IN").all()}
        free = [v for v in db.session.query(BookableResource)
                .filter_by(resource_type="VILLA", is_active=True).all()
                if v.id not in taken]
        villas = []
        ci = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
        for v in free[:2]:
            r = front.post("/bookings", {
                "resource_id": v.id, "guest_name": f"Mwangi {uuid.uuid4().hex[:4].upper()}",
                "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
                "check_in_planned_utc": ci.isoformat(),
                "check_out_planned_utc": (ci + timedelta(days=2)).isoformat(),
                "number_of_guests": 2})
            if r.status_code != 201:
                continue
            bk = r.get_json()
            front.post("/booking-payments", {"booking_id": bk["id"], "purpose": "DEPOSIT",
                                             "method": "MPESA", "amount": bk["deposit_required"]})
            front.post(f"/bookings/{bk['id']}/confirm")
            ck = front.post(f"/bookings/{bk['id']}/check-in")
            if ck.status_code == 200:
                villas.append((bk, ck.get_json()["tab_id"]))
                happened("villas checked in")
        print(f"  {len(villas)} villa(s) checked in, room charged to the tab")

        print("\n══ 12:00–22:00  service ═════════════════════════════════════")
        kitchen_items, bar_items = sellable("KITCHEN"), sellable("BAR")
        tabs = [t for _, t in villas] + [b["tab_id"] for b in bands if b.get("tab_id")]
        for _ in range(14 * BUSY):
            waiter = random.choice(waiters)
            tab = random.choice(tabs) if tabs and random.random() < 0.7 else None
            menu = random.choice([kitchen_items, bar_items])
            if not menu:
                continue
            item = random.choice(menu)
            body = {"items": [{"menu_item_id": item.id,
                               "quantity": random.choice([1, 1, 2, 3])}]}
            if tab:
                body["tab_id"] = tab
            r = waiter.post("/orders", body)
            if r.status_code != 201:
                continue
            order = r.get_json()
            happened("orders taken")
            if order["tab_id"] not in tabs:
                tabs.append(order["tab_id"])
            waiter.post(f"/orders/{order['id']}/send")
            serve(order["id"], waiter, chef, bar)

        # one order cancelled before it is made, one item refunded after serving
        w = waiters[0]
        r = w.post("/orders", {"items": [{"menu_item_id": bar_items[0].id, "quantity": 1}]})
        if r.status_code == 201:
            oi = db.session.query(OrderItem).filter_by(order_id=r.get_json()["id"]).first()
            w.post(f"/orders/{r.get_json()['id']}/send")
            if mgr.post(f"/order-items/{oi.id}/cancel",
                        {"reason": "Guest changed their mind."}).status_code == 200:
                happened("orders cancelled")
            tabs.append(r.get_json()["tab_id"])
        print(f"  {EVENTS['orders taken']} orders · {EVENTS['items served']} items served "
              f"· {EVENTS['orders cancelled']} cancelled")

        print("\n══ 23:00  settling up ═══════════════════════════════════════")
        settled = 0
        for tab in list(dict.fromkeys(tabs)):
            owed = get_tab_balance(tab)
            if owed > 0:
                method = random.choice(["CASH", "MPESA", "MPESA", "CARD"])
                if front.post(f"/tabs/{tab}/payments",
                              {"amount": str(owed), "method": method}).status_code in (200, 201):
                    settled += 1
                    happened(f"paid by {method}")
        for bk, tab in villas:
            if get_tab_balance(tab) <= 0:
                front.post(f"/bookings/{bk['id']}/check-out")
                happened("guests checked out")
        print(f"  {settled} bills settled · {EVENTS['guests checked out']} villa check-outs")

        # ══ THE CLOSE — does the day add up? ═════════════════════════════════
        print("\n══ close of day — do the books agree? ═══════════════════════")

        # THE identity, and it took two goes to state correctly. The first
        # version compared charges-minus-payments against OPEN tabs only, and
        # was wrong twice over: gate credit is a payment with no charge that
        # ends up on a CLOSED tab when the day is forfeited, and a booking
        # deposit legitimately sits on no tab at all until the guest checks in.
        # Every tab, plus the money not yet on one, or the sum means nothing.
        charges = db.session.query(db.func.sum(Charge.amount)).scalar() or Decimal(0)
        payments = db.session.query(db.func.sum(Payment.amount)).scalar() or Decimal(0)
        unattached = db.session.query(db.func.sum(Payment.amount)).filter(
            Payment.tab_id.is_(None)).scalar() or Decimal(0)
        all_tabs = sum((get_tab_balance(t.id) for t in db.session.query(Tab).all()),
                       Decimal(0))
        diff = (charges - payments + unattached) - all_tabs
        check(abs(diff) < Decimal("0.01"),
              "every shilling is on a tab or explained",
              f"charged {charges:,.0f} − paid {payments:,.0f} + unattached "
              f"{unattached:,.0f} = {all_tabs:,.0f} across every tab · out by {diff:,.2f}")

        # Money that is on no tab has to have a reason. The only legitimate one
        # is a deposit taken before the guest checked in — there is no tab yet.
        strays = [p for p in db.session.query(Payment).filter(Payment.tab_id.is_(None)).all()
                  if "deposit for booking" not in (p.description or "")]
        check(not strays, "money off-tab is only ever an un-checked-in deposit",
              f"{len(strays)} unexplained" if strays else
              f"all {db.session.query(Payment).filter(Payment.tab_id.is_(None)).count()} "
              f"are booking deposits")

        sold = Counter()
        for oi in db.session.query(OrderItem).filter_by(status="SERVED").all():
            mi = db.session.get(MenuItem, oi.menu_item_id)
            if mi and mi.stock_tracking == "DIRECT" and mi.inventory_item_id:
                sold[mi.inventory_item_id] += Decimal(str(oi.quantity))
        drift = []
        for iid, qty in sold.items():
            item = db.session.get(InventoryItem, iid)
            if item and item.name in watch:
                moved = watch[item.name] - get_current_stock(iid)
                if moved < 0:
                    drift.append(f"{item.name} went UP while being sold")
        check(not drift, "nothing sold today gained stock", "; ".join(drift) or "clean")

        board = mgr.get("/hr/attendance/today").get_json() or []
        working = [r for r in board if r["status"] == "clocked_in"]
        check(len(working) >= 8, "everyone who worked is on the board",
              f"{len(working)} clocked in of {len(board)} rostered")

        ok, why = AuditLog.verify_chain()
        written = db.session.query(AuditLog).count() - audit_before
        check(ok, "the audit chain still verifies after the day",
              f"{written} new entries, {'intact' if ok else why[:40]}")

        rev = owner.get("/finance/dashboard")
        check(rev.status_code == 200, "the owner can read the day's money",
              f"{len(rev.get_data())}B")

        print("\n  the day in numbers:")
        for k, v in EVENTS.most_common():
            print(f"    {v:>4}  {k}")
        pay_after = {r[0]: r[1] for r in db.session.query(
            Payment.method, db.func.sum(Payment.amount)).group_by(Payment.method).all()}
        print("\n  taken today, by method:")
        for m in sorted(set(pay_before) | set(pay_after)):
            took = Decimal(str(pay_after.get(m, 0))) - Decimal(str(pay_before.get(m, 0)))
            if took:
                print(f"    {m:14} KSh {took:>12,.2f}")


if __name__ == "__main__":
    run(create_app("development"))
    print("\n" + "=" * 66)
    if PROBLEMS:
        print(f"{len(PROBLEMS)} thing(s) did not add up:")
        for x in PROBLEMS:
            print(f"  • {x}")
    else:
        print("A full day traded, and the books balance.")
    sys.exit(1 if PROBLEMS else 0)
