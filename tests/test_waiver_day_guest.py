"""
Waivers for the day guest — the person on the water who never booked a villa.

The waiver gate existed only on book_water_session(booking_id), and
Waiver.booking_id was the only link a waiver had. So the wristband POS — the
till that actually sells jet skis — never asked for one, and a day visitor
could not have signed even if it had: there was no booking to hang it on.

These cover the whole path: refuse the sale, let the person AT the post record
the waiver against the wristband, then allow the sale.
"""
import uuid
import pytest
from decimal import Decimal

from app.extensions import db


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def water_lead_token(client, app):
    """Francis at the jet ski: level 2, Water Activities. Below front desk."""
    from app.models.user import User
    from app.models.role import Role
    from app.models.department import Department
    from app.models.employee_profile import EmployeeProfile
    from app.models.clock_event import ClockEvent, ClockEventType
    from datetime import datetime, timezone

    role = db.session.query(Role).filter(Role.level == 2).first()
    if role is None:
        role = Role(name="water_lead", level=2)
        db.session.add(role)
        db.session.flush()

    dept = db.session.query(Department).filter(
        Department.name.ilike("%water%")).first()
    if dept is None:
        dept = Department(name="Water Activities")
        db.session.add(dept)
        db.session.flush()

    u = User(username="water.test", role_id=role.id, department_id=dept.id, is_active=True)
    u.set_password("WaterPass1!")
    db.session.add(u)
    db.session.flush()

    profile = EmployeeProfile(user_id=u.id, full_name="Water Test", phone="+254700009911")
    db.session.add(profile)
    db.session.flush()
    db.session.add(ClockEvent(
        employee_id=profile.id, event_type=ClockEventType.CLOCK_IN.value,
        occurred_at_utc=datetime.now(timezone.utc), idempotency_key=str(uuid.uuid4()),
    ))
    db.session.commit()

    rv = client.post("/auth/login", json={"username": "water.test", "password": "WaterPass1!"})
    return rv.get_json()["access_token"]


def _water_dept():
    from app.models.department import Department
    dept = db.session.query(Department).filter(
        Department.name.ilike("%water%")).first()
    if dept is None:
        dept = Department(name="Water Activities")
        db.session.add(dept)
        db.session.flush()
    return dept


def _activity_item(name, category):
    """A sellable activity. SERVICE because a ride consumes no stock — and an
    UNTRACKED item is refused before the waiver rule is ever reached."""
    from app.models.menu_item import MenuItem, StockTracking
    item = MenuItem(name=name, price=Decimal("3500.00"), category=category,
                    department_id=_water_dept().id, is_active=True,
                    stock_tracking=StockTracking.SERVICE.value)
    db.session.add(item)
    db.session.commit()
    return item.id


@pytest.fixture
def jet_ski_item(app):
    """A menu item in the category the gate keys on."""
    return _activity_item("Jet Ski Ride (test)", "Water Activities")


@pytest.fixture
def nature_trail_item(app):
    """Same department, different category — must NOT be gated."""
    return _activity_item("Nature Trail (test)", "Activities")


def _issue_band(client, token):
    rv = client.post("/gate/issue-band",
                     json={"method": "CASH", "idempotency_key": str(uuid.uuid4())},
                     headers=auth(token))
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()


# ── the gate ────────────────────────────────────────────────────────────────

def test_water_activity_refused_without_a_waiver(client, manager_token, jet_ski_item):
    """The sale itself is refused, not just the villa booking flow."""
    band = _issue_band(client, manager_token)

    rv = client.post("/orders", json={
        "tab_id": band["tab_id"],
        "items": [{"menu_item_id": jet_ski_item, "quantity": 1}],
    }, headers=auth(manager_token))

    assert rv.status_code == 403, rv.get_json()
    assert "waiver" in rv.get_json()["error"].lower()


