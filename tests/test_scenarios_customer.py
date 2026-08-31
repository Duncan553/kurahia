"""
tests/test_scenarios_customer.py — adversarial CUSTOMER / GUEST scenarios.

Domain: bookings, villas, check-in/out, occupants, wristbands at the gate,
guest records, waivers, feedback, ordering, the guest folio/receipt.

Two halves:
  GOOD  — does the thing a real front desk needs actually work end to end?
  BAD   — does the system REFUSE the wrong thing, with a plain-English reason?

Every test that asserts a HOLE is marked `# HOLE:` and states what the correct
behaviour would be, so the test doubles as the spec for the fix.
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures — villa pattern copied from tests/test_bookings.py (rule 3)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def villa(app):
    """A 4-sleeper villa at KSh 10,000/night."""
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Villa 6", resource_type=ResourceType.VILLA.value,
        base_price="10000", capacity=4,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def villa_b(app):
    """A second villa whose name is a PREFIX collision with the first
    ("Villa 6" vs "Villa 60") — used to probe the by-room lookup."""
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Villa 60", resource_type=ResourceType.VILLA.value,
        base_price="10000", capacity=4,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def jetski(app):
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Jetski A", resource_type=ResourceType.WATER_ACTIVITY.value,
        base_price="3000", capacity=2,
    )
    db.session.add(r)
    db.session.commit()
    return r


# ── helpers ───────────────────────────────────────────────────────────────────

def _dates(days_ahead=3, nights=2):
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=days_ahead)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=nights)).replace(hour=11, minute=0, second=0, microsecond=0)
    return ci, co


def make_booking(client, token, resource_id, name="John Doe", phone=None,
                 days_ahead=3, nights=2, guests=2, ci=None, co=None, **extra):
    d_ci, d_co = _dates(days_ahead, nights)
    body = {
        "resource_id": resource_id,
        "guest_name": name,
        "guest_phone": phone or f"+2547{uuid.uuid4().int % 10**8:08d}",
        "check_in_planned_utc":  (ci or d_ci).isoformat(),
        "check_out_planned_utc": (co or d_co).isoformat(),
        "number_of_guests": guests,
    }
    body.update(extra)
    return client.post("/bookings", json=body, headers=auth(token))


def pay_deposit(client, token, booking_id, amount):
    return client.post("/booking-payments", json={
        "booking_id": booking_id, "purpose": "DEPOSIT",
        "method": "MPESA", "amount": str(amount),
    }, headers=auth(token))


def stay(client, token, resource_id, **kw):
    """create → deposit → confirm → check-in. Returns (booking_id, tab_id)."""
    rv = make_booking(client, token, resource_id, **kw)
    assert rv.status_code == 201, rv.get_json()
    b = rv.get_json()
    if Decimal(b["deposit_required"]) > 0:
        assert pay_deposit(client, token, b["id"], b["deposit_required"]).status_code == 201
    assert client.post(f"/bookings/{b['id']}/confirm", headers=auth(token)).status_code == 200
    rv = client.post(f"/bookings/{b['id']}/check-in", headers=auth(token))
    assert rv.status_code == 200, rv.get_json()
    return b["id"], rv.get_json()["tab_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# GOOD PATHS — the real front-desk workflow
# ═══════════════════════════════════════════════════════════════════════════════

def test_full_stay_folio_shows_room_deposit_drinks_and_payment(
        client, manager_token, waiter_token, villa, drink_item_id):
    """The whole arc: book, deposit, confirm, check in, drink at the bar,
    settle, check out — and the folio names every line."""
    booking_id, tab_id = stay(client, manager_token, villa.id)

    # Room (2 nights x 10,000) is on the tab, deposit (30% = 6,000) credited.
    folio = client.get(f"/receipts/{tab_id}", headers=auth(manager_token)).get_json()
    descs = [c["description"] for c in folio["charges"]]
    assert any(d.startswith("Accommodation —") for d in descs), descs
    assert Decimal(folio["charges"][0]["amount"]) == Decimal("20000")
    assert Decimal(folio["payments"][0]["amount"]) == Decimal("6000")
    assert Decimal(folio["balance"]) == Decimal("14000")

    # A drink at the bar lands on the villa tab.
    rv = client.post("/orders", json={"tab_id": tab_id,
                                      "items": [{"menu_item_id": drink_item_id, "quantity": 2}]},
                     headers=auth(waiter_token))
    assert rv.status_code == 201, rv.get_json()
    order_id = rv.get_json()["id"]
    assert client.post(f"/orders/{order_id}/send", headers=auth(waiter_token)).status_code == 200

    tab = client.get(f"/tabs/{tab_id}", headers=auth(manager_token)).get_json()
    assert Decimal(tab["balance"]) == Decimal("14600")  # 20000 room - 6000 deposit + 600 beer

    # Bar makes it, waiter serves it — an unresolved item must not block checkout
    # by still sitting in the queue when the guest is at the desk.
    oi_id = tab["orders"][0]["items"][0]["id"]
    for step in ("receive", "ready", "serve"):
        assert client.post(f"/order-items/{oi_id}/{step}",
                           headers=auth(manager_token)).status_code == 200, step

    # Settle, then check out.
    assert client.post(f"/tabs/{tab_id}/payments",
                       json={"amount": "14600", "method": "CASH"},
                       headers=auth(manager_token)).status_code == 201
    rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
    assert rv.status_code == 200, rv.get_json()
    assert rv.get_json()["status"] == "CHECKED_OUT"

    # Folio after checkout still carries every line and both payments.
    folio = client.get(f"/receipts/{tab_id}", headers=auth(manager_token)).get_json()
    assert len(folio["payments"]) == 2
    assert Decimal(folio["balance"]) == Decimal("0")
    assert folio["closed_at"] is not None


def test_accommodation_is_charged_at_check_in_regression(client, manager_token, villa):
    """REGRESSION: base_total must hit the villa tab at check-in."""
    from app.extensions import db
    from app.models.charge import Charge
    _, tab_id = stay(client, manager_token, villa.id, nights=3)
    room = db.session.query(Charge).filter(
        Charge.tab_id == tab_id,
        Charge.description.like("Accommodation —%")).one()
    assert Decimal(str(room.amount)) == Decimal("30000")
    assert "3 nights" in room.description


def test_room_is_charged_once_even_if_the_service_is_re_run_regression(
        client, manager_token, villa):
    """REGRESSION: the room may never be charged twice.

    POST /check-in is already idempotent at the route (it returns early when the
    booking is CHECKED_IN), so that path never reaches the service a second
    time. This tests the layer BELOW it — a retry, a re-run of the sweep, or any
    future caller invoking the service directly. charge_accommodation_to_tab
    guards on "is there already an Accommodation line on this tab", which is
    safe because one villa tab belongs to exactly one booking.

    A double-charge here is not a cosmetic bug: the guest is billed the whole
    stay twice and check-out then refuses until they pay it.
    """
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.booking import Booking
    from app.models.tab import Tab
    from app.services.booking import charge_accommodation_to_tab

    _, tab_id = stay(client, manager_token, villa.id)
    booking = db.session.query(Booking).filter_by(tab_id=tab_id).one()
    tab     = db.session.get(Tab, tab_id)

    # Second run, straight at the service — the guard must swallow it.
    charge_accommodation_to_tab(booking, tab, tab.opened_by_id)
    db.session.commit()

    rooms = db.session.query(Charge).filter(
        Charge.tab_id == tab_id,
        Charge.description.like("Accommodation —%")).all()
    assert len(rooms) == 1
    balance = client.get(f"/tabs/{tab_id}", headers=auth(manager_token)).get_json()["balance"]
    assert Decimal(balance) == Decimal("14000")   # 20,000 room - 6,000 deposit


def test_guest_cannot_check_out_owing_the_room_regression(client, manager_token, villa):
    """REGRESSION: the whole point of charging the room — checkout must refuse
    while the accommodation is unpaid, and say the number out loud."""
    booking_id, tab_id = stay(client, manager_token, villa.id)
    rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
    assert rv.status_code == 400
    body = rv.get_json()
    assert Decimal(body["outstanding_balance"]) == Decimal("14000")
    assert "outstanding balance" in body["error"].lower()


def _pdf_strings(raw: bytes) -> list[str]:
    """Every literal reportlab drew, in page order.

    The PDF has one ASCII85+Flate page stream; decoding it gives the drawing
    operators, and each visible string is a `(text) Tj`. Cheap enough to do with
    the stdlib, and it is the only way to read a number the owner actually sees
    rather than the variable that fed it.
    """
    import re, zlib, base64
    body = raw[raw.index(b"stream\n") + 7: raw.index(b"endstream")].strip()
    text = zlib.decompress(base64.a85decode(body, adobe=True)).decode("latin-1")
    return [m.group(1) for m in re.finditer(r"\(([^)]*)\) Tj", text)]


def test_villa_revenue_report_counts_the_room_once_regression(
        client, owner_token, villa):
    """REGRESSION, two faults on the same report path.

    1. /reports/occupancy 500'd the moment ANY booking fell inside the range:
       SQLite returns check_in_planned_utc NAIVE, the range dates are tz-aware,
       and comparing them raises TypeError. Every existing test passed because
       every existing test asked for an empty range.

    2. The double-count question. Villa revenue is summed from Booking.base_total
       (app/reports/routes.py:386). Now that base_total ALSO exists as a Charge
       on the villa tab, the report must not pick it up a second time — it reads
       bookings only, never charges, so one stay is one 20,000, not 40,000.

    Before the tab fix, these two numbers actively disagreed: the report claimed
    20,000 earned while the tab had collected 6,000 and called the guest square.
    Now the room is one figure standing in both places.
    """
    from app.extensions import db
    from app.models.charge import Charge
    _, tab_id = stay(client, owner_token, villa.id)          # 2 nights x 10,000

    ci, co = _dates()
    rv = client.get("/reports/occupancy",
                    query_string={"from": ci.strftime("%Y-%m-%d"),
                                  "to":   co.strftime("%Y-%m-%d")},
                    headers=auth(owner_token))
    assert rv.status_code == 200, rv.get_json()              # fault 1
    assert rv.headers["Content-Type"] == "application/pdf"

    drawn = _pdf_strings(rv.data)
    total = drawn[drawn.index("Total revenue:") + 1]
    assert total == "KSh 20,000.00", drawn                   # fault 2 — not 40,000

    # The same 20,000 the guest's own bill is asking for.
    room = db.session.query(Charge).filter(
        Charge.tab_id == tab_id,
        Charge.description.like("Accommodation —%")).one()
    assert Decimal(str(room.amount)) == Decimal("20000")


def test_overstaying_guest_blocks_the_room_regression(client, manager_token, villa):
    """REGRESSION: a guest still CHECKED_IN past their planned checkout blocks
    a rebooking, whatever the calendar says."""
    from app.extensions import db
    from app.models.booking import Booking
    booking_id, _ = stay(client, manager_token, villa.id)

    # Rewind their stay into the past — they are still CHECKED_IN.
    b = db.session.get(Booking, booking_id)
    b.check_in_planned_utc  = datetime.now(timezone.utc) - timedelta(days=5)
    b.check_out_planned_utc = datetime.now(timezone.utc) - timedelta(days=1)
    db.session.commit()

    rv = make_booking(client, manager_token, villa.id, name="New Arrival", days_ahead=1)
    assert rv.status_code == 409
    assert "still occupied" in rv.get_json()["error"]

    # And availability agrees rather than contradicting the booking endpoint.
    # NOTE: query_string=dict, not an f-string — an ISO offset ends in "+00:00"
    # and a raw "+" in a URL decodes to a space, which made _parse_dt return a
    # 400 dict and the assertion below fail for the wrong reason.
    ci, co = _dates(1, 2)
    avail = client.get("/bookings/availability",
                       query_string={"from": ci.isoformat(), "to": co.isoformat()},
                       headers=auth(manager_token)).get_json()
    assert [r for r in avail if r["id"] == villa.id][0]["available"] is False


def test_closing_a_band_tab_deactivates_the_wristband_regression(client, manager_token):
    """REGRESSION: a settled band is a guest who left — the band stops being live."""
    from app.extensions import db
    from app.models.wristband import Wristband, WristbandStatus
    rv = client.post("/gate/issue-band", json={"method": "CASH"}, headers=auth(manager_token))
    assert rv.status_code == 201
    band = rv.get_json()
    assert Decimal(band["tab_balance"]) == Decimal("-3000")   # credit at the gate

    assert client.post(f"/tabs/{band['tab_id']}/close",
                       headers=auth(manager_token)).status_code == 200

    db.session.expire_all()
    row = db.session.query(Wristband).filter_by(id=band["id"]).one()
    assert row.status == WristbandStatus.DEACTIVATED.value
    assert client.get("/gate/active-bands", headers=auth(manager_token)).get_json() == []


def test_tab_by_room_finds_the_villa_and_says_who_may_charge(
        client, manager_token, waiter_token, villa):
    """REGRESSION: room lookup answers 'where does this go' AND 'should it'."""
    booking_id, tab_id = stay(client, manager_token, villa.id, name="Wanjiru Kamau", guests=3)

    # One companion may charge, one may not.
    assert client.post(f"/bookings/{booking_id}/occupants",
                       json={"full_name": "Peter Kamau", "may_charge": True},
                       headers=auth(manager_token)).status_code == 201
    assert client.post(f"/bookings/{booking_id}/occupants",
                       json={"full_name": "Amani Kamau", "is_adult": False},
                       headers=auth(manager_token)).status_code == 201

    # A waiter at the bar is exactly who needs this.
    rv = client.get("/tabs/by-room/Villa 6", headers=auth(waiter_token))
    assert rv.status_code == 200, rv.get_json()
    body = rv.get_json()
    assert body["tab_id"] == tab_id
    assert body["may_charge"] == ["Wanjiru Kamau", "Peter Kamau"]
    assert body["also_staying"] == ["Amani Kamau"]
    assert body["unnamed_count"] == 0


def test_tab_by_room_refuses_to_guess_between_two_open_accounts(
        client, manager_token, waiter_token, villa, villa_b):
    """REGRESSION: ambiguity returns 409 with candidates, never a silent pick.

    'Villa 6' is a substring of 'Villa 60', so a naive LIKE would match both —
    the exact-match-on-the-room-part rule is what saves it. The 409 path is
    proved with a prefix that is exact for neither.
    """
    _, tab6  = stay(client, manager_token, villa.id,   name="Guest A")
    _, tab60 = stay(client, manager_token, villa_b.id, name="Guest B")

    # Exact room name still resolves despite the prefix collision.
    rv = client.get("/tabs/by-room/Villa 6", headers=auth(waiter_token))
    assert rv.status_code == 200 and rv.get_json()["tab_id"] == tab6

    # An ambiguous fragment refuses and hands back the choice.
    rv = client.get("/tabs/by-room/Villa", headers=auth(waiter_token))
    assert rv.status_code == 409
    assert sorted(c["tab_id"] for c in rv.get_json()["candidates"]) == sorted([tab6, tab60])

    rv = client.get("/tabs/by-room/Villa 999", headers=auth(waiter_token))
    assert rv.status_code == 404


def test_waiver_gate_blocks_then_allows_then_blocks_again_after_revoke(
        client, manager_token, villa, jetski):
    booking_id, tab_id = stay(client, manager_token, villa.id)

    rv = client.post(f"/bookings/{booking_id}/water-sessions",
                     json={"resource_id": jetski.id}, headers=auth(manager_token))
    assert rv.status_code == 403
    assert "waiver" in rv.get_json()["error"].lower()

    w = client.post("/waivers", json={"booking_id": booking_id,
                                      "activity_type": "WATER_ACTIVITY",
                                      "signed_by_name": "John Doe"},
                    headers=auth(manager_token))
    assert w.status_code == 201
    waiver_id = w.get_json()["id"]

    rv = client.post(f"/bookings/{booking_id}/water-sessions",
                     json={"resource_id": jetski.id}, headers=auth(manager_token))
    assert rv.status_code == 201
    assert Decimal(rv.get_json()["amount"]) == Decimal("3000")

    assert client.post(f"/waivers/{waiver_id}/revoke",
                       headers=auth(manager_token)).status_code == 200
    rv = client.post(f"/bookings/{booking_id}/water-sessions",
                     json={"resource_id": jetski.id}, headers=auth(manager_token))
    assert rv.status_code == 403


def test_band_lookup_is_date_scoped(client, manager_token):
    """Band numbers reset daily. Band #1 today must not be band #1 yesterday."""
    from app.extensions import db
    from app.models.tab import Tab, TabType, TabStatus
    from app.models.payment import Payment
    from app.models.user import User
    from app.models.wristband import Wristband

    today_band = client.post("/gate/issue-band", json={"method": "CASH"},
                             headers=auth(manager_token)).get_json()
    assert today_band["band_number"] == 1

    # Hand-build yesterday's band #1 (the allocator only ever writes today).
    yday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    actor = db.session.query(User).filter_by(username="manager1").one()
    tab = Tab(tab_type=TabType.BAND.value, reference="Band #1", opened_by_id=actor.id,
              status=TabStatus.CLOSED.value)
    db.session.add(tab); db.session.flush()
    pay = Payment(tab_id=tab.id, amount=Decimal("3000"), method="CASH",
                  received_by_id=actor.id, idempotency_key=str(uuid.uuid4()))
    db.session.add(pay); db.session.flush()
    old = Wristband(band_number=1, issue_date=yday, issued_by_id=actor.id,
                    entry_payment_id=pay.id, tab_id=tab.id, status="FORFEITED",
                    idempotency_key=str(uuid.uuid4()))
    db.session.add(old); db.session.commit()

    # Default lookup = today.
    rv = client.get("/gate/bands/1", headers=auth(manager_token))
    assert rv.status_code == 200 and rv.get_json()["tab_id"] == today_band["tab_id"]

    # Explicit date reaches yesterday's band, and only that one.
    rv = client.get(f"/gate/bands/1?date={yday}", headers=auth(manager_token))
    assert rv.status_code == 200
    assert rv.get_json()["tab_id"] == tab.id
    assert rv.get_json()["status"] == "FORFEITED"


