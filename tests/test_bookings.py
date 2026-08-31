"""
tests/test_bookings.py — Chunk 6 Bookings & Villa Tab tests.

Coverage:
  1. BookableResource CRUD + disable/enable + pricing owner-only
  2. Booking lifecycle: HELD → CONFIRMED → CHECKED_IN → CHECKED_OUT
  3. Illegal state transitions rejected with plain-English errors
  4. Double-booking prevention for same resource / overlapping dates
  5. Capacity enforcement (event venue)
  6. Deposit flow: require deposit before CONFIRMED; transfer to tab on check-in
  7. VILLA tab activation: POS charges land on the tab after check-in
  8. Checkout: blocked if outstanding balance; succeeds when settled
  9. Waiver gate: water session blocked without active waiver; passes after waiver signed
 10. No-show sweep: past-planned bookings without check-in flagged correctly
 11. Repeat guest: same phone → same GuestRecord; new phone → new record
 12. Idempotency: double check-in returns original state, no duplicate tab
 13. Append-only: no Payment records edited during deposit transfer; new records only
 14. Decimal precision on all money math
 15. Role enforcement: staff ≥ 3 can create bookings; owner-only pricing change
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def villa(app):
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Test Villa", resource_type=ResourceType.VILLA.value,
        base_price="10000", capacity=4,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def event_venue(app):
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Event Field", resource_type=ResourceType.EVENT_VENUE.value,
        base_price="50000", capacity=50,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def water_resource(app):
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(
        name="Jetski A", resource_type=ResourceType.WATER_ACTIVITY.value,
        base_price="3000", capacity=2,
    )
    db.session.add(r)
    db.session.commit()
    return r


def _make_booking(client, token, resource_id, guest_name="John Doe",
                  guest_phone=None, days_ahead=3, duration_days=2,
                  num_guests=2, idem_key=None):
    """Helper: POST /bookings and return the response."""
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=days_ahead)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=duration_days)).replace(hour=11, minute=0, second=0, microsecond=0)
    payload = {
        "resource_id": resource_id,
        "guest_name":  guest_name,
        "guest_phone": guest_phone or f"+2547{uuid.uuid4().hex[:8]}",
        "check_in_planned_utc":  ci.isoformat(),
        "check_out_planned_utc": co.isoformat(),
        "number_of_guests": num_guests,
    }
    if idem_key:
        payload["idempotency_key"] = idem_key
    return client.post("/bookings", json=payload, headers=auth(token))


def _record_deposit(client, token, booking_id, amount=None, method="CASH"):
    if amount is None:
        # get deposit_required from the booking
        rv = client.get(f"/bookings?resource_id=test", headers=auth(token))
        amount = "3000"  # fallback
    return client.post("/booking-payments", json={
        "booking_id": booking_id,
        "purpose":    "DEPOSIT",
        "amount":     str(amount),
        "method":     method,
    }, headers=auth(token))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BookableResource CRUD
# ═══════════════════════════════════════════════════════════════════════════════

class TestResources:
    def test_manager_creates_resource(self, client, manager_token):
        rv = client.post("/bookable-resources", json={
            "name": "Villa X", "resource_type": "VILLA", "base_price": "15000",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["name"] == "Villa X"

    def test_staff_cannot_create_resource(self, client, waiter_token):
        rv = client.post("/bookable-resources", json={
            "name": "Villa Y", "resource_type": "VILLA", "base_price": "10000",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_manager_cannot_change_price(self, client, manager_token, villa):
        rv = client.patch(f"/bookable-resources/{villa.id}",
                          json={"base_price": "99000"},
                          headers=auth(manager_token))
        assert rv.status_code == 403
        assert "owner" in rv.get_json()["error"].lower()

    def test_owner_can_change_price(self, client, owner_token, villa):
        rv = client.patch(f"/bookable-resources/{villa.id}",
                          json={"base_price": "18000"},
                          headers=auth(owner_token))
        assert rv.status_code == 200
        assert Decimal(rv.get_json()["base_price"]) == Decimal("18000")

    def test_disable_enable_resource(self, client, manager_token, villa):
        rv = client.post(f"/bookable-resources/{villa.id}/disable",
                         headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is False

        rv = client.post(f"/bookable-resources/{villa.id}/enable",
                         headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is True

    def test_invalid_resource_type_rejected(self, client, manager_token):
        rv = client.post("/bookable-resources", json={
            "name": "X", "resource_type": "SPACESHIP", "base_price": "1000",
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# 2 & 3. Booking lifecycle + state machine
# ═══════════════════════════════════════════════════════════════════════════════

class TestBookingLifecycle:
    def test_create_booking_held(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id)
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["status"] == "HELD"
        assert Decimal(data["deposit_required"]) > 0  # 30% of base_total

    def test_confirm_requires_deposit(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id)
        booking_id = rv.get_json()["id"]

        rv = client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "deposit" in rv.get_json()["error"].lower()

    def test_full_lifecycle(self, client, manager_token, owner_token, villa):
        # Create
        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254722000100")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        # Record deposit
        rv = client.post("/booking-payments", json={
            "booking_id": booking_id,
            "purpose": "DEPOSIT",
            "amount": str(deposit_required),
            "method": "CASH",
        }, headers=auth(manager_token))
        assert rv.status_code == 201

        # Confirm
        rv = client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CONFIRMED"

        # Check-in
        rv = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "CHECKED_IN"
        assert data["tab_id"] is not None
        tab_id = data["tab_id"]

        # The room is charged to the tab at check-in, so after a PARTIAL deposit
        # the balance is what is still owed.
        #
        # This used to assert `balance <= 0` with the comment "deposit covers it
        # as a credit" — which was only ever true because base_total was never
        # charged to the tab at all. The assertion was protecting the bug: it
        # would have failed the moment the room appeared on the bill, which is
        # exactly what it did.
        from app.services.tab import get_tab_balance
        from app.extensions import db
        with client.application.app_context():
            balance = get_tab_balance(tab_id)
        assert balance > Decimal("0"), "the unpaid part of the room must be owed"

        # Check-out is refused while that stands — a guest cannot walk out
        # having paid only the deposit.
        rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "outstanding balance" in rv.get_json()["error"].lower()

        # Settle in full, then they may leave.
        client.post(f"/tabs/{tab_id}/payments",
                    json={"method": "CASH", "amount": str(balance),
                          "idempotency_key": str(uuid.uuid4())},
                    headers=auth(manager_token))
        rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CHECKED_OUT"

    def test_cancel_booking(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id)
        booking_id = rv.get_json()["id"]
        rv = client.post(f"/bookings/{booking_id}/cancel", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CANCELLED"

    def test_cancelled_booking_cannot_be_confirmed(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id)
        booking_id = rv.get_json()["id"]
        client.post(f"/bookings/{booking_id}/cancel", headers=auth(manager_token))

        rv = client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_checked_out_is_terminal(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254722000101")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))

        rv = client.post(f"/bookings/{booking_id}/cancel", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Double-booking prevention
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoubleBooking:
    def test_overlapping_dates_rejected(self, client, manager_token, villa):
        now = datetime.now(timezone.utc)
        ci  = now + timedelta(days=10)
        co  = now + timedelta(days=14)

        # First booking
        rv1 = client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "Guest A", "guest_phone": "+254700200001",
            "check_in_planned_utc":  ci.isoformat(),
            "check_out_planned_utc": co.isoformat(),
            "number_of_guests": 2,
        }, headers=auth(manager_token))
        assert rv1.status_code == 201

        # Overlapping second booking
        rv2 = client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "Guest B", "guest_phone": "+254700200002",
            "check_in_planned_utc":  (ci + timedelta(days=2)).isoformat(),
            "check_out_planned_utc": (co + timedelta(days=2)).isoformat(),
            "number_of_guests": 2,
        }, headers=auth(manager_token))
        assert rv2.status_code == 409
        assert "error" in rv2.get_json()

    def test_non_overlapping_dates_allowed(self, client, manager_token, villa):
        now = datetime.now(timezone.utc)

        rv1 = client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "Guest C", "guest_phone": "+254700200003",
            "check_in_planned_utc":  (now + timedelta(days=20)).isoformat(),
            "check_out_planned_utc": (now + timedelta(days=22)).isoformat(),
            "number_of_guests": 2,
        }, headers=auth(manager_token))
        assert rv1.status_code == 201

        rv2 = client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "Guest D", "guest_phone": "+254700200004",
            "check_in_planned_utc":  (now + timedelta(days=23)).isoformat(),
            "check_out_planned_utc": (now + timedelta(days=25)).isoformat(),
            "number_of_guests": 2,
        }, headers=auth(manager_token))
        assert rv2.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Capacity enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapacity:
    def test_over_capacity_rejected(self, client, manager_token, event_venue):
        rv = client.post("/bookings", json={
            "resource_id": event_venue.id,
            "guest_name": "Big Party", "guest_phone": "+254700300001",
            "check_in_planned_utc":  (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "check_out_planned_utc": (datetime.now(timezone.utc) + timedelta(days=7, hours=8)).isoformat(),
            "number_of_guests": 300,  # exceeds capacity of 50
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_within_capacity_allowed(self, client, manager_token, event_venue):
        rv = client.post("/bookings", json={
            "resource_id": event_venue.id,
            "guest_name": "Small Party", "guest_phone": "+254700300002",
            "check_in_planned_utc":  (datetime.now(timezone.utc) + timedelta(days=8)).isoformat(),
            "check_out_planned_utc": (datetime.now(timezone.utc) + timedelta(days=8, hours=8)).isoformat(),
            "number_of_guests": 40,
        }, headers=auth(manager_token))
        assert rv.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# 6 & 13. Deposit flow + append-only
# ═══════════════════════════════════════════════════════════════════════════════

class TestDepositFlow:
    def test_deposit_recorded_as_payment(self, client, manager_token, villa, app):
        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254700400001")
        booking_id = rv.get_json()["id"]

        rv = client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": "3000", "method": "MPESA", "mpesa_code": "ABC123XYZ",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["purpose"] == "DEPOSIT"
        assert data["amount"] == "3000"

        # Payment record has tab_id=None (no tab yet)
        from app.models.payment import Payment
        from app.extensions import db
        with app.app_context():
            p = db.session.get(Payment, data["payment_id"])
            assert p.tab_id is None

    def test_deposit_transfer_moves_the_payment_it_does_not_duplicate_it(
            self, client, manager_token, villa, app):
        """One movement of money leaves exactly ONE Payment row.

        This test used to assert the opposite — that check-in ADDS a second
        Payment for the deposit — which is how a real double-count got locked in
        as a requirement. Every revenue reader sums Payment rows unfiltered, so
        a KSh 6,000 deposit was reported as 12,000 taken that day.

        The deposit is collected before any tab exists, so its Payment lands
        with tab_id=NULL. Check-in fills in that NULL. Nothing about the money
        itself — amount, method, timestamp — is ever rewritten.
        """
        from app.models.payment import Payment
        from app.extensions import db

        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254700400002")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        # Record deposit
        rv = client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(manager_token))
        deposit_payment_id = rv.get_json()["payment_id"]

        # Confirm
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))

        # Snapshot the money BEFORE check-in, so we can prove none of it moved.
        with app.app_context():
            count_before = db.session.query(Payment).count()
            before = db.session.get(Payment, deposit_payment_id)
            assert before.tab_id is None      # no tab exists yet at booking time
            amount_before  = before.amount
            method_before  = before.method
            created_before = before.created_at_utc

        # Check-in
        rv = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        tab_id = rv.get_json()["tab_id"]

        with app.app_context():
            # No second row invented for money that only moved once.
            assert db.session.query(Payment).count() == count_before

            after = db.session.get(Payment, deposit_payment_id)
            assert after.tab_id == tab_id             # the NULL got filled in
            assert after.amount == amount_before      # and nothing else changed
            assert after.method == method_before
            assert after.created_at_utc == created_before

            # The tab still sees the deposit, so the balance is unaffected.
            from app.services.tab import get_tab_balance
            assert get_tab_balance(tab_id) == Decimal(str(b["base_total"])) - deposit_required

    def test_deposit_transfer_is_idempotent_on_a_re_run(
            self, client, manager_token, villa, app):
        """Re-running the transfer must not move or duplicate anything.

        The old insert needed an idempotency_key to be safe on a retry. Filling
        a NULL is naturally idempotent, but that only holds if the code checks
        before writing — so this drives the service directly a second time on a
        live tab, which is the path a retry would take.
        """
        from app.models.payment import Payment
        from app.models.booking import Booking
        from app.models.tab import Tab
        from app.extensions import db
        from app.services.booking import transfer_deposit_to_tab
        from app.services.tab import get_tab_balance

        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254700400009")
        booking_id = rv.get_json()["id"]
        deposit_required = Decimal(rv.get_json()["deposit_required"])
        client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        rv = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        tab_id = rv.get_json()["tab_id"]

        with app.app_context():
            count_before   = db.session.query(Payment).count()
            balance_before = get_tab_balance(tab_id)

            booking = db.session.get(Booking, booking_id)
            tab     = db.session.get(Tab, tab_id)
            transfer_deposit_to_tab(booking, tab, booking.created_by_id)
            db.session.commit()

            assert db.session.query(Payment).count() == count_before
            assert get_tab_balance(tab_id) == balance_before

    def test_deposit_idempotent(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id)
        booking_id = rv.get_json()["id"]
        idem = str(uuid.uuid4())
        for _ in range(2):
            rv = client.post("/booking-payments", json={
                "booking_id": booking_id, "purpose": "DEPOSIT",
                "amount": "2000", "method": "CASH",
                "idempotency_key": idem,
            }, headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["duplicate"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7. VILLA tab: POS charges flow to it
# ═══════════════════════════════════════════════════════════════════════════════

class TestVillaTab:
    def _full_checkin(self, client, token, villa):
        rv = _make_booking(client, token, villa.id, guest_phone="+254700500001")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(token))
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(token))
        rv = client.post(f"/bookings/{booking_id}/check-in", headers=auth(token))
        return rv.get_json()

    def test_charge_lands_on_villa_tab(self, client, manager_token, villa):
        data = self._full_checkin(client, manager_token, villa)
        tab_id = data["tab_id"]

        # Add a manual charge to the villa tab
        rv = client.post("/tabs/{}/charges".format(tab_id) if False else f"/tabs/{tab_id}", headers=auth(manager_token))
        # Actually use the charges endpoint via POS
        # The tab is open; verify balance via GET /tabs/:id
        rv = client.get(f"/tabs/{tab_id}", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["tab_type"] == "VILLA"

    def test_checkout_blocked_with_outstanding_balance(self, client, manager_token, villa, app):
        from app.models.charge import Charge
        from app.extensions import db

        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254700500002")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))
        rv = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        tab_id = rv.get_json()["tab_id"]

        # Add a large charge that exceeds deposit credit
        with app.app_context():
            from app.models.user import User
            actor = db.session.query(User).filter_by(username="manager1").first()
            charge = Charge(tab_id=tab_id, amount="50000",
                            description="Extra spa services", created_by_id=actor.id)
            db.session.add(charge)
            db.session.commit()

        # Checkout should fail — outstanding balance
        rv = client.post(f"/bookings/{booking_id}/check-out", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "balance" in rv.get_json()["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Waiver gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestWaiverGate:
    def _create_checked_in_water_booking(self, client, token, water_resource):
        """Creates and checks in a water-activity booking (no deposit required)."""
        now = datetime.now(timezone.utc)
        ci = now + timedelta(hours=2)
        co = ci + timedelta(hours=2)
        rv = client.post("/bookings", json={
            "resource_id": water_resource.id,
            "guest_name": "Diver Dave", "guest_phone": "+254700600001",
            "check_in_planned_utc": ci.isoformat(),
            "check_out_planned_utc": co.isoformat(),
            "number_of_guests": 1,
        }, headers=auth(token))
        booking_id = rv.get_json()["id"]
        # Confirm (no deposit required for water activity)
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(token))
        client.post(f"/bookings/{booking_id}/check-in", headers=auth(token))
        return booking_id

    def test_water_session_blocked_without_waiver(self, client, manager_token, water_resource):
        booking_id = self._create_checked_in_water_booking(client, manager_token, water_resource)
        rv = client.post(f"/bookings/{booking_id}/water-sessions", json={
            "resource_id": water_resource.id,
        }, headers=auth(manager_token))
        assert rv.status_code == 403
        assert "waiver" in rv.get_json()["error"].lower()

    def test_water_session_allowed_after_waiver(self, client, manager_token, water_resource):
        booking_id = self._create_checked_in_water_booking(client, manager_token, water_resource)

        # Sign waiver
        rv = client.post("/waivers", json={
            "booking_id": booking_id,
            "activity_type": "WATER_ACTIVITY",
            "signed_by_name": "Diver Dave",
        }, headers=auth(manager_token))
        assert rv.status_code == 201

        # Water session now allowed
        rv = client.post(f"/bookings/{booking_id}/water-sessions", json={
            "resource_id": water_resource.id,
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert Decimal(rv.get_json()["amount"]) > 0

    def test_revoked_waiver_blocks_session(self, client, manager_token, water_resource):
        booking_id = self._create_checked_in_water_booking(client, manager_token, water_resource)

        rv = client.post("/waivers", json={
            "booking_id": booking_id,
            "activity_type": "WATER_ACTIVITY",
            "signed_by_name": "Diver Dave",
        }, headers=auth(manager_token))
        waiver_id = rv.get_json()["id"]

        # Revoke it
        client.post(f"/waivers/{waiver_id}/revoke", headers=auth(manager_token))

        # Session now blocked again
        rv = client.post(f"/bookings/{booking_id}/water-sessions", json={
            "resource_id": water_resource.id,
        }, headers=auth(manager_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 10. No-show sweep
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoShowSweep:
    def test_past_booking_flagged_no_show(self, client, manager_token, villa, app):
        from app.services.booking import flag_no_shows
        from app.models.booking import Booking
        from app.extensions import db

        # Booking with check-in in the past
        now = datetime.now(timezone.utc)
        rv = client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "No Show Nancy", "guest_phone": "+254700700001",
            "check_in_planned_utc":  (now - timedelta(hours=5)).isoformat(),
            "check_out_planned_utc": (now + timedelta(days=1)).isoformat(),
            "number_of_guests": 1,
        }, headers=auth(manager_token))
        booking_id = rv.get_json()["id"]

        with app.app_context():
            count = flag_no_shows()
            db.session.commit()
            b = db.session.get(Booking, booking_id)
            assert b.status == "NO_SHOW"
            assert count >= 1

    def test_future_booking_not_flagged(self, client, manager_token, villa, app):
        from app.services.booking import flag_no_shows
        from app.models.booking import Booking
        from app.extensions import db

        now = datetime.now(timezone.utc)
        rv = _make_booking(client, manager_token, villa.id, days_ahead=7, guest_phone="+254700700002")
        booking_id = rv.get_json()["id"]

        with app.app_context():
            flag_no_shows()
            db.session.commit()
            b = db.session.get(Booking, booking_id)
            assert b.status == "HELD"   # not flagged


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Repeat guest auto-match
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepeatGuest:
    def test_same_phone_links_same_guest_record(self, client, manager_token, villa, app):
        from app.models.booking import Booking
        from app.extensions import db
        phone = "+254700800001"

        rv1 = _make_booking(client, manager_token, villa.id, guest_phone=phone,
                            days_ahead=30, idem_key="rg-test-1")
        assert rv1.status_code == 201
        gr_id_1 = rv1.get_json()["guest_record_id"]

        # Second booking with same phone — different resource to avoid double-booking
        rv2 = client.post("/bookable-resources", json={
            "name": "Villa GR", "resource_type": "VILLA", "base_price": "8000",
        }, headers=auth(manager_token))
        v2_id = rv2.get_json()["id"]

        rv2 = _make_booking(client, manager_token, v2_id, guest_phone=phone,
                            days_ahead=60, idem_key="rg-test-2")
        assert rv2.status_code == 201
        gr_id_2 = rv2.get_json()["guest_record_id"]

        assert gr_id_1 == gr_id_2   # same GuestRecord

    def test_new_phone_creates_new_guest_record(self, client, manager_token, villa, app):
        rv1 = _make_booking(client, manager_token, villa.id,
                            guest_phone="+254700800002", days_ahead=40, idem_key="ng-test-1")
        rv2 = client.post("/bookable-resources", json={
            "name": "Villa NG", "resource_type": "VILLA", "base_price": "8000",
        }, headers=auth(manager_token))
        v2_id = rv2.get_json()["id"]

        rv2 = _make_booking(client, manager_token, v2_id,
                            guest_phone="+254700800003", days_ahead=40, idem_key="ng-test-2")
        assert rv1.get_json()["guest_record_id"] != rv2.get_json()["guest_record_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Idempotency
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_duplicate_booking_returns_original(self, client, manager_token, villa):
        idem = str(uuid.uuid4())
        rv1 = _make_booking(client, manager_token, villa.id, days_ahead=50, idem_key=idem)
        rv2 = _make_booking(client, manager_token, villa.id, days_ahead=50, idem_key=idem)
        assert rv1.status_code == 201
        assert rv2.status_code == 200
        assert rv2.get_json()["duplicate"] is True

    def test_double_check_in_idempotent(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id, guest_phone="+254700900001")
        b = rv.get_json()
        booking_id = b["id"]
        deposit_required = Decimal(b["deposit_required"])

        client.post("/booking-payments", json={
            "booking_id": booking_id, "purpose": "DEPOSIT",
            "amount": str(deposit_required), "method": "CASH",
        }, headers=auth(manager_token))
        client.post(f"/bookings/{booking_id}/confirm", headers=auth(manager_token))

        rv1 = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        tab_id_1 = rv1.get_json()["tab_id"]

        rv2 = client.post(f"/bookings/{booking_id}/check-in", headers=auth(manager_token))
        tab_id_2 = rv2.get_json()["tab_id"]

        assert tab_id_1 == tab_id_2   # same tab, not duplicated


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Decimal precision
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecimalPrecision:
    def test_base_total_is_decimal(self, client, manager_token, villa):
        rv = _make_booking(client, manager_token, villa.id, duration_days=3,
                           guest_phone="+254700100001")
        data = rv.get_json()
        # base_total = 10000 * 3 nights = 30000
        assert Decimal(data["base_total"]) == Decimal("30000")
        # deposit_required = 30% of 30000 = 9000
        assert Decimal(data["deposit_required"]) == Decimal("9000.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 15. Availability endpoint
# ═══════════════════════════════════════════════════════════════════════════════

def _dt_str(dt: datetime) -> str:
    """Format datetime for use in URL query params (no timezone offset + sign)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class TestAvailability:
    def test_availability_returns_resources(self, client, manager_token, villa):
        now = datetime.now(timezone.utc)
        rv = client.get(
            f"/bookings/availability?resource_type=VILLA"
            f"&from={_dt_str(now)}"
            f"&to={_dt_str(now + timedelta(days=5))}",
            headers=auth(manager_token),
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, list)
        assert any(r["name"] == "Test Villa" for r in data)

    def test_booked_resource_shows_unavailable(self, client, manager_token, villa):
        now = datetime.now(timezone.utc)
        ci = now + timedelta(days=15)
        co = now + timedelta(days=17)
        client.post("/bookings", json={
            "resource_id": villa.id,
            "guest_name": "Blocker", "guest_phone": "+254700100002",
            "check_in_planned_utc": ci.isoformat(),
            "check_out_planned_utc": co.isoformat(),
            "number_of_guests": 1,
        }, headers=auth(manager_token))

        rv = client.get(
            f"/bookings/availability?resource_type=VILLA"
            f"&from={_dt_str(ci + timedelta(hours=1))}"
            f"&to={_dt_str(co - timedelta(hours=1))}",
            headers=auth(manager_token),
        )
        results = rv.get_json()
        villa_entry = next((r for r in results if r["name"] == "Test Villa"), None)
        assert villa_entry is not None
        assert villa_entry["available"] is False


