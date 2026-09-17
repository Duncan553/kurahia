"""
tests/test_booking_dates.py — a guest stays longer, or leaves early.

Asked by Wachira, 17 Sep 2026, after watching Duncan's 3 nights charged once
at check-in: there was no way to add a night or take one off.

  - Front desk changes the leaving date.
  - Staying longer is refused if the villa is booked by someone else.
  - The nightly rate is the one the guest BOOKED at — a price change since
    does not reach an existing stay.
  - Checked in: the difference goes on the room bill as its own line.
    Not yet checked in: only the booking's total changes (the room is charged
    at check-in).
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest


def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def villa(app):
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(name="Villa 15", resource_type=ResourceType.VILLA.value,
                         base_price="10000", capacity=4)
    db.session.add(r)
    db.session.commit()
    return r


def _book(client, token, villa_id, nights=2, days_ahead=0, guest="Duncan"):
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=days_ahead)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=nights)).replace(hour=11)
    rv = client.post("/bookings", headers=H(token), json={
        "resource_id": villa_id, "guest_name": guest, "guest_phone": f"+2547{uuid.uuid4().hex[:8]}",
        "check_in_planned_utc": ci.isoformat(), "check_out_planned_utc": co.isoformat(),
        "number_of_guests": 2, "idempotency_key": str(uuid.uuid4())})
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()


def _check_in(client, token, booking):
    client.post("/booking-payments", headers=H(token), json={
        "booking_id": booking["id"], "purpose": "DEPOSIT",
        "amount": booking["deposit_required"], "method": "CASH"})
    client.post(f"/bookings/{booking['id']}/confirm", headers=H(token))
    rv = client.post(f"/bookings/{booking['id']}/check-in", headers=H(token))
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["tab_id"]


def _new_checkout(booking, nights):
    ci = datetime.fromisoformat(booking["check_in_planned"])
    ci = ci if ci.tzinfo else ci.replace(tzinfo=timezone.utc)
    return (ci + timedelta(days=nights)).replace(hour=11).isoformat()


def _change(client, token, booking, nights):
    return client.post(f"/bookings/{booking['id']}/change-dates", headers=H(token),
                       json={"check_out_planned_utc": _new_checkout(booking, nights)})


def _charges(client, token, tab_id):
    return client.get(f"/tabs/{tab_id}", headers=H(token)).get_json()["charges"]


class TestStayingLongerOrLeavingEarly:

    def test_before_check_in_only_the_bookings_total_changes(self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2, days_ahead=3)
        rv = _change(client, manager_token, b, nights=3)
        assert rv.status_code == 200, rv.get_json()
        assert (rv.get_json()["nights"], rv.get_json()["base_total"]) == (3, "30000.00")

    def test_a_checked_in_guest_staying_longer_is_charged_the_extra_night(
            self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2)
        tab = _check_in(client, manager_token, b)
        rv = _change(client, manager_token, b, nights=3)
        assert rv.status_code == 200, rv.get_json()
        lines = [(c["description"], c["amount"]) for c in _charges(client, manager_token, tab)]
        assert ("Accommodation — Villa 15, 2 nights", "20000.00") in lines
        assert ("Extra night — Villa 15, 1 night", "10000.00") in lines
        assert rv.get_json()["base_total"] == "30000.00"

    def test_a_guest_leaving_early_is_not_charged_for_nights_not_stayed(
            self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=3)
        tab = _check_in(client, manager_token, b)
        rv = _change(client, manager_token, b, nights=1)
        assert rv.status_code == 200, rv.get_json()
        lines = [(c["description"], c["amount"]) for c in _charges(client, manager_token, tab)]
        assert ("Nights not stayed — Villa 15, 2 nights", "-20000.00") in lines

    def test_the_rate_is_the_one_the_guest_booked_at(self, client, manager_token, villa):
        from app.extensions import db
        b = _book(client, manager_token, villa.id, nights=2)
        tab = _check_in(client, manager_token, b)
        villa.base_price = Decimal("99999")          # the owner raised the rate since
        db.session.commit()
        _change(client, manager_token, b, nights=3)
        assert ("Extra night — Villa 15, 1 night", "10000.00") in \
               [(c["description"], c["amount"]) for c in _charges(client, manager_token, tab)]

    def test_staying_longer_into_someone_elses_booking_is_refused(self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2)
        _book(client, manager_token, villa.id, nights=2, days_ahead=2, guest="Otieno")
        rv = _change(client, manager_token, b, nights=3)
        assert rv.status_code == 409
        assert "Villa 15" in rv.get_json()["error"]

    def test_a_stay_cannot_be_cut_to_nothing(self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2)
        rv = client.post(f"/bookings/{b['id']}/change-dates", headers=H(manager_token),
                         json={"check_out_planned_utc": b["check_in_planned"]})
        assert rv.status_code == 400

    def test_saving_the_same_date_changes_nothing(self, client, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2)
        tab = _check_in(client, manager_token, b)
        _change(client, manager_token, b, nights=2)
        assert len(_charges(client, manager_token, tab)) == 1

    def test_a_waiter_cannot_change_a_stay(self, client, waiter_token, manager_token, villa):
        b = _book(client, manager_token, villa.id, nights=2)
        assert _change(client, waiter_token, b, nights=3).status_code == 403