def test_band_credit_ceiling_stops_the_order_at_2x_entry_fee(
        client, manager_token, waiter_token, food_item_id):
    """A band tab may run to +6,000 (2x the 3,000 entry fee) and no further."""
    band = client.post("/gate/issue-band", json={"method": "CASH"},
                       headers=auth(manager_token)).get_json()
    tab_id = band["tab_id"]

    # -3000 + 7x1200 = +5400 → under the ceiling.
    o1 = client.post("/orders", json={"tab_id": tab_id,
                                      "items": [{"menu_item_id": food_item_id, "quantity": 7}]},
                     headers=auth(waiter_token)).get_json()["id"]
    assert client.post(f"/orders/{o1}/send", headers=auth(waiter_token)).status_code == 200

    # One more plate would clear the ceiling.
    o2 = client.post("/orders", json={"tab_id": tab_id,
                                      "items": [{"menu_item_id": food_item_id, "quantity": 1}]},
                     headers=auth(waiter_token)).get_json()["id"]
    rv = client.post(f"/orders/{o2}/send", headers=auth(waiter_token))
    assert rv.status_code == 400
    assert "spending limit" in rv.get_json()["error"]


def test_forfeit_day_closes_bands_and_their_tabs(client, manager_token):
    from app.extensions import db
    from app.models.tab import Tab, TabStatus
    from app.models.wristband import Wristband
    band = client.post("/gate/issue-band", json={"method": "CASH"},
                       headers=auth(manager_token)).get_json()

    rv = client.post("/gate/forfeit-day", json={}, headers=auth(manager_token))
    assert rv.status_code == 200
    assert rv.get_json()["forfeited"] == 1
    assert Decimal(rv.get_json()["total_unused_credit"]) == Decimal("3000")

    db.session.expire_all()
    assert db.session.query(Wristband).filter_by(id=band["id"]).one().status == "FORFEITED"
    assert db.session.get(Tab, band["tab_id"]).status == TabStatus.CLOSED.value
    # A forfeited band is no longer usable at the bar.
    assert client.post(f"/gate/deactivate-band/{band['band_number']}",
                       headers=auth(manager_token)).status_code == 404