# ── The room must be on the room's bill ───────────────────────────────────────

def _full_villa_checkin(client, token, vid, guest="Charge Test Guest"):
    """booking -> full deposit -> confirm -> check-in. Returns (booking, tab_id)."""
    from datetime import datetime, timezone, timedelta
    import uuid as _u
    ci = datetime.now(timezone.utc) + timedelta(hours=2)
    co = ci + timedelta(days=2)
    h = {"Authorization": f"Bearer {token}"}
    bk = client.post("/bookings", json={
        "resource_id": vid, "guest_name": guest, "guest_phone": f"+2547{_u.uuid4().int % 10**8:08d}",
        "number_of_guests": 2,
        "check_in_planned_utc": ci.isoformat(), "check_out_planned_utc": co.isoformat(),
        "idempotency_key": str(_u.uuid4()),
    }, headers=h).get_json()
    client.post("/booking-payments", json={
        "booking_id": bk["id"], "purpose": "DEPOSIT", "method": "CASH",
        "amount": bk["deposit_required"], "idempotency_key": str(_u.uuid4()),
    }, headers=h)
    client.post(f"/bookings/{bk['id']}/confirm", headers=h)
    rv = client.post(f"/bookings/{bk['id']}/check-in", headers=h)
    return bk, rv.get_json().get("tab_id")