def test_the_same_department_without_the_category_is_not_gated(
        client, manager_token, nature_trail_item):
    """
    The rule keys on the item's CATEGORY. A hike sold by the same post as the
    jet skis does not need a water waiver, and gating by department would have
    stopped it.
    """
    band = _issue_band(client, manager_token)

    rv = client.post("/orders", json={
        "tab_id": band["tab_id"],
        "items": [{"menu_item_id": nature_trail_item, "quantity": 1}],
    }, headers=auth(manager_token))

    assert rv.status_code == 201, rv.get_json()


# ── recording it ────────────────────────────────────────────────────────────

def test_the_person_at_the_post_can_record_the_waiver(
        client, manager_token, water_lead_token):
    """
    The water lead is level 2 and the endpoint wanted front desk (3). That made
    the gate above a dead end: he could not sell the ride, and could not record
    the thing that would let him.
    """
    band = _issue_band(client, manager_token)

    rv = client.post("/waivers", json={
        "band_number": band["band_number"],
        "activity_type": "WATER_ACTIVITY",
        "signed_by_name": "Day Guest Dan",
    }, headers=auth(water_lead_token))

    assert rv.status_code == 201, rv.get_json()
    body = rv.get_json()
    assert body["booking_id"] is None
    assert body["tab_id"] == band["tab_id"]


def test_waiver_needs_a_booking_or_a_band_but_not_both(client, manager_token):
    band = _issue_band(client, manager_token)

    both = client.post("/waivers", json={
        "band_number": band["band_number"], "booking_id": str(uuid.uuid4()),
        "activity_type": "WATER_ACTIVITY", "signed_by_name": "X",
    }, headers=auth(manager_token))
    assert both.status_code == 400

    neither = client.post("/waivers", json={
        "activity_type": "WATER_ACTIVITY", "signed_by_name": "X",
    }, headers=auth(manager_token))
    assert neither.status_code == 400


def test_waiver_for_a_band_that_is_not_out_there(client, manager_token):
    rv = client.post("/waivers", json={
        "band_number": 9999, "activity_type": "WATER_ACTIVITY",
        "signed_by_name": "Ghost",
    }, headers=auth(manager_token))
    assert rv.status_code == 404
    assert "9999" in rv.get_json()["error"]


# ── the whole path ──────────────────────────────────────────────────────────

def test_sale_goes_through_once_the_waiver_is_on_the_record(
        client, manager_token, water_lead_token, jet_ski_item):
    band = _issue_band(client, manager_token)

    refused = client.post("/orders", json={
        "tab_id": band["tab_id"],
        "items": [{"menu_item_id": jet_ski_item, "quantity": 1}],
    }, headers=auth(manager_token))
    assert refused.status_code == 403

    signed = client.post("/waivers", json={
        "band_number": band["band_number"],
        "activity_type": "WATER_ACTIVITY",
        "signed_by_name": "Day Guest Dan",
    }, headers=auth(water_lead_token))
    assert signed.status_code == 201

    allowed = client.post("/orders", json={
        "tab_id": band["tab_id"],
        "items": [{"menu_item_id": jet_ski_item, "quantity": 1}],
    }, headers=auth(manager_token))
    assert allowed.status_code == 201, allowed.get_json()


def test_one_guests_waiver_does_not_cover_another(
        client, manager_token, water_lead_token, jet_ski_item):
    """
    The waiver hangs off the wristband, so it must not leak sideways. Two
    guests, one signature: the second is still refused.
    """
    signed_band   = _issue_band(client, manager_token)
    unsigned_band = _issue_band(client, manager_token)

    client.post("/waivers", json={
        "band_number": signed_band["band_number"],
        "activity_type": "WATER_ACTIVITY", "signed_by_name": "Signed Sam",
    }, headers=auth(water_lead_token))

    rv = client.post("/orders", json={
        "tab_id": unsigned_band["tab_id"],
        "items": [{"menu_item_id": jet_ski_item, "quantity": 1}],
    }, headers=auth(manager_token))
    assert rv.status_code == 403, rv.get_json()