def test_repeat_guest_is_matched_by_phone_and_history_accumulates(
        client, manager_token, villa, villa_b):
    phone = "+254712345678"
    b1 = make_booking(client, manager_token, villa.id, name="Grace Njeri",
                      phone=phone, days_ahead=2, nights=1).get_json()
    b2 = make_booking(client, manager_token, villa_b.id, name="Grace Njeri",
                      phone=phone, days_ahead=20, nights=1).get_json()
    assert b1["guest_record_id"] == b2["guest_record_id"]

    hist = client.get(f"/guest-records/{b1['guest_record_id']}/history",
                      headers=auth(manager_token))
    assert hist.status_code == 200
    assert len(hist.get_json()["bookings"]) == 2


def test_occupant_register_is_readable_by_any_serving_staff(
        client, manager_token, waiter_token, villa):
    """A waiter must be able to answer 'may this person charge here?'."""
    booking_id, _ = stay(client, manager_token, villa.id, guests=4)
    client.post(f"/bookings/{booking_id}/occupants", json={"full_name": "Companion One"},
                headers=auth(manager_token))
    rv = client.get(f"/bookings/{booking_id}/occupants", headers=auth(waiter_token))
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["number_of_guests"] == 4
    assert len(body["occupants"]) == 1
    assert body["unnamed_count"] == 2      # 4 booked - lead - 1 named


