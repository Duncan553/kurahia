"""
tests/test_events.py — Chunk 8 Events & Notifications tests.

Coverage:
  1.  Event lifecycle: PLANNED → CONFIRMED → IN_PROGRESS → COMPLETED; illegal moves rejected
  2.  Cancellation flips all QUEUED notifications to FAILED
  3.  Alert scheduling: confirming with 1 assigned employee creates exactly 5 notifications
  4.  Idempotent confirm: double-tap returns same state, notifications still only 4
  5.  Alive delivery: clocked-in recipient → IN_APP; off-shift with no phone gateway → waits in the inbox
  6.  Inbox: returns unread DELIVERED items; mark-as-read works; idempotent
  7.  Event inventory: allocation → issue writes EVENT_ALLOCATION movement
  8.  Judge exclusion: EVENT_ALLOCATION movement excluded from consumption ratios
  9.  Allocation → return restores stock; per-event reconciliation correct
 10.  Suggestion routing: OWNER_PRIVATE invisible to manager (query-layer filter)
 11.  Manager sees MANAGEMENT; owner sees both
 12.  Anonymous OWNER_PRIVATE allowed; anonymous MANAGEMENT rejected
 13.  Owner notified via Notification when OWNER_PRIVATE suggestion submitted
 14.  Role enforcement throughout
 15.  Plain-English errors
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def event_type(app):
    from app.models.event_type import EventType
    from app.extensions import db
    et = EventType(name="TEST_WEDDING")
    db.session.add(et)
    db.session.commit()
    return et


@pytest.fixture
def employee_profile(app):
    """EmployeeProfile for waiter1 — needed for assignments and notification delivery.
    Idempotent: waiter_token (conftest.py) may have already created this same
    row so require_clocked_in passes elsewhere in the same test."""
    from app.models.employee_profile import EmployeeProfile
    from app.models.user import User
    from app.extensions import db
    user = db.session.query(User).filter_by(username="waiter1").first()
    profile = db.session.query(EmployeeProfile).filter_by(user_id=user.id).first()
    if not profile:
        profile = EmployeeProfile(user_id=user.id, full_name="Test Waiter",
                                   phone="+254700000001")
        db.session.add(profile)
        db.session.commit()
    return profile


@pytest.fixture
def inventory_item(app):
    from app.models.inventory_item import InventoryItem
    from app.models.department import Department
    from app.extensions import db
    dept = db.session.query(Department).filter_by(name="General").first()
    item = InventoryItem(name="Event Wine", unit="bottle", reorder_level=Decimal("5"),
                         department_id=dept.id)
    db.session.add(item)
    db.session.commit()
    return item


def _make_event(client, token, event_type_id, days_ahead=14, idem=None, venue_id=None, **fields):
    from tests.helpers import make_venue
    now = datetime.now(timezone.utc)
    return client.post("/events", json={
        "title": "Test Event",
        "event_type_id": event_type_id,
        "venue_id": venue_id or make_venue(),
        "starts_at_utc": (now + timedelta(days=days_ahead)).isoformat(),
        "ends_at_utc":   (now + timedelta(days=days_ahead, hours=6)).isoformat(),
        "expected_guests": 50,
        "idempotency_key": idem or str(uuid.uuid4()),
        **fields,
    }, headers=auth(token))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Event lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventLifecycle:
    def test_create_event_planned(self, client, manager_token, event_type):
        rv = _make_event(client, manager_token, event_type.id)
        assert rv.status_code == 201
        assert rv.get_json()["status"] == "PLANNED"

    def test_full_lifecycle(self, client, manager_token, event_type):
        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        rv = client.post(f"/events/{eid}/confirm",    headers=auth(manager_token))
        assert rv.get_json()["status"] == "CONFIRMED"
        rv = client.post(f"/events/{eid}/start",      headers=auth(manager_token))
        assert rv.get_json()["status"] == "IN_PROGRESS"
        rv = client.post(f"/events/{eid}/complete",   headers=auth(manager_token))
        assert rv.get_json()["status"] == "COMPLETED"

    def test_illegal_transition_rejected(self, client, manager_token, event_type):
        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        # Cannot go PLANNED → IN_PROGRESS (skip CONFIRMED)
        rv = client.post(f"/events/{eid}/start", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_completed_is_terminal(self, client, manager_token, event_type):
        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        client.post(f"/events/{eid}/confirm",  headers=auth(manager_token))
        client.post(f"/events/{eid}/start",    headers=auth(manager_token))
        client.post(f"/events/{eid}/complete", headers=auth(manager_token))
        rv = client.post(f"/events/{eid}/cancel", headers=auth(manager_token))
        assert rv.status_code == 400

    def test_staff_cannot_create_event(self, client, waiter_token, event_type):
        rv = _make_event(client, waiter_token, event_type.id)
        assert rv.status_code == 403


class TestTheEventsScreenListsEveryOpenEvent:
    """/events/upcoming is the ONLY list the Events screen reads, and the Start,
    Finish and stock buttons live on its cards. It used to return PLANNED and
    CONFIRMED events that had not started yet — so a wedding vanished the
    moment it was started (no Finish button anywhere) or the moment its start
    time passed (no Start button either). Open means not finished, not future."""

    def _ids(self, client, token):
        return {e["id"] for e in client.get("/events/upcoming", headers=auth(token)).get_json()}

    def test_a_started_event_stays_on_the_list_until_it_is_finished(
            self, client, manager_token, event_type):
        eid = _make_event(client, manager_token, event_type.id).get_json()["id"]
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))
        client.post(f"/events/{eid}/start",   headers=auth(manager_token))
        assert eid in self._ids(client, manager_token)
        client.post(f"/events/{eid}/complete", headers=auth(manager_token))
        assert eid not in self._ids(client, manager_token)

    def test_an_event_whose_start_time_passed_can_still_be_started(
            self, client, manager_token, event_type):
        # Began an hour ago, confirmed, nobody has pressed Start yet.
        eid = _make_event(client, manager_token, event_type.id, days_ahead=-1 / 24).get_json()["id"]
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))
        assert eid in self._ids(client, manager_token)


class TestAnEventIsHeldSomewhere:
    """Every event books one of the spaces the manager registered. Before this,
    "where" was free text: two weddings could share one lawn at the same hour,
    and 300 guests could be booked into a space for 200."""

    def test_an_event_with_no_venue_is_refused(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        make_venue()  # a venue exists — the event simply did not pick one
        now = datetime.now(timezone.utc)
        rv = client.post("/events", headers=auth(manager_token), json={
            "title": "Nowhere", "event_type_id": event_type.id,
            "starts_at_utc": (now + timedelta(days=3)).isoformat(),
            "ends_at_utc": (now + timedelta(days=3, hours=4)).isoformat(),
        })
        assert rv.status_code == 400
        assert "where" in rv.get_json()["error"].lower()

    def test_a_villa_is_not_an_event_venue(self, client, manager_token, event_type):
        from app.extensions import db
        from app.models.bookable_resource import BookableResource
        villa = BookableResource(name="Villa 9", resource_type="VILLA",
                                 capacity=8, base_price=Decimal("100000"))
        db.session.add(villa); db.session.commit()
        rv = _make_event(client, manager_token, event_type.id, venue_id=villa.id)
        assert rv.status_code == 400
        assert "not an event venue" in rv.get_json()["error"]

    def test_a_switched_off_venue_cannot_be_booked(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue(name="Old Hall")
        client.post(f"/bookable-resources/{vid}/disable", headers=auth(manager_token))
        rv = _make_event(client, manager_token, event_type.id, venue_id=vid)
        assert rv.status_code == 400
        assert "Old Hall" in rv.get_json()["error"]

    def test_more_guests_than_the_space_holds_is_refused(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue(name="Garden", capacity=200)
        rv = _make_event(client, manager_token, event_type.id, venue_id=vid, expected_guests=300)
        assert rv.status_code == 400
        assert "Garden holds 200" in rv.get_json()["error"]
        assert _make_event(client, manager_token, event_type.id, venue_id=vid,
                           expected_guests=200).status_code == 201

    def test_two_open_events_cannot_share_a_space_at_the_same_time(
            self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue(name="Lake Lawn")
        first = _make_event(client, manager_token, event_type.id, venue_id=vid, title="Otieno Wedding")
        assert first.status_code == 201
        rv = _make_event(client, manager_token, event_type.id, venue_id=vid, title="Kamau Party")
        assert rv.status_code == 409
        assert "Otieno Wedding" in rv.get_json()["error"]
        assert "UTC" not in rv.get_json()["error"]  # said in the resort's clock
        # A different space the same day is fine.
        assert _make_event(client, manager_token, event_type.id, title="Kamau Party").status_code == 201

    def test_one_event_may_start_the_moment_the_last_one_ends(
            self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue()
        start = datetime.now(timezone.utc) + timedelta(days=5)
        body = lambda s, t: {"venue_id": vid, "title": t,
                             "starts_at_utc": s.isoformat(),
                             "ends_at_utc": (s + timedelta(hours=4)).isoformat()}
        assert _make_event(client, manager_token, event_type.id, **body(start, "Morning")).status_code == 201
        assert _make_event(client, manager_token, event_type.id,
                           **body(start + timedelta(hours=4), "Evening")).status_code == 201

    def test_a_cancelled_event_frees_the_space(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue()
        eid = _make_event(client, manager_token, event_type.id, venue_id=vid).get_json()["id"]
        client.post(f"/events/{eid}/cancel", headers=auth(manager_token))
        assert _make_event(client, manager_token, event_type.id, venue_id=vid).status_code == 201

    def test_editing_cannot_overfill_or_double_book_a_space(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        small, busy = make_venue(name="Gazebo", capacity=40), make_venue(name="Hall")
        _make_event(client, manager_token, event_type.id, venue_id=busy, title="Hall Booking")
        eid = _make_event(client, manager_token, event_type.id, venue_id=small,
                          expected_guests=30).get_json()["id"]
        rv = client.patch(f"/events/{eid}", headers=auth(manager_token), json={"expected_guests": 60})
        assert rv.status_code == 400 and "Gazebo holds 40" in rv.get_json()["error"]
        rv = client.patch(f"/events/{eid}", headers=auth(manager_token), json={"venue_id": busy})
        assert rv.status_code == 409 and "Hall Booking" in rv.get_json()["error"]
        # Editing its own details does not make it clash with itself.
        rv = client.patch(f"/events/{eid}", headers=auth(manager_token), json={"title": "Renamed"})
        assert rv.status_code == 200

    def test_the_event_says_where_it_is(self, client, manager_token, event_type):
        from tests.helpers import make_venue
        vid = make_venue(name="Poolside", capacity=120)
        ev = _make_event(client, manager_token, event_type.id, venue_id=vid).get_json()
        assert ev["venue"] == {"id": vid, "name": "Poolside", "capacity": 120}
        assert ev["location"] == "Poolside"

    def test_a_guest_count_that_is_not_a_number_is_refused_in_plain_english(
            self, client, manager_token, event_type):
        for bad in ("many", -50, 0):
            rv = _make_event(client, manager_token, event_type.id, expected_guests=bad)
            assert rv.status_code == 400, bad
            assert "guests" in rv.get_json()["error"]


class TestTheManagerRunsTheVenues:
    """The spaces are the manager's to run, fee included (decided 17 Sep 2026).
    A villa's nightly rate stays the owner's."""

    def test_a_manager_sets_a_venue_fee(self, client, manager_token):
        from tests.helpers import make_venue
        vid = make_venue(base_price="50000")
        rv = client.patch(f"/bookable-resources/{vid}", headers=auth(manager_token),
                          json={"base_price": "65000", "capacity": 250})
        assert rv.status_code == 200
        assert rv.get_json()["base_price"] == "65000.00"
        assert rv.get_json()["capacity"] == 250

    def test_a_manager_still_cannot_change_a_villa_rate(self, client, manager_token):
        from app.extensions import db
        from app.models.bookable_resource import BookableResource
        villa = BookableResource(name="Villa 3", resource_type="VILLA",
                                 capacity=8, base_price=Decimal("100000"))
        db.session.add(villa); db.session.commit()
        rv = client.patch(f"/bookable-resources/{villa.id}", headers=auth(manager_token),
                          json={"base_price": "1"})
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 2 & 3. Alert scheduling on confirm
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertScheduling:
    def test_confirm_creates_4_notifications_per_employee(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification, NotificationReferenceType
        from app.extensions import db

        # Create event and assign the employee
        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        client.post(f"/events/{eid}/assignments", json={
            "employee_id": employee_profile.id,
            "job": "SERVICE", "role_on_event": "Waiter",
        }, headers=auth(manager_token))

        # Confirm the event
        rv = client.post(f"/events/{eid}/confirm", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["notifications_scheduled"] == 5   # 7 days, 3 days, tomorrow, 2 hours, and the morning of

        with app.app_context():
            notifs = db.session.query(Notification).filter_by(
                reference_type=NotificationReferenceType.EVENT_ALERT.value,
                reference_id=eid,
            ).all()
        assert len(notifs) == 5   # 7 days, 3 days, tomorrow, 2 hours, and the morning of

    def test_notifications_have_correct_offsets(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification
        from app.extensions import db

        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        starts = datetime.fromisoformat(ev["starts_at"])
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)

        client.post(f"/events/{eid}/assignments", json={
            "employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "Lead",
        }, headers=auth(manager_token))
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))

        with app.app_context():
            notifs = db.session.query(Notification).filter_by(reference_id=eid).all()
        as_utc = lambda d: d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
        today = [n for n in notifs if n.subject.startswith("[Today]")]
        # The morning-of reminder: 07:00 on the resort clock (UTC in tests),
        # never later than 3 hours before the start.
        morning = starts.replace(hour=7, minute=0, second=0, microsecond=0)
        assert len(today) == 1
        assert abs((as_utc(today[0].scheduled_for_utc) - min(morning, starts - timedelta(hours=3))).total_seconds()) < 5
        scheduled_times = sorted(
            [as_utc(n.scheduled_for_utc) for n in notifs if not n.subject.startswith("[Today]")]
        )
        expected_offsets = sorted([
            starts - timedelta(days=7),
            starts - timedelta(days=3),
            starts - timedelta(days=1),
            starts - timedelta(hours=2),
        ])
        for actual, expected in zip(scheduled_times, expected_offsets):
            diff = abs((actual - expected).total_seconds())
            assert diff < 5  # within 5 seconds


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Idempotent confirm — no duplicate notifications
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotentConfirm:
    def test_double_confirm_still_has_4_notifications(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification
        from app.extensions import db

        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        client.post(f"/events/{eid}/assignments", json={
            "employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "Chef",
        }, headers=auth(manager_token))

        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))  # first
        rv2 = client.post(f"/events/{eid}/confirm", headers=auth(manager_token))  # second
        assert rv2.status_code == 200   # idempotent — not an error

        with app.app_context():
            count = db.session.query(Notification).filter_by(reference_id=eid).count()
        assert count == 5   # still 5, not 10


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Cancellation flips QUEUED notifications to FAILED
# ═══════════════════════════════════════════════════════════════════════════════

class TestCancellation:
    def test_cancel_flips_notifications_to_failed(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification, NotificationStatus
        from app.extensions import db

        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        client.post(f"/events/{eid}/assignments", json={
            "employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "Bar",
        }, headers=auth(manager_token))
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))
        client.post(f"/events/{eid}/cancel",  headers=auth(manager_token))

        with app.app_context():
            notifs = db.session.query(Notification).filter_by(reference_id=eid).all()
        assert all(n.status == NotificationStatus.FAILED.value for n in notifs)
        assert all("cancelled" in (n.notes or "") for n in notifs)
        assert len(notifs) == 5   # history preserved, not deleted


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Alive delivery
# ═══════════════════════════════════════════════════════════════════════════════

class TestAliveDelivery:
    def _seed_notification(self, app, user_id, past_minutes=30):
        """Create a QUEUED notification due 30 minutes ago."""
        from app.models.notification import Notification, NotificationStatus
        from app.extensions import db
        now = datetime.now(timezone.utc)
        notif = Notification(
            recipient_user_id=user_id,
            reference_type="GENERAL",
            subject="Test alert",
            body="Hello there.",
            status=NotificationStatus.QUEUED.value,
            scheduled_for_utc=now - timedelta(minutes=past_minutes),
            idempotency_key=f"test-alive-{uuid.uuid4()}",
        )
        with app.app_context():
            db.session.add(notif)
            db.session.commit()
            return notif.id

    def test_clocked_in_user_gets_in_app_delivery(
            self, client, manager_token, employee_profile, app):
        from app.models.clock_event import ClockEvent, ClockEventType
        from app.models.notification import Notification, NotificationStatus
        from app.models.user import User
        from app.extensions import db
        from app.services.notifications.dispatcher import deliver_due

        with app.app_context():
            user = db.session.query(User).filter_by(username="waiter1").first()
            # Clock them in
            clock = ClockEvent(
                employee_id=employee_profile.id,
                event_type=ClockEventType.CLOCK_IN.value,
                occurred_at_utc=datetime.now(timezone.utc),
                idempotency_key=f"test-clock-{uuid.uuid4()}",
            )
            db.session.add(clock)
            db.session.commit()

            notif_id = self._seed_notification(app, user.id)
            db.session.expire_all()

            results = deliver_due()
            db.session.commit()

            notif = db.session.get(Notification, notif_id)
            assert notif.status == NotificationStatus.DELIVERED.value
            assert notif.channel == "IN_APP"
            assert results["delivered"] >= 1

    def test_off_shift_user_finds_the_reminder_in_their_inbox(
            self, client, manager_token, app):
        """Was: off shift → FAILED. The inbox only shows DELIVERED, so a reminder
        to anyone not at work — the people a "[7 days]" reminder is FOR — was
        thrown away, and their Alerts screen said "You're all caught up".
        Proved in Chrome on 17 Sep 2026. With no phone gateway it now waits in
        the inbox for when they next open the app."""
        from app.models.notification import Notification, NotificationStatus
        from app.models.user import User
        from app.extensions import db
        from app.services.notifications.dispatcher import deliver_due

        # owner1 has no EmployeeProfile → never present → falls through
        with app.app_context():
            user = db.session.query(User).filter_by(username="owner1").first()
            notif_id = self._seed_notification(app, user.id)
            db.session.expire_all()

            results = deliver_due()
            db.session.commit()

            notif = db.session.get(Notification, notif_id)
            assert notif.status == NotificationStatus.DELIVERED.value
            assert notif.channel == "IN_APP"
            assert "SMS" in (notif.notes or "")          # why it did not go by phone
            assert results["delivered"] >= 1

        # Logged in WITHOUT clocking in — the owner_token fixture clocks in,
        # which would make them "present" and prove nothing.
        token = client.post("/auth/login", json={"username": "owner1",
                                                 "password": "OwnerPass1!"}).get_json()["access_token"]
        inbox = client.get("/notifications/inbox", headers=auth(token)).get_json()
        assert any(n["subject"] == "Test alert" for n in inbox)


class TestReminderWording:
    """Reminders are read by staff on their phones, in Kenya."""

    def test_a_reminder_gives_the_resort_time_and_the_venue(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification
        from app.models.system_setting import SystemSetting
        from app.extensions import db
        from tests.helpers import make_venue
        db.session.get(SystemSetting, "business_day_timezone").value = "EAT"
        db.session.commit()
        start = datetime(2030, 3, 14, 11, 0, tzinfo=timezone.utc)        # 14:00 in Nairobi
        eid = client.post("/events", headers=auth(manager_token), json={
            "title": "Otieno Wedding", "event_type_id": event_type.id,
            "venue_id": make_venue(name="Lakeside Lawn"),
            "starts_at_utc": start.isoformat(),
            "ends_at_utc": (start + timedelta(hours=6)).isoformat(),
        }).get_json()["id"]
        client.post(f"/events/{eid}/assignments", headers=auth(manager_token),
                    json={"employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "Bar"})
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))
        body = db.session.query(Notification).filter_by(reference_id=eid).first().body
        assert "14 Mar 2030 14:00" in body and "UTC" not in body
        assert "Lakeside Lawn" in body


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Inbox + mark-as-read
# ═══════════════════════════════════════════════════════════════════════════════

class TestInbox:
    def _deliver_to_waiter(self, client, manager_token, employee_profile, app):
        from app.models.clock_event import ClockEvent, ClockEventType
        from app.models.notification import Notification, NotificationStatus
        from app.models.user import User
        from app.extensions import db
        from app.services.notifications.dispatcher import deliver_due

        with app.app_context():
            user = db.session.query(User).filter_by(username="waiter1").first()
            clock = ClockEvent(
                employee_id=employee_profile.id,
                event_type=ClockEventType.CLOCK_IN.value,
                occurred_at_utc=datetime.now(timezone.utc),
                idempotency_key=f"inbox-clock-{uuid.uuid4()}",
            )
            db.session.add(clock)
            notif = Notification(
                recipient_user_id=user.id,
                reference_type="GENERAL",
                subject="Inbox test",
                body="Check me out.",
                status=NotificationStatus.QUEUED.value,
                scheduled_for_utc=datetime.now(timezone.utc) - timedelta(minutes=5),
                idempotency_key=f"inbox-notif-{uuid.uuid4()}",
            )
            db.session.add(notif)
            db.session.commit()
            deliver_due()
            db.session.commit()
            return notif.id

    def test_inbox_returns_unread_delivered(
            self, client, manager_token, waiter_token, employee_profile, app):
        self._deliver_to_waiter(client, manager_token, employee_profile, app)
        rv = client.get("/notifications/inbox", headers=auth(waiter_token))
        assert rv.status_code == 200
        assert len(rv.get_json()) >= 1

    def test_mark_read_changes_status(
            self, client, manager_token, waiter_token, employee_profile, app):
        notif_id = self._deliver_to_waiter(client, manager_token, employee_profile, app)
        rv = client.post(f"/notifications/{notif_id}/mark-read", headers=auth(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "READ"

    def test_mark_read_is_idempotent(
            self, client, manager_token, waiter_token, employee_profile, app):
        notif_id = self._deliver_to_waiter(client, manager_token, employee_profile, app)
        client.post(f"/notifications/{notif_id}/mark-read", headers=auth(waiter_token))
        rv2 = client.post(f"/notifications/{notif_id}/mark-read", headers=auth(waiter_token))
        assert rv2.status_code == 200

    def test_marked_read_not_in_inbox(
            self, client, manager_token, waiter_token, employee_profile, app):
        notif_id = self._deliver_to_waiter(client, manager_token, employee_profile, app)
        client.post(f"/notifications/{notif_id}/mark-read", headers=auth(waiter_token))
        rv = client.get("/notifications/inbox", headers=auth(waiter_token))
        ids = [n["id"] for n in rv.get_json()]
        assert notif_id not in ids


# ═══════════════════════════════════════════════════════════════════════════════
# 8 & 9. Event inventory — issue, judge exclusion, return, reconciliation
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventInventory:
    def _setup(self, client, manager_token, event_type, inventory_item, app):
        """Create event + allocation, return (event_id, alloc_id)."""
        from app.services.stock import get_current_stock
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.user import User
        from app.extensions import db

        # Seed some stock first
        with app.app_context():
            user = db.session.query(User).filter_by(username="manager1").first()
            sm = StockMovement(
                item_id=inventory_item.id,
                change_amount=Decimal("100"),
                reason=MovementReason.PURCHASE.value,
                actor_id=user.id,
                idempotency_key=f"stock-seed-{uuid.uuid4()}",
            )
            db.session.add(sm)
            db.session.commit()

        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        rv = client.post(f"/events/{eid}/inventory/allocate", json={
            "inventory_item_id": inventory_item.id,
            "allocated_quantity": "20",
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        alloc_id = rv.get_json()["id"]
        return eid, alloc_id

    def test_issue_writes_event_allocation_movement(
            self, client, manager_token, event_type, inventory_item, app):
        from app.models.stock_movement import StockMovement, MovementReason
        from app.extensions import db

        eid, alloc_id = self._setup(client, manager_token, event_type, inventory_item, app)
        rv = client.post(f"/events/{eid}/inventory/{alloc_id}/issue",
                         headers=auth(manager_token))
        assert rv.status_code == 200
        movement_id = rv.get_json()["movement_id"]

        with app.app_context():
            mv = db.session.get(StockMovement, movement_id)
        assert mv.reason == MovementReason.EVENT_ALLOCATION.value
        assert Decimal(str(mv.change_amount)) == Decimal("-20")

    def test_event_allocation_excluded_from_judge_consumption(
            self, client, manager_token, event_type, inventory_item, app):
        """EVENT_ALLOCATION must NOT be in CONSUMPTION_REASONS."""
        from app.models.stock_movement import MovementReason, CONSUMPTION_REASONS
        assert MovementReason.EVENT_ALLOCATION not in CONSUMPTION_REASONS

    def test_judge_ignores_event_movement_in_ratio(
            self, client, manager_token, event_type, inventory_item, app):
        """A large event movement should not cause a judge ratio alert."""
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.judge_baseline import JudgeBaseline
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.extensions import db
        from app.judge.engine import _get_period_consumption
        from decimal import Decimal
        from datetime import timedelta

        with app.app_context():
            user = db.session.query(User).filter_by(username="manager1").first()
            # Create a large EVENT_ALLOCATION movement
            sm = StockMovement(
                item_id=inventory_item.id,
                change_amount=Decimal("-999"),
                reason=MovementReason.EVENT_ALLOCATION.value,
                actor_id=user.id,
                idempotency_key=f"judge-test-event-{uuid.uuid4()}",
            )
            db.session.add(sm)
            db.session.commit()

            now = datetime.now(timezone.utc)
            # Consumption should be 0 — event movements excluded
            consumption = _get_period_consumption(
                inventory_item.id,
                now - timedelta(hours=1),
                now + timedelta(hours=1),
            )
        assert consumption == Decimal("0")

    def test_return_restores_stock(
            self, client, manager_token, event_type, inventory_item, app):
        from app.services.stock import get_current_stock

        eid, alloc_id = self._setup(client, manager_token, event_type, inventory_item, app)
        client.post(f"/events/{eid}/inventory/{alloc_id}/issue", headers=auth(manager_token))

        with app.app_context():
            stock_after_issue = get_current_stock(inventory_item.id)

        rv = client.post(f"/events/{eid}/inventory/{alloc_id}/return",
                         json={"return_quantity": "15"}, headers=auth(manager_token))
        assert rv.status_code == 200

        with app.app_context():
            stock_after_return = get_current_stock(inventory_item.id)
        assert stock_after_return == stock_after_issue + Decimal("15")

    def test_per_event_reconciliation(
            self, client, manager_token, event_type, inventory_item, app):
        eid, alloc_id = self._setup(client, manager_token, event_type, inventory_item, app)
        client.post(f"/events/{eid}/inventory/{alloc_id}/issue", headers=auth(manager_token))
        client.post(f"/events/{eid}/inventory/{alloc_id}/return",
                    json={"return_quantity": "5"}, headers=auth(manager_token))

        rv = client.get(f"/events/{eid}/inventory", headers=auth(manager_token))
        assert rv.status_code == 200
        recon = rv.get_json()["reconciliation"]
        assert len(recon) == 1
        r = recon[0]
        assert Decimal(r["issued"]) == Decimal("20")
        assert Decimal(r["returned"]) == Decimal("5")
        assert Decimal(r["consumed"]) == Decimal("15")


# ═══════════════════════════════════════════════════════════════════════════════
# 10 & 11 & 12. Suggestion routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestSuggestionRouting:
    def _submit(self, client, token, category, anonymous=False, idem=None):
        return client.post("/suggestions", json={
            "category":        category,
            "subject":         f"Test {category}",
            "body":            "This is a test suggestion.",
            "anonymous":       anonymous,
            "idempotency_key": idem or str(uuid.uuid4()),
        }, headers=auth(token))

    def test_owner_private_invisible_to_manager_list(
            self, client, manager_token, owner_token):
        self._submit(client, owner_token, "OWNER_PRIVATE")
        rv = client.get("/suggestions", headers=auth(manager_token))
        assert rv.status_code == 200
        cats = [s["category"] for s in rv.get_json()]
        assert "OWNER_PRIVATE" not in cats

    def test_owner_private_404_to_manager_by_id(
            self, client, manager_token, owner_token):
        rv = self._submit(client, owner_token, "OWNER_PRIVATE")
        sid = rv.get_json()["id"]
        rv = client.get(f"/suggestions/{sid}", headers=auth(manager_token))
        assert rv.status_code == 404

    def test_owner_sees_owner_private(self, client, owner_token):
        self._submit(client, owner_token, "OWNER_PRIVATE")
        rv = client.get("/suggestions", headers=auth(owner_token))
        cats = [s["category"] for s in rv.get_json()]
        assert "OWNER_PRIVATE" in cats

    def test_management_visible_to_manager(self, client, manager_token):
        self._submit(client, manager_token, "MANAGEMENT")
        rv = client.get("/suggestions", headers=auth(manager_token))
        cats = [s["category"] for s in rv.get_json()]
        assert "MANAGEMENT" in cats

    def test_anonymous_owner_private_allowed(self, client, manager_token, owner_token):
        rv = self._submit(client, manager_token, "OWNER_PRIVATE", anonymous=True)
        assert rv.status_code == 201
        assert rv.get_json()["submitted_by"] == "anonymous"

    def test_anonymous_management_rejected(self, client, manager_token):
        rv = self._submit(client, manager_token, "MANAGEMENT", anonymous=True)
        assert rv.status_code == 400
        assert "anonymous" in rv.get_json()["error"].lower()

    def test_staff_below_manager_cannot_list(self, client, waiter_token):
        rv = client.get("/suggestions", headers=auth(waiter_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Owner gets Notification on OWNER_PRIVATE suggestion
# ═══════════════════════════════════════════════════════════════════════════════

class TestOwnerNotification:
    def test_owner_private_creates_notification_for_owner(
            self, client, manager_token, owner_token, app):
        from app.models.notification import Notification, NotificationReferenceType
        from app.models.user import User
        from app.extensions import db

        idem = str(uuid.uuid4())
        rv = client.post("/suggestions", json={
            "category": "OWNER_PRIVATE",
            "subject": "Sensitive issue",
            "body": "This goes to the owner only.",
            "idempotency_key": idem,
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        suggestion_id = rv.get_json()["id"]

        with app.app_context():
            owner = db.session.query(User).filter_by(username="owner1").first()
            notif = db.session.query(Notification).filter_by(
                recipient_user_id=owner.id,
                reference_type=NotificationReferenceType.SUGGESTION_OWNER.value,
                reference_id=suggestion_id,
            ).first()
        assert notif is not None

    def test_management_suggestion_does_not_create_owner_notification(
            self, client, manager_token, app):
        from app.models.notification import Notification, NotificationReferenceType
        from app.extensions import db

        idem = str(uuid.uuid4())
        rv = client.post("/suggestions", json={
            "category": "MANAGEMENT",
            "subject": "Staff schedule",
            "body": "Consider rotating shifts.",
            "idempotency_key": idem,
        }, headers=auth(manager_token))
        suggestion_id = rv.get_json()["id"]

        with app.app_context():
            notif = db.session.query(Notification).filter_by(
                reference_type=NotificationReferenceType.SUGGESTION_OWNER.value,
                reference_id=suggestion_id,
            ).first()
        assert notif is None


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Assignment workflow
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssignments:
    def test_assign_employee_to_event(
            self, client, manager_token, event_type, employee_profile):
        ev = _make_event(client, manager_token, event_type.id).get_json()
        rv = client.post(f"/events/{ev['id']}/assignments", json={
            "employee_id": employee_profile.id,
            "job": "SERVICE", "role_on_event": "Head Chef",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["status"] == "ASSIGNED"

    def test_employee_acknowledges_assignment(
            self, client, manager_token, waiter_token, event_type, employee_profile):
        ev = _make_event(client, manager_token, event_type.id).get_json()
        rv = client.post(f"/events/{ev['id']}/assignments", json={
            "employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "Waiter",
        }, headers=auth(manager_token))
        aid = rv.get_json()["id"]
        rv = client.post(f"/events/{ev['id']}/assignments/{aid}/acknowledge",
                         headers=auth(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "ACKNOWLEDGED"

    def test_assigning_to_confirmed_event_schedules_notifications(
            self, client, manager_token, event_type, employee_profile, app):
        from app.models.notification import Notification
        from app.extensions import db

        ev = _make_event(client, manager_token, event_type.id).get_json()
        eid = ev["id"]
        client.post(f"/events/{eid}/confirm", headers=auth(manager_token))

        # Assign after confirm → notifications created immediately
        rv = client.post(f"/events/{eid}/assignments", json={
            "employee_id": employee_profile.id, "job": "SERVICE", "role_on_event": "DJ",
        }, headers=auth(manager_token))
        assert rv.get_json()["notifications_scheduled"] == 5   # 7 days, 3 days, tomorrow, 2 hours, and the morning of

        with app.app_context():
            count = db.session.query(Notification).filter_by(reference_id=eid).count()
        assert count == 5


def test_two_hour_alert_is_deliverable_within_a_quarter_hour(app):
    """The 2-hour and 'tomorrow' tiers only work if delivery runs often.

    ALERT_OFFSETS promises a warning 2 hours before an event. That warning is
    queued for start-2h and sits QUEUED until `flask events deliver-due` runs.
    While that cron was daily (DEPLOY.md), the alert could be delivered up to
    24h late — i.e. after the event was over. This pins the requirement so the
    schedule cannot silently regress: the tightest offset must be much larger
    than the delivery interval.
    """
    from datetime import timedelta
    from app.services.events import ALERT_OFFSETS

    DELIVERY_INTERVAL = timedelta(minutes=15)   # */15 in DEPLOY.md
    tightest = min(offset for offset, _label in ALERT_OFFSETS)

    assert tightest > DELIVERY_INTERVAL * 4, (
        f"Tightest alert is {tightest} but notifications are only dispatched every "
        f"{DELIVERY_INTERVAL}. Either widen the offset or run deliver-due more often "
        f"— otherwise that alert arrives after the event it was warning about."
    )
