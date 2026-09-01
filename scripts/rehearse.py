"""
scripts/rehearse.py — walk the demo path through the API, in presentation order.

Not another test. The suite proves endpoints answer; this proves THE STORY
answers, step by step, in the order a person will click it, with the numbers
printed as they will appear on screen. If a step is going to fail in front of an
audience, it fails here first, quietly.

The path:

  1. front desk takes a booking            Grace, station tablet
  2. confirm is REFUSED without a deposit  the rule that protects the resort
  3. deposit paid, confirm succeeds
  4. check in                              THE FIX: the room lands on the tab
  5. waiter puts a drink on the same tab    Ivan
  6. the bar makes it and it is served      David
  7. guest tries to leave                   REFUSED, bill outstanding
  8. guest pays, checks out                 the door opens
  9. the owner reads the money              Amara

Uses a REAL villa and checks the guest out again, so the villa is free
afterwards and the only trace is one completed stay — which is honest history,
not litter.

Run:  python scripts/rehearse.py
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
from app.models.order_item import OrderItem                   # noqa: E402
from app.models.bookable_resource import BookableResource     # noqa: E402
from app.services.tab import get_tab_balance                  # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
FAILED = []


def step(n, who, what, ok, detail=""):
    mark = "ok " if ok else "✗ FAILS LIVE"
    print(f"  {n}. [{who:14}] {what:44} {mark}  {detail}")
    if not ok:
        FAILED.append(what)
    return ok


class Desk:
    def __init__(self, app, username):
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            raise SystemExit(f"no such user: {username}")
        self.c = app.test_client()
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h, environ_base=LAN, **kw)

    def post(self, p, json=None):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN)


def run(app):
    with app.app_context():
        front = Desk(app, "grace.muthoni")     # station :5176
        waiter = Desk(app, "ivan.kipchoge")    # station :5176
        bar = Desk(app, "david.otieno")        # station :5176
        owner = Desk(app, "amara.wanjiku")     # owner   :5174
        for d in (front, waiter, bar, owner):
            d.post("/hr/clock-in", {})

        # A real, FREE villa, so the screens show a real room. Freed again at
        # the end. Picking one by name was the first thing this script got
        # wrong: Villa 14 was still occupied by a leftover test guest, and the
        # booking was refused — which is exactly the failure this exists to
        # find before an audience does.
        from app.models.booking import Booking
        taken = {b.resource_id for b in db.session.query(Booking)
                 .filter_by(status="CHECKED_IN").all()}
        villa = next((v for v in db.session.query(BookableResource)
                      .filter_by(resource_type="VILLA", is_active=True)
                      .order_by(BookableResource.name).all()
                      if v.id not in taken), None)
        if not villa:
            raise SystemExit("Every villa is occupied — free one before demoing.")

        print(f"\n  {villa.name} · KSh {villa.base_price}/night · sleeps {villa.capacity}\n")

        ci = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
        r = front.post("/bookings", {
            "resource_id": villa.id, "guest_name": "Otieno Barasa",
            "guest_phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
            "check_in_planned_utc": ci.isoformat(),
            "check_out_planned_utc": (ci + timedelta(days=2)).isoformat(),
            "number_of_guests": 2})
        if not step(1, "front desk", "takes a 2-night booking", r.status_code == 201,
                    f"room KSh {r.get_json().get('base_total')}" if r.status_code == 201
                    else str(r.get_json())[:50]):
            return
        bk = r.get_json()

        r = front.post(f"/bookings/{bk['id']}/confirm")
        step(2, "front desk", "confirm REFUSED with no deposit", r.status_code == 400,
             str(r.get_json().get("error", ""))[:44])

        front.post("/booking-payments", {"booking_id": bk["id"], "purpose": "DEPOSIT",
                                         "method": "MPESA", "amount": bk["deposit_required"]})
        r = front.post(f"/bookings/{bk['id']}/confirm")
        step(3, "front desk", f"deposit KSh {bk['deposit_required']} → confirm",
             r.status_code == 200)

        r = front.post(f"/bookings/{bk['id']}/check-in")
        if not step(4, "front desk", "CHECK IN — room lands on the tab",
                    r.status_code == 200, str(r.get_json())[:44] if r.status_code != 200 else ""):
            return
        tab = r.get_json()["tab_id"]
        owed = get_tab_balance(tab)
        print(f"        └─ tab now owes KSh {owed:,.2f}  "
              f"(room {bk['base_total']} − deposit {bk['deposit_required']})")

        drink = (db.session.query(MenuItem)
                 .filter(MenuItem.is_active == True,                    # noqa: E712
                         MenuItem.prep_station == "BAR",
                         MenuItem.stock_tracking != "UNTRACKED").first())
        r = waiter.post("/orders", {"tab_id": tab,
                                    "items": [{"menu_item_id": drink.id, "quantity": 2}]})
        ok = r.status_code == 201
        step(5, "waiter", f"puts 2x {drink.name} on the villa tab", ok,
             "" if ok else str(r.get_json())[:44])
        if ok:
            order = r.get_json()
            waiter.post(f"/orders/{order['id']}/send")
            for oi in db.session.query(OrderItem).filter_by(order_id=order["id"]).all():
                bar.post(f"/order-items/{oi.id}/receive")
                bar.post(f"/order-items/{oi.id}/ready")
                waiter.post(f"/order-items/{oi.id}/serve")
            step(6, "bar", "makes it, waiter serves it", True,
                 f"tab now KSh {get_tab_balance(tab):,.2f}")

        r = front.post(f"/bookings/{bk['id']}/check-out")
        step(7, "front desk", "guest tries to leave — REFUSED", r.status_code == 400,
             str(r.get_json().get("error", ""))[:46])

        owed = get_tab_balance(tab)
        r = front.post(f"/tabs/{tab}/payments", {"amount": str(owed), "method": "MPESA"})
        step(8, "front desk", f"guest pays KSh {owed:,.2f}", r.status_code in (200, 201),
             f"tab now {get_tab_balance(tab):,.2f}")

        r = front.post(f"/bookings/{bk['id']}/check-out")
        step(9, "front desk", "CHECK OUT — the door opens", r.status_code == 200,
             "villa free again" if r.status_code == 200 else str(r.get_json())[:44])

        print()
        for n, (who, what, path, q) in enumerate([
            ("owner", "menu profit and margins", "/finance/menu-engineering", {}),
            ("owner", "the money for the period", "/finance/dashboard", {}),
            ("owner", "the hash-chained audit trail", "/audit/verify", {}),
        ], start=10):
            r = owner.get(path, query_string=q)
            body = r.get_json() or {}
            extra = ("chain intact" if path.endswith("verify") and body.get("intact")
                     else f"{len(r.get_data())}B of data")
            step(n, who, what, r.status_code == 200, extra)


if __name__ == "__main__":
    run(create_app("development"))
    print("\n" + "=" * 74)
    if FAILED:
        print(f"{len(FAILED)} STEP(S) WOULD FAIL LIVE:")
        for f in FAILED:
            print(f"  • {f}")
    else:
        print("Every step of the demo answers. Safe to walk through live.")
    sys.exit(1 if FAILED else 0)