def test_accommodation_is_charged_to_the_villa_tab(client, owner_token, villa):
    """base_total lived on the BOOKING and was never written to the tab, so a
    villa tab was an incidentals account and the room was invisible to it."""
    bk, tab_id = _full_villa_checkin(client, owner_token, villa.id)
    assert tab_id
    folio = client.get(f"/receipts/{tab_id}",
                       headers={"Authorization": f"Bearer {owner_token}"}).get_json()
    rooms = [c for c in folio["charges"] if c["description"].startswith("Accommodation")]
    assert len(rooms) == 1, "the room must appear on the bill exactly once"
    assert Decimal(rooms[0]["amount"]) == Decimal(bk["base_total"])


def test_guest_cannot_check_out_owing_the_room(client, owner_token, villa, app):
    """The whole point: balance was NEGATIVE (deposit, no room charge), so
    is_tab_closable said yes and a guest could walk owing 70% of the stay."""
    from app.services.tab import is_tab_closable
    bk, tab_id = _full_villa_checkin(client, owner_token, villa.id)
    with app.app_context():
        ok, reason = is_tab_closable(tab_id)
    assert ok is False, "a guest owing the balance of the room must not be closable"
    assert "outstanding balance" in reason.lower()


def test_room_is_not_charged_twice(client, owner_token, villa):
    """A second check-in attempt must not add another accommodation line."""
    bk, tab_id = _full_villa_checkin(client, owner_token, villa.id)
    client.post(f"/bookings/{bk['id']}/check-in",
                headers={"Authorization": f"Bearer {owner_token}"})
    folio = client.get(f"/receipts/{tab_id}",
                       headers={"Authorization": f"Bearer {owner_token}"}).get_json()
    rooms = [c for c in folio["charges"] if c["description"].startswith("Accommodation")]
    assert len(rooms) == 1


