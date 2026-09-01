"""
tests/test_hr.py — Chunk 5 HR & Clock-in tests.

Coverage:
  - Employee profile CRUD (manager creates, owner disables/enables)
  - WiFi allow-list management (owner only)
  - Shift scheduling (conflict detection, cancel)
  - Clock-in/out WiFi enforcement
  - Manual clock override (manager only)
  - Leave request lifecycle (create, approve, reject, self-approval block)
  - Absence notices (employee posts, manager lists)
  - Attendance today view
  - Performance scoring endpoint
  - Payroll draft
"""
import uuid
import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════════════════

def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Employee profiles
# ══════════════════════════════════════════════════════════════════════════════

class TestEmployeeProfiles:
    def test_manager_creates_profile(self, client, manager_token, app):
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            user = db.session.query(User).filter_by(username="staff1").first()
            uid = user.id

        rv = client.post("/hr/profiles", json={
            "user_id": uid, "full_name": "Jane Doe", "phone": "+254711111111",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["full_name"] == "Jane Doe"

    def test_staff_cannot_create_profile(self, client, waiter_token, app):
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            user = db.session.query(User).filter_by(username="staff1").first()
            uid = user.id

        rv = client.post("/hr/profiles", json={
            "user_id": uid, "full_name": "Jane Doe", "phone": "+254711111111",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_duplicate_profile_rejected(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/profiles", json={
            "user_id": waiter_profile.user_id,
            "full_name": "Duplicate", "phone": "+254799999999",
        }, headers=auth(manager_token))
        assert rv.status_code == 409

    def test_owner_disables_and_enables_profile(self, client, owner_token, waiter_profile):
        pid = waiter_profile.id
        rv = client.post(f"/hr/profiles/{pid}/disable", headers=auth(owner_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is False

        rv = client.post(f"/hr/profiles/{pid}/enable", headers=auth(owner_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is True

    def test_manager_cannot_disable_profile(self, client, manager_token, waiter_profile):
        rv = client.post(f"/hr/profiles/{waiter_profile.id}/disable",
                         headers=auth(manager_token))
        assert rv.status_code == 403

    def test_disabled_profile_kills_already_issued_token(self, client, owner_token, waiter_token, waiter_profile):
        """The kill-switch invariant: disabling a profile must lock the login
        account too, or a JWT issued before the disable keeps working on every
        endpoint that isn't clock-gated (require_active_user only ever checked
        User.is_active, never EmployeeProfile.is_active)."""
        # Sanity: the token works before disable.
        rv = client.get("/hr/clock-status", headers=auth(waiter_token))
        assert rv.status_code == 200

        rv = client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        assert rv.status_code == 200

        # Same still-unexpired token, no re-login — must now be rejected.
        rv = client.get("/hr/clock-status", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_owner_cannot_disable_own_profile(self, client, owner_token, app):
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            owner = db.session.query(User).filter_by(username="owner1").first()
            # owner_token already creates this profile (so require_clocked_in
            # passes on POS endpoints elsewhere) — reuse it instead of a second
            # insert, which would violate EmployeeProfile.user_id's unique constraint.
            profile = db.session.query(EmployeeProfile).filter_by(user_id=owner.id).first()
            if not profile:
                profile = EmployeeProfile(user_id=owner.id, full_name="Test Owner", phone="+254700000099")
                db.session.add(profile)
                db.session.commit()
            pid = profile.id
        rv = client.post(f"/hr/profiles/{pid}/disable", headers=auth(owner_token))
        assert rv.status_code == 403

    def test_reactivating_profile_disabled_account_requires_owner(self, client, owner_token, manager_token, waiter_profile, app):
        """/auth/users/<id>/activate must not be able to silently undo an
        owner-level profile disable — only the owner can reverse it there too."""
        from app.models.employee_profile import EmployeeProfile
        from app.extensions import db

        rv = client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        assert rv.status_code == 200
        target_user_id = waiter_profile.user_id

        # A manager who outranks the waiter cannot reactivate a profile-disabled account.
        rv = client.post(f"/auth/users/{target_user_id}/activate", headers=auth(manager_token))
        assert rv.status_code == 403

        # The owner can, and it cascades the profile back on too.
        rv = client.post(f"/auth/users/{target_user_id}/activate", headers=auth(owner_token))
        assert rv.status_code == 200
        with app.app_context():
            assert db.session.get(EmployeeProfile, waiter_profile.id).is_active is True


# ══════════════════════════════════════════════════════════════════════════════
# 2. WiFi allow-list
# ══════════════════════════════════════════════════════════════════════════════

class TestWifi:
    def test_owner_creates_wifi_entry(self, client, owner_token):
        rv = client.post("/hr/wifi", json={
            "ssid": "Hotel-Staff", "ip_cidr": "10.0.0.0/8",
        }, headers=auth(owner_token))
        assert rv.status_code == 201
        assert rv.get_json()["ip_cidr"] == "10.0.0.0/8"

    def test_invalid_cidr_rejected(self, client, owner_token):
        rv = client.post("/hr/wifi", json={
            "ssid": "BadNet", "ip_cidr": "not-a-cidr",
        }, headers=auth(owner_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_manager_cannot_create_wifi(self, client, manager_token):
        rv = client.post("/hr/wifi", json={
            "ssid": "Hotel-Staff", "ip_cidr": "10.0.0.0/8",
        }, headers=auth(manager_token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 3. Shift scheduling
# ══════════════════════════════════════════════════════════════════════════════

class TestShifts:
    def test_manager_creates_shift(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/shifts", json={
            "employee_id": waiter_profile.id,
            "scheduled_start_utc": "2030-01-01T08:00:00",
            "scheduled_end_utc":   "2030-01-01T16:00:00",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["employee_id"] == waiter_profile.id

    def test_shift_conflict_rejected(self, client, manager_token, waiter_profile):
        # First shift
        client.post("/hr/shifts", json={
            "employee_id": waiter_profile.id,
            "scheduled_start_utc": "2030-06-01T08:00:00",
            "scheduled_end_utc":   "2030-06-01T16:00:00",
        }, headers=auth(manager_token))
        # Overlapping shift
        rv = client.post("/hr/shifts", json={
            "employee_id": waiter_profile.id,
            "scheduled_start_utc": "2030-06-01T10:00:00",
            "scheduled_end_utc":   "2030-06-01T18:00:00",
        }, headers=auth(manager_token))
        assert rv.status_code == 409

    def test_cancel_shift(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/shifts", json={
            "employee_id": waiter_profile.id,
            "scheduled_start_utc": "2030-03-01T08:00:00",
            "scheduled_end_utc":   "2030-03-01T16:00:00",
        }, headers=auth(manager_token))
        shift_id = rv.get_json()["id"]

        rv = client.post(f"/hr/shifts/{shift_id}/cancel", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CANCELLED"

    def test_staff_cannot_create_shift(self, client, waiter_token, waiter_profile):
        rv = client.post("/hr/shifts", json={
            "employee_id": waiter_profile.id,
            "scheduled_start_utc": "2030-02-01T08:00:00",
            "scheduled_end_utc":   "2030-02-01T16:00:00",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 4. Clock-in / clock-out (WiFi enforcement)
# ══════════════════════════════════════════════════════════════════════════════

class TestClockInOut:
    def test_clock_in_on_wifi(self, client, waiter_token, waiter_profile, wifi_allowed):
        rv = client.post("/hr/clock-in",
                         json={"ssid": "staff-dev-net"},
                         headers=auth(waiter_token),
                         environ_base={"REMOTE_ADDR": "127.0.0.1"})
        assert rv.status_code == 201
        assert rv.get_json()["event_type"] == "CLOCK_IN"

    def test_clock_in_blocked_off_wifi(self, client, waiter_token, waiter_profile, wifi_allowed):
        """Off the network, with a network configured.

        This used to omit the `wifi_allowed` fixture, so it ran against an EMPTY
        allow-list and passed because nothing was configured — not because
        8.8.8.8 was outside a real range. Those are different failures with
        different fixes, and only one of them is what this test's name claims.
        The fixture makes it test what it says.
        """
        rv = client.post("/hr/clock-in",
                         json={},
                         headers=auth(waiter_token),
                         environ_base={"REMOTE_ADDR": "8.8.8.8"})
        assert rv.status_code == 403
        assert "WiFi" in rv.get_json()["error"]

    def test_clock_out_on_wifi(self, client, waiter_token, waiter_profile, wifi_allowed):
        # Clock in first
        client.post("/hr/clock-in",
                    json={"ssid": "staff-dev-net"},
                    headers=auth(waiter_token),
                    environ_base={"REMOTE_ADDR": "127.0.0.1"})
        rv = client.post("/hr/clock-out",
                         json={},
                         headers=auth(waiter_token),
                         environ_base={"REMOTE_ADDR": "127.0.0.1"})
        assert rv.status_code == 201
        assert rv.get_json()["event_type"] == "CLOCK_OUT"

    def test_clock_in_idempotent(self, client, waiter_token, waiter_profile, wifi_allowed):
        idem = str(uuid.uuid4())
        for _ in range(2):
            rv = client.post("/hr/clock-in",
                             json={"idempotency_key": idem},
                             headers=auth(waiter_token),
                             environ_base={"REMOTE_ADDR": "127.0.0.1"})
        assert rv.status_code == 200
        assert rv.get_json()["duplicate"] is True

    def test_no_profile_blocks_clock_in(self, client, wifi_allowed):
        # manager1 has no employee profile yet — deliberately NOT using the
        # manager_token fixture here, since it now creates one (so POS/payment
        # tests elsewhere pass require_clocked_in). Raw login keeps this test's
        # actual premise (no profile) true.
        rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
        token = rv.get_json()["access_token"]
        rv = client.post("/hr/clock-in",
                         json={},
                         headers=auth(token),
                         environ_base={"REMOTE_ADDR": "127.0.0.1"})
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 5. Manual clock override
# ══════════════════════════════════════════════════════════════════════════════

class TestManualClock:
    def test_manager_can_override(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id,
            "event_type":  "CLOCK_IN",
            "reason":      "Phone was lost",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["is_manual_override"] is True

    def test_override_requires_reason(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id,
            "event_type":  "CLOCK_IN",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_staff_cannot_override(self, client, waiter_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id,
            "event_type":  "CLOCK_IN",
            "reason":      "Testing",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 6. Leave requests
# ══════════════════════════════════════════════════════════════════════════════

class TestLeaveRequests:
    def test_employee_creates_leave(self, client, waiter_token, waiter_profile):
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "ANNUAL",
            "start_date": "2030-07-01",
            "end_date":   "2030-07-05",
        }, headers=auth(waiter_token))
        assert rv.status_code == 201
        assert rv.get_json()["status"] == "PENDING"

    def test_manager_approves_leave(self, client, waiter_token, manager_token, waiter_profile):
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "SICK",
            "start_date": "2030-08-01",
            "end_date":   "2030-08-02",
        }, headers=auth(waiter_token))
        lr_id = rv.get_json()["id"]

        rv = client.post(f"/hr/leave-requests/{lr_id}/approve",
                         json={"notes": "Approved"},
                         headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "APPROVED"

    def test_manager_rejects_leave(self, client, waiter_token, manager_token, waiter_profile):
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "ANNUAL",
            "start_date": "2030-09-01",
            "end_date":   "2030-09-03",
        }, headers=auth(waiter_token))
        lr_id = rv.get_json()["id"]

        rv = client.post(f"/hr/leave-requests/{lr_id}/reject",
                         headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "REJECTED"

    def test_self_approval_blocked(self, client, manager_token, manager_profile):
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "ANNUAL",
            "start_date": "2030-10-01",
            "end_date":   "2030-10-02",
        }, headers=auth(manager_token))
        lr_id = rv.get_json()["id"]

        rv = client.post(f"/hr/leave-requests/{lr_id}/approve",
                         headers=auth(manager_token))
        assert rv.status_code == 403
        assert "own" in rv.get_json()["error"].lower()

    def test_leave_idempotent(self, client, waiter_token, waiter_profile):
        idem = str(uuid.uuid4())
        for _ in range(2):
            rv = client.post("/hr/leave-requests", json={
                "leave_type":      "ANNUAL",
                "start_date":      "2030-11-01",
                "end_date":        "2030-11-01",
                "idempotency_key": idem,
            }, headers=auth(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["duplicate"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 7. Absence notices
# ══════════════════════════════════════════════════════════════════════════════

class TestAbsenceNotices:
    def test_employee_sends_notice(self, client, waiter_token, waiter_profile):
        rv = client.post("/hr/absence-notices", json={
            "notice_type": "ABSENT",
            "reason":      "Feeling unwell",
        }, headers=auth(waiter_token))
        assert rv.status_code == 201
        assert rv.get_json()["notice_type"] == "ABSENT"

    def test_late_notice_with_minutes(self, client, waiter_token, waiter_profile):
        rv = client.post("/hr/absence-notices", json={
            "notice_type":           "LATE",
            "expected_late_minutes": 30,
        }, headers=auth(waiter_token))
        assert rv.status_code == 201

    def test_manager_lists_notices(self, client, waiter_token, manager_token, waiter_profile):
        client.post("/hr/absence-notices", json={
            "notice_type": "ABSENT",
        }, headers=auth(waiter_token))
        rv = client.get("/hr/absence-notices", headers=auth(manager_token))
        assert rv.status_code == 200
        assert len(rv.get_json()) >= 1

    def test_no_profile_blocks_notice(self, client):
        # manager1 has no employee profile — raw login, not the manager_token
        # fixture, for the same reason as test_no_profile_blocks_clock_in above.
        rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
        token = rv.get_json()["access_token"]
        rv = client.post("/hr/absence-notices", json={
            "notice_type": "ABSENT",
        }, headers=auth(token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 8. Attendance today view
# ══════════════════════════════════════════════════════════════════════════════

class TestAttendanceToday:
    def test_today_view_requires_manager(self, client, waiter_token):
        rv = client.get("/hr/attendance/today", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_today_view_returns_list(self, client, manager_token, sample_shift):
        rv = client.get("/hr/attendance/today", headers=auth(manager_token))
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Performance scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformance:
    def test_performance_endpoint(self, client, manager_token, waiter_profile):
        rv = client.get(f"/hr/performance/{waiter_profile.id}",
                        headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "composite_score" in data
        assert "detail" in data
        assert "weights" in data

    def test_performance_unknown_profile(self, client, manager_token):
        rv = client.get("/hr/performance/nonexistent-id", headers=auth(manager_token))
        assert rv.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 10. Payroll draft
# ══════════════════════════════════════════════════════════════════════════════

class TestPayrollDraft:
    def test_payroll_draft_returns_employees(self, client, manager_token, waiter_profile):
        rv = client.get("/hr/payroll-draft", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "employees" in data
        assert "period_start" in data

    def test_staff_cannot_see_payroll(self, client, waiter_token, waiter_profile):
        rv = client.get("/hr/payroll-draft", headers=auth(waiter_token))
        assert rv.status_code == 403


class TestWiFiUnconfiguredIsNamedHonestly:
    """An EMPTY allow-list and a WRONG network are the same 403 but not the
    same problem, and they are not fixed by the same person.

    is_ip_allowed() has no empty-list fallback (deliberate — see the module
    docstring), and @require_clocked_in guards 11 POS endpoints. So an empty
    list means nobody clocks in, which means no tabs, no orders and no
    payments. Telling that room to "connect to the staff network" sends a whole
    shift to look at a router while the actual fix is one owner-only row.
    """

    def _clear_allow_list(self, app):
        from app.extensions import db as _db
        from app.models.wifi_allow_list import WiFiAllowList
        with app.app_context():
            for w in _db.session.query(WiFiAllowList).all():
                _db.session.delete(w)
            _db.session.commit()

    def test_empty_list_says_nothing_is_configured(self, client, waiter_token, app):
        self._clear_allow_list(app)
        rv = client.post("/hr/clock-in", json={},
                         headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 403
        msg = rv.get_json()["error"]
        # Must name the real cause and who fixes it...
        assert "owner" in msg.lower()
        # ...and must NOT send them to the router.
        assert "connect to the staff network" not in msg.lower()

    def test_configured_but_wrong_network_still_says_connect(self, client, waiter_token, app):
        """With a network on file, the original message is the correct one."""
        from app.extensions import db as _db
        from app.models.wifi_allow_list import WiFiAllowList
        self._clear_allow_list(app)
        with app.app_context():
            # A range the test client's 127.0.0.1 is NOT in.
            _db.session.add(WiFiAllowList(ssid="Kurahia-Staff", ip_cidr="10.99.0.0/24", label="Resort staff"))
            _db.session.commit()
        rv = client.post("/hr/clock-in", json={},
                         headers={"Authorization": f"Bearer {waiter_token}"})
        assert rv.status_code == 403
        assert "staff network" in rv.get_json()["error"].lower()


def test_a_profile_photo_can_be_changed_not_just_set_once(client, manager_token, app):
    """photo_path was accepted on CREATE and ignored on PATCH, so a staff photo
    could be set at hire time and never corrected."""
    from app.extensions import db
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="waiter1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        rv = client.post("/hr/profiles", json={
            "user_id": u.id, "full_name": "Photo Test", "phone": "+254700999888",
        }, headers=auth(manager_token))
        assert rv.status_code == 201, rv.get_data(as_text=True)
        pid = rv.get_json()["id"]
    else:
        pid = prof.id

    rv = client.patch(f"/hr/profiles/{pid}", json={"photo_path": "/images/profiles/ab12.jpg"},
                      headers=auth(manager_token))
    assert rv.status_code == 200, rv.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(EmployeeProfile, pid).photo_path == "/images/profiles/ab12.jpg"

    # And it shows up on the staff LIST, which is what a roster with faces reads.
    rows = client.get("/hr/profiles", headers=auth(manager_token)).get_json()
    mine = [r for r in rows if r["id"] == pid][0]
    assert mine["photo_path"] == "/images/profiles/ab12.jpg"


def test_a_profile_photo_cannot_point_off_site(client, manager_token, app):
    """The value lands in an <img src>. Free text here would let somebody aim a
    staff photo at an external tracking pixel that fires every time a manager
    opens the roster — or at a javascript: scheme."""
    from app.extensions import db
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="waiter1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        prof = EmployeeProfile(user_id=u.id, full_name="Photo Test", phone="+254700999777")
        db.session.add(prof)
        db.session.commit()

    for bad in ("https://tracker.example.com/pixel.gif", "javascript:alert(1)",
                "//evil.example.com/x.png"):
        rv = client.patch(f"/hr/profiles/{prof.id}", json={"photo_path": bad},
                          headers=auth(manager_token))
        assert rv.status_code == 400, f"accepted {bad!r}"
        assert "uploaded image path" in rv.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════════
# Roster generation — the pattern is typed once, the shifts come from it
# ══════════════════════════════════════════════════════════════════════════════

def _patterned(profile, days="MON,TUE,WED,THU,FRI", start="08:00", end="17:00"):
    from app.extensions import db
    profile.roster_days, profile.roster_start, profile.roster_end = days, start, end
    db.session.commit()
    return profile


def test_a_week_of_shifts_is_generated_from_one_pattern(client, manager_token, app):
    """WAS THE PROBLEM: 14 staff x 6 days is 84 rows somebody types every Sunday,
    so nobody does, and the attendance board silently lists nobody."""
    from datetime import date
    from app.extensions import db
    from app.models.shift import Shift
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="waiter1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        prof = EmployeeProfile(user_id=u.id, full_name="Pattern Tester", phone="+254700111000")
        db.session.add(prof)
        db.session.commit()
    _patterned(prof)

    before = db.session.query(Shift).filter_by(employee_id=prof.id).count()
    rv = client.post("/hr/shifts/generate", json={"week_start": "2026-09-07"},
                     headers=auth(manager_token))
    assert rv.status_code == 200, rv.get_data(as_text=True)
    # Mon-Fri from one line of pattern
    assert rv.get_json()["created"] >= 5
    assert db.session.query(Shift).filter_by(employee_id=prof.id).count() == before + 5


def test_generating_the_same_week_twice_creates_nothing(client, manager_token, app):
    """Somebody will click it twice. That must not double the roster."""
    from app.extensions import db
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="waiter1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        prof = EmployeeProfile(user_id=u.id, full_name="Pattern Tester", phone="+254700111001")
        db.session.add(prof)
        db.session.commit()
    _patterned(prof)

    first = client.post("/hr/shifts/generate", json={"week_start": "2026-09-14"},
                        headers=auth(manager_token)).get_json()
    second = client.post("/hr/shifts/generate", json={"week_start": "2026-09-14"},
                         headers=auth(manager_token)).get_json()
    assert first["created"] > 0
    assert second["created"] == 0
    assert second["already_rostered"] >= first["created"]


def test_somebody_with_no_pattern_is_left_alone(client, manager_token, app):
    """Casuals and anyone whose days move around stay manual, on purpose."""
    from app.extensions import db
    from app.models.shift import Shift
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="staff1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        prof = EmployeeProfile(user_id=u.id, full_name="Casual Worker", phone="+254700111002")
        db.session.add(prof)
        db.session.commit()
    prof.roster_days = prof.roster_start = prof.roster_end = None
    db.session.commit()

    rv = client.post("/hr/shifts/generate", json={"week_start": "2026-09-21"},
                     headers=auth(manager_token))
    assert rv.status_code == 200
    assert rv.get_json()["no_pattern"] >= 1
    assert db.session.query(Shift).filter_by(employee_id=prof.id).count() == 0


def test_an_overnight_pattern_does_not_end_before_it_starts(client, manager_token, app):
    """The bar works 16:00 to 00:00 — that is eight hours into the next day, not
    minus eight hours on the same one."""
    from app.extensions import db
    from app.models.shift import Shift
    from app.models.user import User
    from app.models.employee_profile import EmployeeProfile

    u = db.session.query(User).filter_by(username="waiter1").first()
    prof = db.session.query(EmployeeProfile).filter_by(user_id=u.id).first()
    if prof is None:
        prof = EmployeeProfile(user_id=u.id, full_name="Night Bar", phone="+254700111003")
        db.session.add(prof)
        db.session.commit()
    _patterned(prof, days="MON", start="16:00", end="00:00")

    client.post("/hr/shifts/generate", json={"week_start": "2026-09-28"},
                headers=auth(manager_token))
    sh = (db.session.query(Shift).filter_by(employee_id=prof.id)
          .order_by(Shift.scheduled_start_utc.desc()).first())
    assert sh.scheduled_end_utc > sh.scheduled_start_utc
    hours = (sh.scheduled_end_utc - sh.scheduled_start_utc).total_seconds() / 3600
    assert 7.9 < hours < 8.1, f"an 8-hour night shift came out as {hours}h"


def test_a_waiter_cannot_generate_the_roster(client, waiter_token):
    rv = client.post("/hr/shifts/generate", json={"week_start": "2026-10-05"},
                     headers=auth(waiter_token))
    assert rv.status_code == 403