# ═══════════════════════════════════════════════════════════════════════════════
# BAD PATHS — does it refuse?
# ═══════════════════════════════════════════════════════════════════════════════

def test_double_booking_the_same_villa_is_refused(client, manager_token, villa):
    assert make_booking(client, manager_token, villa.id, days_ahead=5, nights=3).status_code == 201
    # Overlaps by one night.
    rv = make_booking(client, manager_token, villa.id, name="Second Guest",
                      days_ahead=7, nights=3)
    assert rv.status_code == 409
    assert "already booked" in rv.get_json()["error"]

    # Butting up exactly against the end is NOT an overlap and must be allowed.
    rv = make_booking(client, manager_token, villa.id, name="Third Guest",
                      days_ahead=8, nights=2)
    assert rv.status_code == 201, rv.get_json()


def test_check_out_date_before_check_in_is_refused(client, manager_token, villa):
    ci, co = _dates(5, 2)
    rv = make_booking(client, manager_token, villa.id, ci=co, co=ci)
    assert rv.status_code == 400
    assert "must be after" in rv.get_json()["error"]
    # Zero-length stay too.
    rv = make_booking(client, manager_token, villa.id, ci=ci, co=ci)
    assert rv.status_code == 400


def test_cannot_check_in_a_booking_that_was_never_confirmed(client, manager_token, villa):
    b = make_booking(client, manager_token, villa.id).get_json()
    rv = client.post(f"/bookings/{b['id']}/check-in", headers=auth(manager_token))
    assert rv.status_code == 400
    assert "HELD to CHECKED_IN" in rv.get_json()["error"]