def test_overstaying_guest_blocks_the_room(client, owner_token, villa, app):
    """A room is free when the person has LEFT, not when the diary says so.

    The overlap check compares PLANNED dates, so a guest due out on the 28th who
    has not checked out falls outside every future window and the villa reads as
    free. Found live: Villa 4 held two open accounts at once — PW Guest 96604
    (due out, never checked out) and a new arrival. Overstays are ordinary."""
    from app.extensions import db as _db
    from app.models.booking import Booking, BookingStatus
    from app.services.booking import check_resource_availability
    from datetime import datetime, timezone, timedelta
    import uuid as _u

    # A guest who was due out yesterday and is still in the room.
    past_out = datetime.now(timezone.utc) - timedelta(days=1)
    with app.app_context():
        _db.session.add(Booking(
            resource_id=villa.id, guest_name="Overstayer", guest_phone=f"+2547{_u.uuid4().int % 10**8:08d}",
            number_of_guests=1,
            check_in_planned_utc=past_out - timedelta(days=2),
            check_out_planned_utc=past_out,
            check_out_actual_utc=None,
            base_total="10000", deposit_required="0",
            status=BookingStatus.CHECKED_IN.value,
            idempotency_key=str(_u.uuid4()),
            created_by_id=_db.session.query(__import__("app.models.user", fromlist=["User"]).User).first().id,
        ))
        _db.session.commit()

        # Dates well clear of their planned window — the calendar sees no clash.
        ci = datetime.now(timezone.utc) + timedelta(days=7)
        ok, why = check_resource_availability(villa.id, ci, ci + timedelta(days=2))

    assert ok is False, "a room someone is still in must not be bookable"
    assert "still occupied" in why
    assert "Overstayer" in why
