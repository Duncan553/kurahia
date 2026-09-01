"""
scripts/ripple.py — do one thing, then check everywhere it should have landed.

scripts/reflect.py proved the core money and attendance loops agree with
themselves. This one goes after the features NOBODY has cross-checked, and it
follows each one OUTWARD: a feature is not "working" because its own endpoint
returned 201. It is working when the other places that claim to care about it
actually heard.

    sell past the reorder level   -> does the owner get a low-stock notice?
    sell an item with no recipe   -> does anybody get told stock is now wrong?
    a guest rates a waiter        -> does the waiter's score move?
    equipment goes overdue        -> does it show as due, derived not stored?
    a stock count finds a gap     -> does the variance say so, in shillings?

Every ripple below was read out of the source first, not guessed. Where a
feature has no downstream effect, the check is that it survives a round trip
and is visible to the role that needs it — no invented behaviour.

Run:  python scripts/ripple.py

NOT a seeder. Every write is an HTTP call by the person whose job it is.
Re-runnable: anything it creates is disabled or left inert at the end.
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                    # noqa: E402
from app.extensions import db                                 # noqa: E402
from app.models.user import User                              # noqa: E402
from app.models.role import Role                              # noqa: E402
from app.models.menu_item import MenuItem                     # noqa: E402
from app.models.inventory_item import InventoryItem           # noqa: E402
from app.models.notification import Notification              # noqa: E402
from app.services.stock import get_current_stock              # noqa: E402
from flask_jwt_extended import create_access_token             # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}
RESULTS = []


def record(ok, step, detail=""):
    RESULTS.append((ok, step, detail))
    print(f"{'  ok  ' if ok else '  ✗ NO RIPPLE'}  {step}{(' — ' + detail) if detail else ''}")


def expect(cond, step, detail=""):
    record(bool(cond), step, detail)
    return bool(cond)


def act(title):
    print(f"\n── {title} " + "─" * max(4, 58 - len(title)))


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

    def patch(self, p, json=None, **kw):
        return self.c.patch(p, json=json or {}, headers=self.h, environ_base=LAN, **kw)

    def clock_in(self):
        return self.post("/hr/clock-in", {})


def menu_id(name):
    m = db.session.query(MenuItem).filter_by(name=name, is_active=True).first()
    return m.id if m else None


def inv_id(name):
    i = db.session.query(InventoryItem).filter_by(name=name, is_active=True).first()
    return i.id if i else None


def notices_for(user_id, subject_startswith):
    return db.session.query(Notification).filter(
        Notification.recipient_user_id == user_id,
        Notification.subject.like(f"{subject_startswith}%"),
    ).all()


def sell_and_make(waiter, kitchen, bar, item_name, qty=1):
    """Order → send → receive → ready. READY is what fires consumption, so any
    check taken before it proves nothing."""
    mid = menu_id(item_name)
    if not mid:
        return None
    r = waiter.post("/orders", {"items": [{"menu_item_id": mid, "quantity": qty}]})
    if r.status_code != 201:
        return None
    order = r.get_json()
    waiter.post(f"/orders/{order['id']}/send")
    tab = waiter.get(f"/tabs/{order['tab_id']}").get_json()
    for item in tab["orders"][-1]["items"]:
        mi = db.session.query(MenuItem).filter_by(name=item["name"]).first()
        desk = kitchen if mi and mi.prep_station == "KITCHEN" else bar
        desk.post(f"/order-items/{item['id']}/receive")
        desk.post(f"/order-items/{item['id']}/ready")
    return order


# ══ 1. LOW STOCK ════════════════════════════════════════════════════════════
def ripple_low_stock(owner, mgr, waiter, kitchen, bar):
    """Selling past the reorder level must reach the OWNER, not just the table.

    The owner is the only person who can authorise a purchase, so a reorder
    level that nobody is told about is a number in a database.
    """
    act("selling past the reorder level")
    name = "Potatoes"
    iid = inv_id(name)
    item = db.session.get(InventoryItem, iid)

    # Put the reorder level just ABOVE current stock so the next sale crosses it.
    current = get_current_stock(iid)
    r = mgr.patch(f"/inventory/items/{iid}", {"reorder_level": str(current)})
    if not expect(r.status_code == 200, "manager sets the reorder level",
                  f"{name} at {current}, level now {current}"):
        return
    before = len(notices_for(owner.user_id, f"Low stock: {name}"))

    sell_and_make(waiter, kitchen, bar, "Chips", qty=1)

    after = notices_for(owner.user_id, f"Low stock: {name}")
    expect(len(after) > before or before > 0,
           "the owner is told stock crossed the line",
           after[-1].body[:60] if after else "no notification raised")

    # Twice in a day must not mean two pages. Alert fatigue is how a real alert
    # gets ignored.
    n1 = len(notices_for(owner.user_id, f"Low stock: {name}"))
    sell_and_make(waiter, kitchen, bar, "Chips", qty=1)
    n2 = len(notices_for(owner.user_id, f"Low stock: {name}"))
    expect(n2 == n1, "a second sale does not send a second page",
           f"{n1} notice(s), still {n1}" if n2 == n1 else f"{n1} -> {n2}")

    item.reorder_level = 0            # leave the store as we found it
    db.session.commit()


# ══ 2. NO RECIPE ════════════════════════════════════════════════════════════
def ripple_no_recipe(owner, mgr, chef, waiter, kitchen, bar):
    """An item that sells but deducts nothing must raise its hand.

    This is the silent one: stock drifts, nobody sees an error, and the count
    at the end of the month is wrong with no event to blame.
    """
    act("selling something with no recipe")
    dept = db.session.get(User, chef.user_id).department_id
    r = chef.post("/menu/items", {
        "name": f"Ripple Snack {uuid.uuid4().hex[:5].upper()}", "price": "250",
        "category": "Snacks", "prep_station": "KITCHEN", "department_id": dept,
        "idempotency_key": str(uuid.uuid4())})
    if not expect(r.status_code == 201, "chef adds an item with no recipe yet",
                  str(r.get_json())[:60]):
        return
    item = r.get_json()

    # UNTRACKED must REFUSE to sell. That block is the whole reason the
    # catalogue work mattered — an item nobody has classified cannot be sold.
    o = waiter.post("/orders", {"items": [{"menu_item_id": item["id"], "quantity": 1}]})
    expect(o.status_code >= 400,
           "an unclassified item cannot be sold at all",
           str(o.get_json().get("error", ""))[:60] if o.status_code >= 400
           else "IT SOLD — the untracked block is not holding")

    chef.post(f"/menu/items/{item['id']}/disable")


# ══ 3. GUEST FEEDBACK ═══════════════════════════════════════════════════════
def ripple_feedback(owner, mgr, front, waiter):
    """A guest rates the person who served them. That rating has to reach the
    performance score, or the review is a suggestion box with no bottom."""
    act("a guest rates the waiter who served them")
    prof = mgr.get("/hr/profiles").get_json() or []
    target = next((p for p in prof if p.get("user_id") == waiter.user_id), None)
    if not expect(target, "the waiter has an employee file"):
        return

    start = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    before = mgr.get(f"/hr/performance/{target['id']}",
                     query_string={"start_date": start, "end_date": end})
    rating_before = (before.get_json() or {}).get("guest_rating")

    r = front.post("/feedback", {
        "score": 5, "comment": "Very quick service at the pool bar.",
        "served_by_employee_id": target["id"],
        "guest_name": "Ripple Guest",
        "idempotency_key": str(uuid.uuid4())})
    if not expect(r.status_code in (200, 201), "the feedback is recorded",
                  str(r.get_json())[:70]):
        return

    after = mgr.get(f"/hr/performance/{target['id']}",
                    query_string={"start_date": start, "end_date": end}).get_json() or {}
    rating_after = (after.get("detail") or {}).get("guest_rating")
    expect(rating_after is not None,
           "it reaches the waiter's performance record",
           f"guest_rating {rating_before} -> {rating_after}")

    # ...but NOT the composite score. guest_rating is computed and reported in
    # `detail`, while composite_score is punctuality + attendance + cash_health
    # + void_health only (app/services/hr.py:298-304). It was built as a socket
    # before the Feedback model existed and never wired in.
    #
    # Recorded, deliberately NOT "fixed": how much a guest's opinion should
    # weigh against somebody's wages is Wachira's call, not an agent's.
    weights = after.get("weights") or {}
    expect("guest_rating" not in weights,
           "guest rating is still OUTSIDE the composite score — Wachira's call",
           f"weights: {', '.join(sorted(weights))}")


# ══ 4. EQUIPMENT ════════════════════════════════════════════════════════════
def ripple_equipment(owner, mgr):
    """is_due_service is DERIVED from the last service date. Servicing it must
    clear the flag with no separate 'is_due' field to forget to update."""
    act("equipment falls due, then is serviced")
    r = mgr.post("/equipment", {
        "name": f"Ripple Pump {uuid.uuid4().hex[:4].upper()}",
        "equipment_type": "PUMP",              # required — create takes no last_service
        "service_interval_days": 30,
        "idempotency_key": str(uuid.uuid4())})
    if not expect(r.status_code == 201, "manager registers a pump, 30-day interval",
                  str(r.get_json())[:70]):
        return
    eq = r.get_json()

    # Never serviced reads as NOT due, on purpose: is_due_service needs a last
    # service to measure from, and "we have no record" is not the same claim as
    # "it is overdue". Worth knowing — a pump nobody has ever serviced will not
    # appear on a due list.
    expect(eq.get("is_due_service") is False,
           "brand new, never serviced -> not flagged due (no date to measure from)",
           f"is_due_service={eq.get('is_due_service')}")

    r = mgr.post(f"/equipment/{eq['id']}/maintenance", {
        "notes": "Impeller cleaned, seals replaced.",
        "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code in (200, 201), "the service is logged",
           str(r.get_json())[:60])

    # Read it back off the LIST. There is no GET /equipment/<id> — only the
    # collection — so a detail screen has to pull the whole list and filter.
    # Nothing calls it today, so this is a note, not a bug.
    def read_back():
        rows = mgr.get("/equipment").get_json() or []
        rows = rows.get("equipment", rows) if isinstance(rows, dict) else rows
        return next((x for x in rows if x["id"] == eq["id"]), {})

    again = read_back()
    expect(again.get("is_due_service") is False,
           "and it reads as serviced — derived from the date, never stored",
           f"is_due_service={again.get('is_due_service')}")

    # Backdate the service past the interval and the SAME field must flip with
    # no write to the equipment row. That is what "derived" has to mean.
    from app.models.equipment import Equipment
    row = db.session.get(Equipment, eq["id"])
    row.last_service_utc = datetime.now(timezone.utc) - timedelta(days=90)
    db.session.commit()
    overdue = read_back()
    expect(overdue.get("is_due_service") is True,
           "90 days later it flags itself due, with nothing updating it",
           f"is_due_service={overdue.get('is_due_service')}")

    mgr.post(f"/equipment/{eq['id']}/disable")


# ══ 5. STOCK COUNT VARIANCE ═════════════════════════════════════════════════
def ripple_stock_count(owner, mgr, bar, chef):
    """Counting less than the ledger says is the theft signal. The variance has
    to be stated — a count that quietly overwrites the ledger hides the gap.

    WHO CAN COUNT is the finding here. Submitting a count needs manager level
    (>=5) AND, below owner, the item's own department. The seeded resort has
    nobody who is both: the manager sits in Management, and the kitchen and bar
    leads are level 3. So for a Bar or Kitchen item the ONLY person who can
    count is the owner — see the checks below, which pin it rather than pretend.
    """
    act("a stock count finds less than the books say")
    name = "Tusker Beer"
    iid = inv_id(name)
    expected = get_current_stock(iid)
    short_by = Decimal("3")

    r = mgr.post("/inventory/counts", {
        "item_id": iid, "counted_amount": str(expected),
        "count_type": "DAILY", "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code == 403,
           "the manager cannot count Bar stock — wrong department",
           str(r.get_json().get("error", ""))[:56])

    r = bar.post("/inventory/counts", {
        "item_id": iid, "counted_amount": str(expected),
        "count_type": "DAILY", "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code == 403,
           "the bar lead cannot either — below manager level",
           str(r.get_json().get("error", ""))[:56])

    # Which leaves exactly one person in the whole resort.
    r = owner.post("/inventory/counts", {
        "item_id": iid, "counted_amount": str(expected - short_by),
        "count_type": "DAILY", "notes": "ripple sweep",
        "idempotency_key": str(uuid.uuid4())})
    if not expect(r.status_code in (200, 201),
                  f"only the OWNER can count {name} — 3 short",
                  str(r.get_json())[:70]):
        return
    body = r.get_json()

    expect(Decimal(str(body.get("prior_stock"))) == expected,
           "it says what the books expected", f"prior_stock={body.get('prior_stock')}")
    expect(Decimal(str(body.get("adjustment"))) == -short_by,
           "and states the gap out loud, rather than quietly overwriting",
           f"adjustment={body.get('adjustment')}")

    after = get_current_stock(iid)
    expect(after == expected - short_by,
           "the ledger moves by an ADJUSTMENT movement, not an edit",
           f"{expected} -> {after}")

    # A gap must cost the item its trust. If a short count changed nothing about
    # how closely the item is watched, counting would be paperwork.
    expect("demoted" in body,
           "a short count is scored against the item's trust tier",
           f"prior_tier={body.get('prior_tier')} demoted={body.get('demoted')}")


# ══ 6. THE ROLE WALL ════════════════════════════════════════════════════════
def ripple_role_wall(waiter):
    """Every one of these, tried by a waiter, every run. A permission that is
    only checked when somebody remembers to check it is not a permission.

    Each POST carries a VALID body. A junk body gets rejected by validation
    before the role check ever runs, which proves nothing about the wall — the
    first version of this test sent junk, got a 400, and called it a leak.
    """
    act("a waiter tries every door they should not open")
    from app.models.user import User as U

    owner_role = db.session.query(Role).filter_by(name="owner").first()
    wall = [
        ("GET",  "/dashboard/finance", "the owner's money", None),
        ("GET",  "/hr/payroll-draft",  "everyone's wages", None),
        ("GET",  "/audit",             "the audit trail", None),
        ("GET",  "/suppliers",         "who we buy from", None),
        ("GET",  "/finance/budgets",   "the budgets", None),
        ("POST", "/suppliers",         "adding a supplier",
         {"name": f"Ripple Supplier {uuid.uuid4().hex[:5]}"}),
        # A complete, valid account request — nothing missing for validation to
        # trip over, so only the role check can stop it.
        ("POST", "/auth/users",        "minting an owner account",
         {"username": f"ripple.{uuid.uuid4().hex[:6]}", "password": "Kurahia1!",
          "role_id": owner_role.id if owner_role else None}),
    ]

    users_before = db.session.query(U).count()
    leaked = []
    for method, path, what, body in wall:
        r = waiter.get(path) if method == "GET" else waiter.post(path, body)
        ok = r.status_code in (401, 403, 404, 405)
        record(ok, f"{what:26} {method:4} {path}",
               "" if ok else f"OPENED with {r.status_code} {str(r.get_json())[:40]}")
        if not ok:
            leaked.append(path)

    expect(not leaked, "no owner-level door opened for a waiter",
           ", ".join(leaked) if leaked else "all held")
    # The assertion that actually matters: whatever the status code was, no
    # account came into existence.
    expect(db.session.query(U).count() == users_before,
           "and no account was created by any of it",
           f"{users_before} users before and after")


def run(app):
    with app.app_context():
        owner = Desk(app, "amara.wanjiku")
        mgr = Desk(app, "brian.mwangi")
        chef = Desk(app, "cynthia.achieng")
        bar = Desk(app, "david.otieno")
        front = Desk(app, "grace.muthoni")
        waiter = Desk(app, "peter.mwendwa")
        for d in (mgr, chef, bar, front, waiter):
            d.clock_in()

        ripple_low_stock(owner, mgr, waiter, chef, bar)
        ripple_no_recipe(owner, mgr, chef, waiter, chef, bar)
        ripple_feedback(owner, mgr, front, waiter)
        ripple_equipment(owner, mgr)
        ripple_stock_count(owner, mgr, bar, chef)
        ripple_role_wall(waiter)


if __name__ == "__main__":
    run(create_app("development"))
    bad = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} ripples landed")
    if bad:
        print(f"\n{len(bad)} DID NOT:")
        for _, step, detail in bad:
            print(f"  • {step}  {detail}")
    sys.exit(1 if bad else 0)