def test_cannot_confirm_a_villa_without_the_deposit(client, manager_token, villa):
    b = make_booking(client, manager_token, villa.id).get_json()
    assert Decimal(b["deposit_required"]) == Decimal("6000")

    rv = client.post(f"/bookings/{b['id']}/confirm", headers=auth(manager_token))
    assert rv.status_code == 400
    assert "deposit" in rv.get_json()["error"].lower()

    # Part payment is still not enough.
    pay_deposit(client, manager_token, b["id"], "1000")
    rv = client.post(f"/bookings/{b['id']}/confirm", headers=auth(manager_token))
    assert rv.status_code == 400

    pay_deposit(client, manager_token, b["id"], "5000")
    assert client.post(f"/bookings/{b['id']}/confirm",
                       headers=auth(manager_token)).status_code == 200


def test_cannot_check_out_twice_or_cancel_after_check_in(client, manager_token, villa):
    booking_id, tab_id = stay(client, manager_token, villa.id)

    # Cancelling an occupied villa would leave a guest in a room nobody owns.
    rv = client.post(f"/bookings/{booking_id}/cancel", headers=auth(manager_token))
    assert rv.status_code == 400
    assert "CHECKED_IN to CANCELLED" in rv.get_json()["error"]

    client.post(f"/tabs/{tab_id}/payments", json={"amount": "14000", "method": "CASH"},
                headers=auth(manager_token))
    assert client.post(f"/bookings/{booking_id}/check-out",
                       headers=auth(manager_token)).status_code == 200
    rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
    assert rv.status_code == 400
    assert "terminal state" in rv.get_json()["error"]


def test_cannot_book_more_guests_than_the_villa_sleeps(client, manager_token, villa):
    rv = make_booking(client, manager_token, villa.id, guests=9)
    assert rv.status_code == 400
    assert "holds up to 4 guests" in rv.get_json()["error"]


def test_deposit_cannot_be_recorded_after_check_in(client, manager_token, villa):
    booking_id, _ = stay(client, manager_token, villa.id)
    rv = pay_deposit(client, manager_token, booking_id, "1000")
    assert rv.status_code == 400
    assert "HELD or CONFIRMED" in rv.get_json()["error"]


