"""
scripts/tidy_demo_data.py — clear the test litter out of the demo database.

The drivers (scenarios, catalogue, reflect, ripple, everywhere) all write to the
real dev database, because that is the point: they exercise the system the way a
person would. The cost is that after enough runs the resort looks like a test
harness — a hundred open tabs, staff who were hired to prove hiring works, beer
drunk down to five bottles.

This puts it back to something a person can be shown, using the SAME endpoints
a manager would use. Nothing is deleted (invariant 6: disable, never delete) and
nothing is invented.

WHAT IT WILL NOT DO, on purpose: settle a tab that still owes money. Closing a
bill means recording a payment, and recording a payment that nobody made would
inflate the revenue on the very dashboard being demonstrated. Those tabs are
listed at the end instead, for a human to decide about.

Run:  python scripts/tidy_demo_data.py            # report only, changes nothing
      python scripts/tidy_demo_data.py --apply    # do it
"""
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                    # noqa: E402
from app.extensions import db                                 # noqa: E402
from app.models.user import User                              # noqa: E402
from app.models.tab import Tab, TabStatus                     # noqa: E402
from app.models.order_item import OrderItem                   # noqa: E402
from app.models.order import Order                            # noqa: E402
from app.models.inventory_item import InventoryItem           # noqa: E402
from app.services.tab import get_tab_balance                  # noqa: E402
from app.services.stock import get_current_stock              # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
APPLY = "--apply" in sys.argv

# Restock anything at or below this so the screens do not read as an empty bar.
LOW_WATER = Decimal("12")
RESTOCK = {                       # item -> (quantity, total KSh, real pack)
    "Tusker Beer":            ("24", "2880", "one crate of 24 @ KSh 120/bottle"),
    "Guinness":               ("24", "3600", "one crate of 24 @ KSh 150/bottle"),
    "Soda 330ml":             ("24", "1200", "one crate of 24 @ KSh 50/bottle"),
    "Mineral Water 500ml":    ("24",  "600", "one shrink-pack of 24 @ KSh 25"),
    "Chocolate Cake (whole)": ("4", "10000", "4 whole cakes @ KSh 2,500"),
    "Spices Mix":             ("2",  "1600", "2kg @ KSh 800/kg"),
    "Fuel":                   ("20", "3900", "20L @ KSh 195/L"),
    "Petrol (outboard)":      ("50", "9750", "50L @ KSh 195/L"),
    "Paddle Sets":            ("4",  "9600", "4 sets @ KSh 2,400"),
    "Aromatherapy Kit":       ("4", "14000", "4 sets @ KSh 3,500"),
    "Massage Oil":            ("6",  "7200", "6 bottles @ KSh 1,200"),
    "Cooking Oil":            ("20", "5600", "one 20L jerrican @ KSh 280/L"),
}


def say(action, detail=""):
    print(f"  {'✓' if APPLY else '·'} {action}{(' — ' + detail) if detail else ''}")


class Desk:
    def __init__(self, app, username):
        u = db.session.query(User).filter_by(username=username).first()
        self.c, self.user_id = app.test_client(), u.id
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def post(self, p, json=None):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN)


def run(app):
    with app.app_context():
        owner = Desk(app, "amara.wanjiku")
        owner.post("/hr/clock-in", {})

        # ── 1. Items stuck mid-flight ─────────────────────────────────────────
        # A driver that stopped between "send" and "serve" leaves an item on the
        # pass forever, and a tab cannot close while one is in flight. These are
        # test orders nobody is waiting for, so they are CANCELLED, not served —
        # serving something that was never made would be a lie in the ledger.
        stuck = db.session.query(OrderItem).filter(
            ~OrderItem.status.in_(["SERVED", "CANCELLED", "REFUNDED"])).all()
        print(f"\n── {len(stuck)} order item(s) stuck mid-flight")
        cancelled = 0
        for oi in stuck:
            if APPLY:
                r = owner.post(f"/order-items/{oi.id}/cancel",
                               {"reason": "Test order — cleared before demo."})
                if r.status_code in (200, 201):
                    cancelled += 1
            else:
                cancelled += 1
        say(f"cancelled {cancelled} of {len(stuck)}")

        # ── 2. Tabs that owe nothing ──────────────────────────────────────────
        # Settled or never charged. Closing these invents nothing.
        open_tabs = db.session.query(Tab).filter(Tab.status != TabStatus.CLOSED.value).all()
        zero, owing = [], []
        for t in open_tabs:
            (owing if get_tab_balance(t.id) > 0 else zero).append(t)
        print(f"\n── {len(open_tabs)} open tab(s): {len(zero)} owe nothing, {len(owing)} still owe")
        closed = 0
        for t in zero:
            if APPLY:
                if owner.post(f"/tabs/{t.id}/close").status_code == 200:
                    closed += 1
            else:
                closed += 1
        say(f"closed {closed} tab(s) that owed nothing")

        # ── 3. Staff hired to prove hiring works ──────────────────────────────
        test_users = db.session.query(User).filter(
            db.or_(User.username.like("newhire.%"),
                   User.username.like("ripple.%"),
                   User.username.like("chef_test%")),
            User.is_active == True).all()                       # noqa: E712
        print(f"\n── {len(test_users)} test staff account(s) still active")
        for u in test_users:
            if APPLY:
                owner.post(f"/auth/deactivate/{u.id}")
            say(f"deactivated {u.username}")

        # ── 4. Put stock back on the shelves ──────────────────────────────────
        print("\n── restocking what the drivers drank and cooked")
        for name, (qty, cost, pack) in RESTOCK.items():
            item = db.session.query(InventoryItem).filter_by(name=name, is_active=True).first()
            if not item:
                continue
            have = get_current_stock(item.id)
            if have > LOW_WATER:
                continue
            if APPLY:
                r = owner.post("/inventory/purchases", {
                    "item_id": item.id, "quantity": qty, "actual_cost": cost,
                    "receipt_photo_path": f"receipts/restock-{uuid.uuid4().hex[:8]}.jpg",
                    "notes": pack, "idempotency_key": f"tidy-{uuid.uuid4()}"})
                ok = r.status_code in (200, 201)
            else:
                ok = True
            say(f"{name}: {have} -> +{qty}" if ok else f"{name}: FAILED", pack)

        # ── What is left for a person to decide ───────────────────────────────
        print(f"\n── LEFT ALONE: {len(owing)} tab(s) that still owe money")
        print("   Closing a tab records a PAYMENT. Recording payments nobody made")
        print("   would inflate the revenue on the dashboard being demonstrated,")
        print("   so these are listed, not settled:\n")
        total = Decimal("0")
        for t in sorted(owing, key=lambda x: -get_tab_balance(x.id))[:10]:
            bal = get_tab_balance(t.id)
            total += bal
            print(f"     {t.tab_type:8} {(t.reference or t.id[:8]):14} KSh {bal:>12,.2f}")
        rest = sum((get_tab_balance(t.id) for t in owing), Decimal("0"))
        if len(owing) > 10:
            print(f"     ... and {len(owing) - 10} more")
        print(f"\n   total unpaid on test tabs: KSh {rest:,.2f}")
        print("   Either leave them (they are honest: bills that were never paid),")
        print("   or reseed the database for a clean start before presenting.")

        if not APPLY:
            print("\n  DRY RUN — nothing was changed. Re-run with --apply.")


if __name__ == "__main__":
    run(create_app("development"))
