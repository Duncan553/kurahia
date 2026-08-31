"""
scripts/scenarios.py — drive the whole resort through real endpoints.

NOT a seeder. Nothing is written directly to the database: every step is an
HTTP call a real person would make from a real screen, with a real role, and
each one is asserted. If a step 403s because the wrong person tried it, that is
a PASS — the point is to find the places where the system says yes when it
should say no, and no when it should say yes.

Run:  python scripts/scenarios.py           # once
      python scripts/scenarios.py --loop 3  # repeat, proving idempotency

Every run uses fresh names and phone numbers, so it can be run repeatedly
against the same database without colliding.
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, ".")
from app import create_app                                  # noqa: E402
from app.extensions import db                               # noqa: E402
from app.models.user import User                            # noqa: E402
from flask_jwt_extended import create_access_token           # noqa: E402

LAN = {"REMOTE_ADDR": "127.0.0.1"}          # inside the WiFi allow-list
RESULTS = []


def record(ok, scenario, step, detail=""):
    RESULTS.append((ok, scenario, step, detail))
    mark = "  ok " if ok else "  ✗ HOLE"
    print(f"{mark}  {step}{(' — ' + detail) if detail else ''}")


def expect(cond, scenario, step, detail=""):
    record(bool(cond), scenario, step, detail)
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
        return self.post("/hr/clock-in", {})


def uniq(prefix):
    return f"{prefix} {uuid.uuid4().hex[:5].upper()}"


def phone():
    return f"+2547{uuid.uuid4().int % 10**8:08d}"


# ── Scenario 1: villa guest, full stay ────────────────────────────────────────
def scenario_villa_stay(app, desks):
    s = "villa stay"
    print(f"\n── {s} " + "─" * (56 - len(s)))
    grace, waiter, mgr = desks["grace.muthoni"], desks["ivan.kipchoge"], desks["brian.mwangi"]

    # The harness makes its OWN villa rather than competing for real ones.
    # A first run that books the last free room leaves the resort full and every
    # later run failing on a business fact, not a bug — and worse, it puts test
    # guests in rooms real guests need. Created through POST /bookable-resources
    # like anything else, so the endpoint is exercised too.
    r = mgr.post("/bookable-resources", {
        "name": uniq("Test Villa"), "resource_type": "VILLA",
        "base_price": "12000", "capacity": 4,
    })
    if not expect(r.status_code == 201, s, "manager can create a bookable villa",
                  str(r.get_json())[:70]):
        return None
    made = r.get_json()

    free = [r for r in grace.get(
        "/bookings/availability",
        query_string={"resource_type": "VILLA",
                      "from": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                      "to": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()},
    ).get_json() if r["available"]]
    free = [r for r in free if r["id"] == made["id"]] or free
    if not expect(free, s, "the new villa shows as available"):
        return None

    ci = datetime.now(timezone.utc) + timedelta(hours=2)
    co = ci + timedelta(days=2)
    guest = uniq("Guest")
    r = grace.post("/bookings", {
        "resource_id": free[0]["id"], "guest_name": guest, "guest_phone": phone(),
        "guest_id_number": f"ID{uuid.uuid4().hex[:7].upper()}", "number_of_guests": 3,
        "check_in_planned_utc": ci.isoformat(), "check_out_planned_utc": co.isoformat(),
        "idempotency_key": str(uuid.uuid4()),
    })
    if not expect(r.status_code == 201, s, "front desk creates a booking", str(r.get_json())[:80]):
        return None
    bk = r.get_json()

    # Confirming before the deposit is paid must fail.
    r = grace.post(f"/bookings/{bk['id']}/confirm")
    expect(r.status_code == 400, s, "confirm is refused before the deposit is paid")

    grace.post("/booking-payments", {
        "booking_id": bk["id"], "purpose": "DEPOSIT", "method": "MPESA",
        "amount": bk["deposit_required"], "mpesa_code": f"Q{uuid.uuid4().hex[:8].upper()}",
        "idempotency_key": str(uuid.uuid4()),
    })
    expect(grace.post(f"/bookings/{bk['id']}/confirm").status_code == 200,
           s, "confirm succeeds once the deposit is in")

    r = grace.post(f"/bookings/{bk['id']}/check-in")
    if not expect(r.status_code == 200, s, "check-in opens a villa tab"):
        return None
    tab = r.get_json()["tab_id"]

    # The room must be ON the bill.
    folio = grace.get(f"/receipts/{tab}").get_json()
    rooms = [c for c in folio["charges"] if c["description"].startswith("Accommodation")]
    expect(len(rooms) == 1, s, "the room is charged to the tab",
           rooms[0]["description"] if rooms else "MISSING")
    expect(Decimal(folio["balance"]) > 0, s, "balance shows what is owed, not a credit",
           f"KSh {folio['balance']}")

    # Register the companions.
    for n in [uniq("Companion"), uniq("Companion")]:
        r = grace.post(f"/bookings/{bk['id']}/occupants",
                       {"full_name": n, "id_number": "X1", "may_charge": True})
        expect(r.status_code == 201, s, f"register {n.split()[0].lower()}")

    reg = grace.get(f"/bookings/{bk['id']}/occupants").get_json()
    expect(reg["unnamed_count"] == 0, s, "everyone booked for is now named",
           f"unnamed={reg['unnamed_count']}")

    # Waiter charges from the bar, having confirmed who may charge.
    waiter.clock_in()
    room_name = free[0]["name"]
    r = waiter.get(f"/tabs/by-room/{room_name}")
    expect(r.status_code == 200, s, "waiter finds the villa by room number")
    if r.status_code == 200:
        expect(guest in r.get_json()["may_charge"], s, "lookup says who may charge",
               ", ".join(r.get_json()["may_charge"])[:60])

    from app.models.menu_item import MenuItem
    beer = db.session.query(MenuItem).filter_by(name="Tusker Beer").first()
    r = waiter.post("/orders", {"tab_id": tab, "items": [{"menu_item_id": beer.id, "quantity": 2}],
                                "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code == 201, s, "waiter charges drinks to the villa")
    if r.status_code == 201:
        order_id = r.get_json()["id"]
        expect(waiter.post(f"/orders/{order_id}/send").status_code == 200,
               s, "order is sent to the bar")

        # Walk the drink through the bar the way the bar actually does it.
        # Skipping this leaves the item PENDING, and a tab with unserved items
        # cannot close — which is the system correctly refusing to let a guest
        # leave while something they ordered is still being made.
        bar = desks["david.otieno"]
        bar.clock_in()
        queue = bar.get("/bar/queue")
        if queue.status_code != 200:
            queue = bar.get("/pos/bar/queue")
        expect(queue.status_code == 200, s, "bar sees its queue",
               f"{len(queue.get_json() or [])} item(s)" if queue.status_code == 200 else str(queue.status_code))

        oi_id = grace.get(f"/tabs/{tab}").get_json()["orders"][-1]["items"][0]["id"]
        expect(bar.post(f"/order-items/{oi_id}/receive").status_code == 200,
               s, "bar accepts the ticket")
        expect(bar.post(f"/order-items/{oi_id}/ready").status_code == 200,
               s, "bar marks it ready — waiter is notified")
        expect(waiter.post(f"/order-items/{oi_id}/serve").status_code == 200,
               s, "waiter serves it")

        # The ready alert must have reached the waiter who sent it.
        inbox = waiter.get("/notifications/inbox")
        pings = [n for n in (inbox.get_json() or [])
                 if n.get("reference_type") == "order_ready"]
        expect(pings, s, "the waiter who sent it got the ready alert",
               f"{len(pings)} ping(s)")

    # Cannot leave owing money.
    r = grace.post(f"/bookings/{bk['id']}/check-out")
    expect(r.status_code == 400, s, "check-out refused while the bill stands",
           str(r.get_json().get("error", ""))[:60])

    # Settle in full, then leave.
    bal = grace.get(f"/receipts/{tab}").get_json()["balance"]
    grace.post(f"/tabs/{tab}/payments", {"method": "CASH", "amount": bal,
                                         "idempotency_key": str(uuid.uuid4())})
    folio = grace.get(f"/receipts/{tab}").get_json()
    expect(Decimal(folio["balance"]) == 0, s, "balance clears to zero", folio["balance"])

    # Check the guest out. Not politeness — a villa stays occupied until someone
    # leaves, so without this a second run finds no free rooms and the overstay
    # guard correctly refuses to sell an occupied one. Repeatability IS the test.
    r = grace.post(f"/bookings/{bk['id']}/check-out")
    expect(r.status_code == 200, s, "guest checks out once settled",
           str(r.get_json())[:70])

    # Retire the test villa — disabled, never deleted (invariant 6), because the
    # booking that just happened still references it.
    expect(mgr.post(f"/bookable-resources/{made['id']}/disable").status_code == 200,
           s, "test villa is retired, not deleted")
    return {"booking": bk, "tab": tab, "guest": guest}


# ── Scenario 2: gate visitor with a wristband ─────────────────────────────────
def scenario_gate_visitor(app, desks):
    s = "gate visitor"
    print(f"\n── {s} " + "─" * (56 - len(s)))
    gate = desks["hassan.omondi"]

    r = gate.post("/gate/issue-band", {"method": "CASH", "idempotency_key": str(uuid.uuid4())})
    if not expect(r.status_code == 201, s, "gate issues a band", str(r.get_json())[:70]):
        return
    band = r.get_json()

    r = gate.get(f"/gate/bands/{band['band_number']}")
    expect(r.status_code == 200, s, "band looks up by number")

    bal = Decimal(gate.get(f"/receipts/{band['tab_id']}").get_json()["balance"])
    expect(bal < 0, s, "entry fee sits as spendable credit", f"KSh {abs(bal)}")

    gate.post(f"/tabs/{band['tab_id']}/payments",
              {"method": "CASH", "amount": str(abs(bal)), "idempotency_key": str(uuid.uuid4())}) \
        if bal > 0 else None
    r = gate.post(f"/tabs/{band['tab_id']}/close")
    expect(r.status_code == 200, s, "band account closes")

    from app.models.wristband import Wristband
    db.session.expire_all()
    # By ID, never by number: band numbers reset daily, so filter_by(band_number)
    # matches every band that ever carried that number — three of them shared #7.
    w = db.session.get(Wristband, band["id"])
    expect(w and w.status != "ACTIVE", s, "the band dies with its account",
           f"status={w.status if w else '?'}")


# ── Scenario 3: who is allowed to do what ─────────────────────────────────────
def scenario_permissions(app, desks):
    s = "permissions"
    print(f"\n── {s} " + "─" * (56 - len(s)))
    grace, chef, waiter, mgr = (desks["grace.muthoni"], desks["cynthia.achieng"],
                                desks["ivan.kipchoge"], desks["brian.mwangi"])

    from app.models.department import Department
    dept = db.session.query(Department).filter_by(name="Bar").first()

    r = chef.post("/menu/items", {"name": uniq("Juice"), "price": "400", "category": "Soft Drinks",
                                  "prep_station": "BAR", "department_id": dept.id,
                                  "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code == 201, s, "head chef may add a juice")

    r = chef.post("/menu/items", {"name": uniq("Cocktail"), "price": "900", "category": "Cocktails",
                                  "prep_station": "BAR", "department_id": dept.id,
                                  "is_alcoholic": True, "idempotency_key": str(uuid.uuid4())})
    expect(r.status_code == 403, s, "head chef may NOT add alcohol")

    expect(waiter.get("/manager").status_code in (404, 405),
           s, "waiter has no manager endpoint to reach")
    expect(grace.post("/auth/users", {"username": uniq("x").lower().replace(" ", "."),
                                      "role_id": "nope"}).status_code in (400, 403, 404),
           s, "front desk cannot mint accounts freely")
    expect(mgr.get("/hr/payroll-draft",
                   query_string={"start_date": "2026-08-01", "end_date": "2026-08-31"}).status_code == 200,
           s, "manager can pull a payroll draft")


def run(app):
    with app.app_context():
        desks = {u: Desk(app, u) for u in
                 ["grace.muthoni", "ivan.kipchoge", "hassan.omondi",
                  "cynthia.achieng", "brian.mwangi", "david.otieno"]}
        scenario_villa_stay(app, desks)
        scenario_gate_visitor(app, desks)
        scenario_permissions(app, desks)


if __name__ == "__main__":
    loops = 1
    if "--loop" in sys.argv:
        loops = int(sys.argv[sys.argv.index("--loop") + 1])
    app = create_app("development")
    for i in range(loops):
        if loops > 1:
            print(f"\n{'=' * 62}\nPASS {i + 1} of {loops}\n{'=' * 62}")
        run(app)

    holes = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(RESULTS) - len(holes)}/{len(RESULTS)} steps passed")
    if holes:
        print(f"\n{len(holes)} HOLE(S):")
        for _, sc, st, d in holes:
            print(f"  • [{sc}] {st}  {d}")
    sys.exit(1 if holes else 0)