def test_occupant_cannot_be_added_to_a_booking_that_does_not_exist(client, manager_token):
    rv = client.post(f"/bookings/{uuid.uuid4()}/occupants",
                     json={"full_name": "Ghost"}, headers=auth(manager_token))
    assert rv.status_code == 404
    rv = client.get(f"/bookings/{uuid.uuid4()}/occupants", headers=auth(manager_token))
    assert rv.status_code == 404


def test_occupant_needs_a_name(client, manager_token, villa):
    booking_id, _ = stay(client, manager_token, villa.id)
    rv = client.post(f"/bookings/{booking_id}/occupants", json={"full_name": "   "},
                     headers=auth(manager_token))
    assert rv.status_code == 400


def test_occupant_edit_is_scoped_to_its_own_booking(client, manager_token, villa, villa_b):
    """An occupant id from booking A must not be editable through booking B's URL."""
    b1, _ = stay(client, manager_token, villa.id,   name="Guest A")
    b2, _ = stay(client, manager_token, villa_b.id, name="Guest B")
    occ = client.post(f"/bookings/{b1}/occupants", json={"full_name": "Companion"},
                      headers=auth(manager_token)).get_json()
    rv = client.patch(f"/bookings/{b2}/occupants/{occ['id']}",
                      json={"may_charge": True}, headers=auth(manager_token))
    assert rv.status_code == 404


def test_waiter_cannot_create_or_cancel_bookings(client, waiter_token, villa):
    rv = make_booking(client, waiter_token, villa.id)
    assert rv.status_code == 403
    assert "Staff or above" in rv.get_json()["error"]
    rv = client.get("/bookings", headers=auth(waiter_token))
    assert rv.status_code == 403


def test_waiter_cannot_issue_or_deactivate_a_wristband(client, manager_token, waiter_token):
    rv = client.post("/gate/issue-band", json={"method": "CASH"}, headers=auth(waiter_token))
    assert rv.status_code == 403
    band = client.post("/gate/issue-band", json={"method": "CASH"},
                       headers=auth(manager_token)).get_json()
    rv = client.post(f"/gate/deactivate-band/{band['band_number']}", headers=auth(waiter_token))
    assert rv.status_code == 403
    # But looking one up is allowed — that is the whole point of a band.
    assert client.get(f"/gate/bands/{band['band_number']}",
                      headers=auth(waiter_token)).status_code == 200


def test_issue_band_rejects_a_junk_payment_method(client, manager_token):
    rv = client.post("/gate/issue-band", json={"method": "GOAT"}, headers=auth(manager_token))
    assert rv.status_code == 400
    assert "Payment method must be one of" in rv.get_json()["error"]


def test_waiver_for_a_nonexistent_booking_is_refused(client, manager_token):
    rv = client.post("/waivers", json={"booking_id": str(uuid.uuid4()),
                                       "activity_type": "WATER_ACTIVITY",
                                       "signed_by_name": "Nobody"},
                     headers=auth(manager_token))
    assert rv.status_code == 404


def test_water_session_needs_the_guest_to_be_checked_in(client, manager_token, villa, jetski):
    b = make_booking(client, manager_token, villa.id).get_json()
    client.post("/waivers", json={"booking_id": b["id"], "activity_type": "WATER_ACTIVITY",
                                  "signed_by_name": "John Doe"}, headers=auth(manager_token))
    rv = client.post(f"/bookings/{b['id']}/water-sessions",
                     json={"resource_id": jetski.id}, headers=auth(manager_token))
    assert rv.status_code == 400
    assert "CHECKED_IN" in rv.get_json()["error"]


def test_feedback_score_must_be_1_to_5(client, manager_token):
    for bad in [0, 6, -1, "excellent", None]:
        rv = client.post("/feedback", json={"score": bad}, headers=auth(manager_token))
        assert rv.status_code == 400, bad


