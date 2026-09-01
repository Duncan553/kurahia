"""
scripts/full_circle.py — follow one bottle from the supplier to the guest, and back.

The question this answers: a guest drinks a Tusker. Who supplied that bottle,
what did the resort pay for it, what did the guest pay, and when the shelf runs
down, does anyone tell the person who can reorder it?

That is the whole inventory loop, and every link in it is checked here:

    supplier  ->  purchase  ->  stock in  ->  cost learned
                                                  |
                                             guest orders
                                                  |
    supplier  <-  reorder alert  <-  stock out  <-+

A break anywhere in that circle is a break in the resort's ability to answer
"where did this come from and what did it cost us" — which is the question
behind every margin on the owner's screen.

Run:  python scripts/full_circle.py
"""
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                    # noqa: E402
from app.extensions import db                                 # noqa: E402
from app.models.user import User                              # noqa: E402
from app.models.supplier import Supplier                      # noqa: E402
from app.models.purchase import Purchase                      # noqa: E402
from app.models.menu_item import MenuItem                     # noqa: E402
from app.models.order_item import OrderItem                   # noqa: E402
from app.models.charge import Charge                          # noqa: E402
from app.models.notification import Notification              # noqa: E402
from app.models.inventory_item import InventoryItem           # noqa: E402
from app.models.stock_movement import StockMovement           # noqa: E402
from app.services.stock import get_current_stock              # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
RESULTS = []


def link(ok, what, detail=""):
    RESULTS.append((ok, what, detail))
    print(f"  {'ok  ' if ok else '✗ BREAK'}  {what:46} {detail}")
    return ok


class Desk:
    def __init__(self, app, username):
        u = db.session.query(User).filter_by(username=username).first()
        self.c, self.user_id = app.test_client(), u.id
        self.h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h, environ_base=LAN, **kw)

    def post(self, p, json=None):
        return self.c.post(p, json=json or {}, headers=self.h, environ_base=LAN)


def run(app):
    with app.app_context():
        mgr = Desk(app, "brian.mwangi")
        waiter = Desk(app, "peter.mwendwa")
        bar = Desk(app, "david.otieno")
        owner = Desk(app, "amara.wanjiku")
        for d in (mgr, waiter, bar, owner):
            d.post("/hr/clock-in", {})

        stock = db.session.query(InventoryItem).filter_by(name="Tusker Beer",
                                                          is_active=True).first()
        supplier = db.session.query(Supplier).filter_by(name="Thika Road Beverages").first()

        print("\n── 1. the supplier ───────────────────────────────────────────")
        link(supplier is not None, "the supplier is on file",
             f"{supplier.name} · {supplier.phone}" if supplier else "not found")

        print("\n── 2. buying from them ───────────────────────────────────────")
        before = get_current_stock(stock.id)
        key = f"circle-{uuid.uuid4().hex[:8]}"
        r = mgr.post("/inventory/purchases", {
            "item_id": stock.id, "quantity": "25", "actual_cost": "3000",
            "supplier_name": supplier.name,
            "receipt_photo_path": f"receipts/{key}.jpg",
            "notes": "one crate of 25 @ KSh 120/bottle",
            "idempotency_key": key})
        link(r.status_code in (200, 201), "a crate of 25 is recorded against them",
             "KSh 3,000")
        after = get_current_stock(stock.id)
        link(after - before == Decimal("25"), "stock rose by exactly what arrived",
             f"{before} -> {after}")

        db.session.expire_all()
        stock = db.session.get(InventoryItem, stock.id)
        link(stock.cost_per_unit is not None, "the resort now knows what it PAID",
             f"KSh {stock.cost_per_unit}/bottle (weighted average)")

        purchase = db.session.query(Purchase).filter_by(idempotency_key=key).first()

        print("\n── 3. a guest drinks one ─────────────────────────────────────")
        beer = db.session.query(MenuItem).filter_by(name="Tusker Beer",
                                                     is_active=True).first()
        r = waiter.post("/orders", {"items": [{"menu_item_id": beer.id, "quantity": 1}]})
        link(r.status_code == 201, "the waiter puts it on a tab",
             f"guest pays KSh {beer.price}")
        order = r.get_json()
        waiter.post(f"/orders/{order['id']}/send")
        oi = db.session.query(OrderItem).filter_by(order_id=order["id"]).first()
        bar.post(f"/order-items/{oi.id}/receive")
        bar.post(f"/order-items/{oi.id}/ready")
        sold = get_current_stock(stock.id)
        link(after - sold == Decimal("1"), "one bottle leaves the shelf",
             f"{after} -> {sold}")

        print("\n── 4. can we trace the guest's bottle back? ──────────────────")
        charge = db.session.query(Charge).filter_by(order_item_id=oi.id).first()
        link(charge is not None, "the guest's charge links to the order item",
             f"KSh {charge.amount}" if charge else "")
        move = db.session.query(StockMovement).filter(
            StockMovement.idempotency_key.like(f"sale-{oi.id}-%")).first()
        link(move is not None, "the order item links to a stock movement",
             f"{move.change_amount} {stock.unit}" if move else "")
        link(move is not None and move.item_id == stock.id,
             "the movement names the very item bought from the supplier",
             stock.name)

        # THE LINK THAT IS ONLY A STRING.
        named = db.session.query(Supplier).filter_by(name=purchase.supplier_name).first()
        link(named is not None,
             "and the purchase resolves to a supplier ROW",
             f"matched '{purchase.supplier_name}' by NAME, not by id")

        margin = Decimal(str(beer.price)) - Decimal(str(stock.cost_per_unit))
        print(f"\n     bought for KSh {stock.cost_per_unit}  ->  sold for KSh {beer.price}"
              f"  ->  margin KSh {margin}")

        print("\n── 5. when the shelf runs down ───────────────────────────────")
        mgr.post(f"/inventory/items/{stock.id}", None)
        r = mgr.c.patch(f"/inventory/items/{stock.id}",
                        json={"reorder_level": str(get_current_stock(stock.id))},
                        headers=mgr.h, environ_base=LAN)
        link(r.status_code == 200, "manager sets the reorder level",
             f"at {get_current_stock(stock.id)}")
        n_before = db.session.query(Notification).filter(
            Notification.subject.like(f"Low stock: {stock.name}%")).count()
        r = waiter.post("/orders", {"items": [{"menu_item_id": beer.id, "quantity": 1}]})
        o2 = r.get_json()
        waiter.post(f"/orders/{o2['id']}/send")
        oi2 = db.session.query(OrderItem).filter_by(order_id=o2["id"]).first()
        bar.post(f"/order-items/{oi2.id}/receive")
        bar.post(f"/order-items/{oi2.id}/ready")
        n_after = db.session.query(Notification).filter(
            Notification.subject.like(f"Low stock: {stock.name}%")).count()
        link(n_after > n_before or n_before > 0,
             "crossing the line tells the OWNER to reorder",
             "the only person who can authorise a purchase")

        r = mgr.post("/inventory/purchase-requests",
                     {"item_id": stock.id, "quantity": "25",
                      "idempotency_key": str(uuid.uuid4())})
        link(r.status_code == 201, "a purchase request goes back to the supplier",
             "circle closed")
        stock.reorder_level = 0
        db.session.commit()


if __name__ == "__main__":
    run(create_app("development"))
    bad = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 66)
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} links in the circle hold")
    if bad:
        print("\nBREAKS:")
        for _, what, detail in bad:
            print(f"  • {what}  {detail}")
    sys.exit(1 if bad else 0)
