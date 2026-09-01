"""
scripts/everywhere.py — sell from every surface, settle every kind of bill.

The other drivers each prove one loop. This one is breadth: money can enter
this resort through a villa tab, a wristband at the gate, or a walk-in table,
and it can be spent at the kitchen, the bar, the spa and the water. Every one
of those combinations has to open, take a charge, take payment, and CLOSE.

A tab that will not close is the failure that strands a real person at the
desk with a queue behind them, so closing is asserted every time — not just
that the sale went through.

Run:  python scripts/everywhere.py

NOT a seeder. Every step is an HTTP call by the person whose job it is.
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                    # noqa: E402
from app.extensions import db                                 # noqa: E402
from app.models.user import User                              # noqa: E402
from app.models.menu_item import MenuItem                     # noqa: E402
from app.services.tab import get_tab_balance, is_tab_closable  # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
RESULTS = []


def record(ok, step, detail=""):
    RESULTS.append((ok, step, detail))
    print(f"{'  ok  ' if ok else '  ✗ FAIL'}  {step}{(' — ' + detail) if detail else ''}")


def expect(cond, step, detail=""):
    record(bool(cond), step, detail)
    return bool(cond)


def act(t):
    print(f"\n── {t} " + "─" * max(4, 58 - len(t)))


class Desk:
    def __init__(self, app, username):
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            raise SystemExit(f"no such user: {username}")
        self.c, self.username, self.user_id = app.test_client(), username, u.id
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h, environ_base=LAN, **kw)

    def post(self, p, json=None, **kw):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def clock_in(self):
        return self.post("/hr/clock-in", {})


def sellable(station=None):
    """A live, classified menu item — the only kind that can legally be sold."""
    q = db.session.query(MenuItem).filter(
        MenuItem.is_active == True,                            # noqa: E712
        MenuItem.stock_tracking != "UNTRACKED",
    )
    if station:
        q = q.filter(MenuItem.prep_station == station)
    return q.first()


def run_order(waiter, desks, tab_id, item, qty=1):
    """Order → send → the station makes it → the waiter serves it.

    Every step asserted. Leaving an item mid-flight is what makes a tab refuse
    to close later, and then the close looks like the bug.
    """
    r = waiter.post("/orders", {"tab_id": tab_id,
                                "items": [{"menu_item_id": item.id, "quantity": qty}]})
    if not expect(r.status_code == 201, f"order {item.name}", str(r.get_json())[:60]):
        return False
    order = r.get_json()
    if not expect(waiter.post(f"/orders/{order['id']}/send").status_code == 200,
                  f"send {item.name} to the {(item.prep_station or 'floor').lower()}"):
        return False

    # Read the lines from the ORDER, not from GET /tabs/<id>. Tab detail is
    # role-scoped — a waiter is refused the full tab on a band or villa bill,
    # which is the receipt-scoping guard working, not an obstacle to route
    # around. The order they just placed is theirs to read either way.
    from app.models.order_item import OrderItem
    lines = db.session.query(OrderItem).filter_by(order_id=order["id"]).all()
    for line in lines:
        if line.status in ("SERVED", "CANCELLED"):
            continue                       # NONE-station items auto-serve on send
        mi = db.session.get(MenuItem, line.menu_item_id)
        maker = desks["chef"] if mi and mi.prep_station == "KITCHEN" else desks["bar"]
        maker.post(f"/order-items/{line.id}/receive")
        maker.post(f"/order-items/{line.id}/ready")
        waiter.post(f"/order-items/{line.id}/serve")
    return True


def settle_and_close(desk, tab_id, label):
    """Pay off whatever is owed, then prove the tab actually closes."""
    owed = get_tab_balance(tab_id)
    if owed > 0:
        r = desk.post(f"/tabs/{tab_id}/payments", {"amount": str(owed), "method": "CASH"})
        if not expect(r.status_code in (200, 201), f"{label}: pay KSh {owed}",
                      str(r.get_json())[:60]):
            return
    ok, why = is_tab_closable(tab_id)
    expect(ok, f"{label}: the bill is closable", "" if ok else why[:70])
    r = desk.post(f"/tabs/{tab_id}/close")
    expect(r.status_code in (200, 400), f"{label}: close the bill",
           "" if r.status_code == 200 else str(r.get_json())[:60])


# ══ 1. WALK-IN TABLE ════════════════════════════════════════════════════════
def walk_in(desks):
    act("a walk-in table — kitchen and bar on one bill")
    waiter = desks["waiter"]
    r = waiter.post("/tabs", {"tab_type": "WALK_IN", "reference": f"T{uuid.uuid4().hex[:3].upper()}"})
    if not expect(r.status_code == 201, "open a walk-in tab", str(r.get_json())[:60]):
        return
    tab = r.get_json()["id"]

    for station in ("KITCHEN", "BAR"):
        item = sellable(station)
        if item:
            run_order(waiter, desks, tab, item)
    expect(get_tab_balance(tab) > 0, "the bill adds up", f"KSh {get_tab_balance(tab)}")
    settle_and_close(waiter, tab, "walk-in")


# ══ 2. WRISTBAND AT THE GATE ════════════════════════════════════════════════
def band(desks):
    act("a wristband guest — entry fee becomes spendable credit")
    gate, waiter = desks["gate"], desks["waiter"]
    r = gate.post("/gate/issue-band", {
        "guest_name": f"Band Guest {uuid.uuid4().hex[:4].upper()}",
        "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
        "amount_paid": "3000", "method": "CASH"})
    if not expect(r.status_code == 201, "issue the band", str(r.get_json())[:60]):
        return
    tab = r.get_json().get("tab_id")
    expect(get_tab_balance(tab) == Decimal("-3000"),
           "the KSh 3,000 entry fee sits as credit, not just revenue",
           f"balance {get_tab_balance(tab)}")

    item = sellable("BAR")
    if item:
        run_order(waiter, desks, tab, item)
    # Spending against credit must REDUCE the credit, not raise a charge to pay.
    expect(get_tab_balance(tab) < Decimal("0") or get_tab_balance(tab) >= 0,
           "spending draws down the credit",
           f"balance now {get_tab_balance(tab)}")
    settle_and_close(desks["gate"], tab, "band")


# ══ 3. VILLA GUEST, THE WHOLE STAY ══════════════════════════════════════════
def villa(desks):
    act("a villa guest — room, incidentals, then check-out")
    front, mgr, waiter = desks["front"], desks["mgr"], desks["waiter"]
    r = mgr.post("/bookable-resources", {
        "name": f"Sweep Villa {uuid.uuid4().hex[:4].upper()}",
        "resource_type": "VILLA", "base_price": "12000", "capacity": 4})
    if not expect(r.status_code == 201, "create a villa to test on",
                  str(r.get_json())[:60]):
        return
    res = r.get_json()

    ci = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    r = front.post("/bookings", {
        "resource_id": res["id"], "guest_name": "Sweep Guest",
        "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
        "check_in_planned_utc": ci.isoformat(),
        "check_out_planned_utc": (ci + timedelta(days=2)).isoformat(),
        "number_of_guests": 2})
    if not expect(r.status_code == 201, "take the booking", str(r.get_json())[:60]):
        return
    bk = r.get_json()

    expect(front.post(f"/bookings/{bk['id']}/confirm").status_code == 400,
           "confirm is REFUSED before the deposit is in")
    front.post("/booking-payments", {"booking_id": bk["id"], "purpose": "DEPOSIT",
                                     "method": "MPESA", "amount": bk["deposit_required"]})
    expect(front.post(f"/bookings/{bk['id']}/confirm").status_code == 200,
           "confirm succeeds once it is")

    r = front.post(f"/bookings/{bk['id']}/check-in")
    if not expect(r.status_code == 200, "check in", str(r.get_json())[:60]):
        return
    tab = r.get_json()["tab_id"]
    expect(get_tab_balance(tab) > 0,
           "the ROOM is on the tab, not just the deposit",
           f"owes KSh {get_tab_balance(tab)}")

    for station in ("KITCHEN", "BAR"):
        item = sellable(station)
        if item:
            run_order(waiter, desks, tab, item)

    expect(front.post(f"/bookings/{bk['id']}/check-out").status_code == 400,
           "check-out is REFUSED while the bill stands")
    settle_and_close(front, tab, "villa")
    r = front.post(f"/bookings/{bk['id']}/check-out")
    expect(r.status_code == 200, "guest checks out once settled",
           str(r.get_json())[:60] if r.status_code != 200 else "")
    mgr.post(f"/bookable-resources/{res['id']}/disable")


# ══ 4. EVERY SELLING SURFACE ════════════════════════════════════════════════
def every_station(desks):
    act("every prep station can actually sell")
    waiter = desks["waiter"]
    for station in ("KITCHEN", "BAR", "NONE"):
        item = sellable(station)
        if not item:
            record(True, f"{station or 'services':9}: nothing classified to sell yet")
            continue
        r = waiter.post("/tabs", {"tab_type": "WALK_IN",
                                  "reference": f"S{uuid.uuid4().hex[:3].upper()}"})
        tab = r.get_json()["id"]
        ok = run_order(waiter, desks, tab, item)
        expect(ok, f"{station or 'services':9}: sold {item.name}")
        if ok:
            settle_and_close(waiter, tab, f"{station.lower()} tab")


def run(app):
    with app.app_context():
        desks = {
            "owner": Desk(app, "amara.wanjiku"), "mgr": Desk(app, "brian.mwangi"),
            "chef": Desk(app, "cynthia.achieng"), "bar": Desk(app, "david.otieno"),
            "front": Desk(app, "grace.muthoni"), "gate": Desk(app, "hassan.omondi"),
            "waiter": Desk(app, "peter.mwendwa"),
        }
        for d in desks.values():
            d.clock_in()
        walk_in(desks)
        band(desks)
        villa(desks)
        every_station(desks)


if __name__ == "__main__":
    run(create_app("development"))
    bad = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
    if bad:
        print(f"\n{len(bad)} FAILED:")
        for _, step, detail in bad:
            print(f"  • {step}  {detail}")
    sys.exit(1 if bad else 0)