def test_guest_cannot_self_serve_feedback_known_design_gap(client):
    """Confirming the already-reported gap: /feedback needs a staff login, so a
    guest with a QR code on the table cannot leave a rating themselves."""
    rv = client.post("/feedback", json={"score": 5})
    assert rv.status_code in (401, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# HOLES — these assert the CURRENT (wrong) behaviour and name the right one.
# ═══════════════════════════════════════════════════════════════════════════════

def test_HOLE_occupant_register_allows_one_person_more_than_booked(
        client, manager_token, villa):
    """HOLE — app/bookings/core.py:566

        if already + 1 >= (booking.number_of_guests or 1) + 1:

    simplifies to `already >= number_of_guests`, so it permits N companions
    ALONGSIDE the lead guest — N+1 bodies in a villa booked for N. The guard's
    own docstring says "guard against listing more people than the villa was
    booked for", and list_occupants computes unnamed_count as
    `number_of_guests - 1 - len(rows)`, which only makes sense if occupants are
    capped at N-1. Correct condition: `already + 1 > number_of_guests - 1`.

    Consequence: it is also a capacity bypass — this booking is for 2 people in
    a villa that sleeps 4, and the register happily lists 3.
    """
    booking_id, _ = stay(client, manager_token, villa.id, guests=2)

    assert client.post(f"/bookings/{booking_id}/occupants",
                       json={"full_name": "Companion One"},
                       headers=auth(manager_token)).status_code == 201
    # This is the second companion on a TWO-guest booking — should be refused.
    second = client.post(f"/bookings/{booking_id}/occupants",
                         json={"full_name": "Companion Two"},
                         headers=auth(manager_token))
    assert second.status_code == 201, "fixed? then flip this to 400"

    body = client.get(f"/bookings/{booking_id}/occupants",
                      headers=auth(manager_token)).get_json()
    assert len(body["occupants"]) == 2
    assert body["number_of_guests"] == 2
    assert body["unnamed_count"] == 0      # clamped by max(0, ...) — hides the overflow
    # Three named humans on a booking that says two.
    assert 1 + len(body["occupants"]) == 3

    # The third one is finally refused, i.e. the cap is off by exactly one.
    assert client.post(f"/bookings/{booking_id}/occupants",
                       json={"full_name": "Companion Three"},
                       headers=auth(manager_token)).status_code == 400


def test_HOLE_occupant_cap_ignores_the_villa_capacity(client, manager_token, villa):
    """HOLE (same site, second face) — the register is checked against
    number_of_guests only, and number_of_guests is checked against capacity only
    at CREATE time. Book the villa full (4 = capacity) and the register accepts
    4 companions + the lead = 5 people in a 4-sleeper villa.
    """
    booking_id, _ = stay(client, manager_token, villa.id, guests=4)
    for i in range(4):
        rv = client.post(f"/bookings/{booking_id}/occupants",
                         json={"full_name": f"Companion {i}"}, headers=auth(manager_token))
        assert rv.status_code == 201, (i, rv.get_json())
    named = client.get(f"/bookings/{booking_id}/occupants",
                       headers=auth(manager_token)).get_json()
    assert 1 + len(named["occupants"]) == 5 > villa.capacity


def test_water_session_refuses_a_negative_amount_regression(client, manager_token, villa):
    """REGRESSION (was a HOLE, now closed at app/bookings/core.py:493-497).

    `amount` used to come straight from the request body and was only checked
    for being *parseable*, never for sign — so a single front-desk call with
    {"amount": "-14000"} wrote a negative Charge, which is a credit. A guest
    owing 14,000 for the room was wiped to 0 and walked out, with NO Payment
    record, so cash reconciliation saw nothing missing and check-out then
    succeeded. That is precisely the skim vector app/models/charge.py's
    docstring says no API accepts.

    Now refused with a plain-English reason, and the tab is untouched: the
    balance still stands and the door stays shut.
    """
    from app.extensions import db
    from app.models.payment import Payment
    booking_id, tab_id = stay(client, manager_token, villa.id)
    client.post("/waivers", json={"booking_id": booking_id, "activity_type": "WATER_ACTIVITY",
                                  "signed_by_name": "John Doe"}, headers=auth(manager_token))

    balance_before = client.get(f"/tabs/{tab_id}", headers=auth(manager_token)).get_json()["balance"]
    assert Decimal(balance_before) == Decimal("14000")

    rv = client.post(f"/bookings/{booking_id}/water-sessions",
                     json={"amount": "-14000", "description": "adjustment"},
                     headers=auth(manager_token))
    assert rv.status_code == 400
    assert "positive amount" in rv.get_json()["error"]

    # Nothing was written: same balance, still only the deposit payment.
    balance = client.get(f"/tabs/{tab_id}", headers=auth(manager_token)).get_json()["balance"]
    assert Decimal(balance) == Decimal("14000")
    assert db.session.query(Payment).filter_by(tab_id=tab_id).count() == 1  # the deposit only
    # And the door stays shut — the room is still owed.
    assert client.post(f"/bookings/{booking_id}/check-out",
                       headers=auth(manager_token)).status_code == 400


def test_HOLE_zero_or_negative_guest_count_crashes_instead_of_400(client, manager_token, villa):
    """HOLE — app/bookings/core.py:98-101 casts number_of_guests to int and
    never checks it is positive. check_capacity only tests the UPPER bound
    (`num_guests > capacity`), so 0 and -5 sail through to the INSERT, where
    the CHECK constraint ck_booking_guests_pos fires as an IntegrityError.

    A 500 on a typo'd form field is a bug in two ways: the guest sees a crash
    instead of "at least one guest", and every 500 in the log looks the same as
    a real fault. Expected: 400 with a plain-English message (invariant 5).
    """
    from sqlalchemy.exc import IntegrityError
    for bad in (0, -5):
        with pytest.raises(IntegrityError):
            make_booking(client, manager_token, villa.id, guests=bad)
        from app.extensions import db
        db.session.rollback()


def test_HOLE_number_of_guests_is_not_validated_as_a_number(client, manager_token, villa):
    """Sibling of the above and the one branch that IS handled — kept so the
    fix does not regress the good half while fixing the bad one."""
    rv = make_booking(client, manager_token, villa.id, guests="four")
    assert rv.status_code == 400
    assert "integer" in rv.get_json()["error"]


def test_HOLE_a_booking_entirely_in_the_past_is_accepted(client, manager_token, villa):
    """HOLE (lower severity) — nothing compares check_in_planned_utc to now.
    A stay can be entered for last month and it is created as HELD.

    Why it matters: flag_no_shows() immediately marks it NO_SHOW, and until that
    sweep runs it BLOCKS the room (HELD is a blocking status) for dates that have
    already gone. It is also how a backdated booking gets attached to a guest
    record after the fact. Retroactive entry may be legitimate at a resort, but
    it should be a deliberate, audited flag rather than the default.
    """
    from app.services.booking import flag_no_shows
    from app.extensions import db
    ci = datetime.now(timezone.utc) - timedelta(days=30)
    co = ci + timedelta(days=2)
    rv = make_booking(client, manager_token, villa.id, ci=ci, co=co)
    assert rv.status_code == 201, "fixed? then flip this to 400"
    assert rv.get_json()["status"] == "HELD"

    n = flag_no_shows()
    db.session.commit()
    assert n == 1   # it is immediately a no-show; it should never have existed


def test_HOLE_two_different_people_sharing_a_phone_become_one_guest(
        client, manager_token, villa, villa_b):
    """HOLE — app/services/booking.py:127-136 matches a GuestRecord by phone
    ALONE, and GuestRecord.phone is unique=True, so there is no way to store the
    second person. A married couple, a family sharing one line, or a company
    booking desk (extremely common in Kenya) collapses into a single guest.

    The record keeps the FIRST name forever, so /guest-records/<id>/history
    shows one person's stays under someone else's name — and last_visit_utc,
    which is what "repeat guest" recognition reads, is wrong for both.

    Expected: match on (phone, name) or return the record while keeping the
    booking's own name distinct in history, not silently merge two humans.
    """
    phone = "+254799000111"
    b1 = make_booking(client, manager_token, villa.id, name="Grace Njeri",
                      phone=phone, days_ahead=2, nights=1).get_json()
    b2 = make_booking(client, manager_token, villa_b.id, name="Ochieng Otieno",
                      phone=phone, days_ahead=2, nights=1).get_json()

    assert b1["guest_record_id"] == b2["guest_record_id"], "fixed? then expect two records"
    rec = client.get(f"/guest-records/{b2['guest_record_id']}",
                     headers=auth(manager_token)).get_json()
    assert rec["name"] == "Grace Njeri"      # Ochieng's booking is filed under Grace
    hist = client.get(f"/guest-records/{b1['guest_record_id']}/history",
                      headers=auth(manager_token)).get_json()
    assert hist["guest"]["name"] == "Grace Njeri"
    assert len(hist["bookings"]) == 2        # two different humans, one history


def test_get_tab_is_scoped_like_the_receipt_regression(
        client, manager_token, waiter_token, villa):
    """REGRESSION (was a HOLE, now closed at app/pos/tabs.py:161-167).

    app/pos/receipts.py scopes a folio on purpose ("a villa folio is a guest's
    whole stay") so a level-1 waiter may only open a tab they are serving. But
    GET /tabs/<tab_id> used to have NO role check and NO ownership check at all,
    and returned the same charges + payments — plus the order lines, the payment
    METHOD and who took it. The restriction on /receipts/<id> was therefore
    decorative: the tab_id is handed out by /tabs, /bookings and /tabs/by-room,
    and the unguarded door stood right beside the guarded one.

    Both doors now apply the same rule: front desk and above may open any tab;
    below that, only a tab assigned to you or opened by you.
    """
    _, tab_id = stay(client, manager_token, villa.id, name="Wanjiru Kamau")

    # The folio door.
    denied = client.get(f"/receipts/{tab_id}", headers=auth(waiter_token))
    assert denied.status_code == 403
    assert "only open a bill for a table you are serving" in denied.get_json()["error"]

    # The door beside it, which used to be open.
    rv = client.get(f"/tabs/{tab_id}", headers=auth(waiter_token))
    assert rv.status_code == 403
    assert "only open a table you are serving" in rv.get_json()["error"]

    # Front desk and above still get the whole tab — settling accounts is the job.
    body = client.get(f"/tabs/{tab_id}", headers=auth(manager_token)).get_json()
    assert body["reference"] == "Villa 6 / Wanjiru Kamau"
    assert any(c["description"].startswith("Accommodation —") for c in body["charges"])
    assert Decimal(body["balance"]) == Decimal("14000")

    # NOTE (lesser, still open): GET /tabs itself has no role filter unless you
    # ask for mine=true, so a waiter can still SEE that the villa tab exists and
    # read its reference. Only the money behind it is now shut off.
    listing = client.get("/tabs", headers=auth(waiter_token)).get_json()
    assert [t for t in listing if t["id"] == tab_id][0]["reference"] == "Villa 6 / Wanjiru Kamau"


def test_HOLE_feedback_accepts_a_booking_id_that_does_not_exist(client, manager_token):
    """HOLE — app/feedback/core.py:64-72 passes booking_id / event_id /
    department_id / served_by_employee_id straight into the row with no lookup.
    GuestFeedback.booking_id is a real FK and PRAGMA foreign_keys is ON
    (app/__init__.py:74), so a typo'd id is an IntegrityError → 500, not a 400.

    served_by_employee_id is the one that bites: it feeds an employee's
    performance guest_rating, so it must be validated, not trusted.
    """
    from sqlalchemy.exc import IntegrityError
    from app.extensions import db
    with pytest.raises(IntegrityError):
        client.post("/feedback", json={"score": 5, "booking_id": str(uuid.uuid4())},
                    headers=auth(manager_token))
    db.session.rollback()
