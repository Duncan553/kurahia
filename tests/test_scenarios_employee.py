"""
tests/test_scenarios_employee.py — ADVERSARIAL scenarios for the EMPLOYEE / HR domain.

What this file is for: not "does the happy path work" (tests/test_hr.py already
covers that) but "does the system refuse the WRONG thing, and if it doesn't,
where exactly is the gap".

Reading guide for the names:
  test_*            — a property the system currently upholds. Regression guard.
  test_HOLE_*       — a gap. The assertion pins the CURRENT (permissive) behaviour
                      so the suite is green, and the docstring says what SHOULD
                      happen instead. When someone fixes the gap this test FAILS
                      on purpose — that is the signal to delete/flip it.

Domain covered: clock in/out + WiFi gate, the require_clocked_in POS gate,
shifts, leave, roster, attendance, performance/payroll, employee profiles,
account hierarchy, PINs/passwords, conduct signing.
"""
import uuid
from datetime import datetime, timezone, timedelta, date

import pytest

from app.extensions import db


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def auth(token):
    return {"Authorization": f"Bearer {token}"}


ON_NET  = {"REMOTE_ADDR": "127.0.0.1"}     # inside wifi_allowed's 127.0.0.0/8
OFF_NET = {"REMOTE_ADDR": "8.8.8.8"}       # outside it


def _user(username):
    from app.models.user import User
    return db.session.query(User).filter_by(username=username).first()


def _raw_login(client, username, password):
    """Token WITHOUT the conftest side-effect of creating a profile + clocking in.
    Needed whenever the scenario's premise is 'this person is not clocked in'."""
    rv = client.post("/auth/login", json={"username": username, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["access_token"]


def _add_clock_event(profile_id, event_type, when, shift_id=None):
    """Write a ClockEvent directly. Used only where the scenario needs events at
    specific times across a day — the HTTP endpoint always server-stamps `now`,
    which is correct, but makes a multi-hour scenario untestable through it.
    Field-for-field identical to what app/hr/clock.py writes."""
    from app.models.clock_event import ClockEvent
    ev = ClockEvent(
        employee_id=profile_id, event_type=event_type,
        occurred_at_utc=when, shift_id=shift_id,
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(ev)
    db.session.commit()
    return ev


def _add_shift(profile_id, start, end, creator_username="manager1", dept_id=None):
    from app.models.shift import Shift, ShiftStatus
    s = Shift(
        employee_id=profile_id,
        scheduled_start_utc=start, scheduled_end_utc=end,
        status=ShiftStatus.SCHEDULED.value,
        department_id=dept_id,
        created_by_id=_user(creator_username).id,
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(s)
    db.session.commit()
    return s


def _audit_actions():
    from app.models.audit_log import AuditLog
    db.session.expire_all()
    return [a.action for a in db.session.query(AuditLog).all()]


def _iso(dt):
    return dt.replace(tzinfo=None).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Clock-in and the WiFi gate
# ══════════════════════════════════════════════════════════════════════════════

class TestClockGate:

    def test_clock_in_from_ip_outside_allowlist_is_refused(
            self, client, waiter_token, waiter_profile, wifi_allowed):
        """BAD path: right person, wrong network."""
        rv = client.post("/hr/clock-in", json={}, headers=auth(waiter_token),
                         environ_base=OFF_NET)
        assert rv.status_code == 403
        assert "staff network" in rv.get_json()["error"]

    def test_empty_allowlist_names_the_real_cause(self, client, waiter_token, waiter_profile):
        """Regression guard on an already-fixed bug: with NO allow-list rows the
        refusal must blame the missing configuration, not the employee's phone."""
        rv = client.post("/hr/clock-in", json={}, headers=auth(waiter_token),
                         environ_base=ON_NET)
        assert rv.status_code == 403
        err = rv.get_json()["error"]
        assert "No staff network has been set up" in err
        assert "connect to the staff network" not in err

    def test_x_forwarded_for_cannot_spoof_the_wifi_gate(
            self, client, waiter_token, waiter_profile, wifi_allowed):
        """The gate reads request.remote_addr. With no trusted proxy hop configured
        (the default), a client-supplied X-Forwarded-For must not move the IP."""
        headers = auth(waiter_token)
        headers["X-Forwarded-For"] = "127.0.0.1"
        headers["X-Real-IP"] = "127.0.0.1"
        rv = client.post("/hr/clock-in", json={}, headers=headers, environ_base=OFF_NET)
        assert rv.status_code == 403

    def test_clock_in_without_an_employee_profile_is_refused(self, client, wifi_allowed):
        token = _raw_login(client, "chef1", "ChefPass1!")   # chef1 has no profile yet
        rv = client.post("/hr/clock-in", json={}, headers=auth(token), environ_base=ON_NET)
        assert rv.status_code == 403
        assert "profile" in rv.get_json()["error"].lower()

    def test_disabled_profile_cannot_clock_in(
            self, client, owner_token, waiter_profile, wifi_allowed):
        """Owner disables the profile → the cascade also kills the login account,
        so the still-valid JWT dies at the door."""
        waiter_tok = _raw_login(client, "waiter1", "WaiterPass1!")
        rv = client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        assert rv.status_code == 200
        rv = client.post("/hr/clock-in", json={}, headers=auth(waiter_tok), environ_base=ON_NET)
        assert rv.status_code == 403

    def test_staff_cannot_read_everyones_clock_events(
            self, client, waiter_token, waiter_profile):
        rv = client.get("/hr/clock-events", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_clock_events_bad_date_filter_is_plain_english(self, client, manager_token):
        rv = client.get("/hr/clock-events?date=01-01-2026", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "YYYY-MM-DD" in rv.get_json()["error"]

    def test_HOLE_clock_in_twice_is_accepted(
            self, client, waiter_token, waiter_profile, wifi_allowed):
        """HOLE. /hr/clock-in never asks 'are you already clocked in?'.

        Two calls with different idempotency keys both succeed and both become
        CLOCK_IN rows. SHOULD be a 409 telling the employee they are already on
        the clock (the idempotency key only catches an identical retry, not a
        second deliberate press).

        Consequence is measured in the two tests below: attendance counts and
        performance scores are driven by len(clock_ins).
        """
        a = client.post("/hr/clock-in", json={}, headers=auth(waiter_token), environ_base=ON_NET)
        b = client.post("/hr/clock-in", json={}, headers=auth(waiter_token), environ_base=ON_NET)
        assert a.status_code == 201
        assert b.status_code == 201                      # <-- should be 409
        assert a.get_json()["id"] != b.get_json()["id"]

    def test_HOLE_clock_out_without_ever_clocking_in_is_accepted(
            self, client, waiter_token, waiter_profile, wifi_allowed):
        """HOLE. A bare CLOCK_OUT with no open CLOCK_IN is written happily.
        SHOULD be refused ('you are not clocked in'). Mitigation that DOES hold:
        compute_hours_worked ignores an unpaired CLOCK_OUT, so it cannot be
        turned into paid hours — see the next test."""
        rv = client.post("/hr/clock-out", json={}, headers=auth(waiter_token),
                         environ_base=ON_NET)
        assert rv.status_code == 201                     # <-- should be 409

    def test_orphan_clock_out_earns_zero_hours(
            self, client, waiter_token, waiter_profile, wifi_allowed):
        """GOOD: the pairing logic refuses to pay for an unpaired CLOCK_OUT."""
        from app.services.hr import compute_hours_worked
        client.post("/hr/clock-out", json={}, headers=auth(waiter_token), environ_base=ON_NET)
        now = datetime.now(timezone.utc)
        hours = compute_hours_worked(waiter_profile.id, now - timedelta(days=1),
                                     now + timedelta(days=1))
        assert hours == 0

    def test_repeated_clock_ins_do_not_inflate_paid_hours(self, app, waiter_profile):
        """GOOD: IN, IN, OUT pays from the LATEST IN, not the earliest — the
        conservative direction. Verified against app/services/hr.py:161-171."""
        from app.services.hr import compute_hours_worked
        base = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
        _add_clock_event(waiter_profile.id, "CLOCK_IN",  base)
        _add_clock_event(waiter_profile.id, "CLOCK_IN",  base + timedelta(hours=4))
        _add_clock_event(waiter_profile.id, "CLOCK_OUT", base + timedelta(hours=6))
        hours = compute_hours_worked(waiter_profile.id, base - timedelta(days=1),
                                     base + timedelta(days=1))
        assert hours == 2       # not 6


# ══════════════════════════════════════════════════════════════════════════════
# 2. The require_clocked_in gate on POS
# ══════════════════════════════════════════════════════════════════════════════

class TestClockedInGate:

    def test_not_clocked_in_cannot_create_an_order(
            self, client, waiter_profile, food_item_id):
        """The whole point of the gate: no clock-in, no selling."""
        token = _raw_login(client, "waiter1", "WaiterPass1!")
        rv = client.post("/orders", json={
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        }, headers=auth(token))
        assert rv.status_code == 403
        assert "clock in" in rv.get_json()["error"].lower()

    def test_clocking_out_immediately_stops_selling(
            self, client, waiter_token, waiter_profile, wifi_allowed, food_item_id):
        """GOOD: the gate reads the LATEST event, so clock-out closes the till
        on the very next request."""
        rv = client.post("/hr/clock-out", json={}, headers=auth(waiter_token),
                         environ_base=ON_NET)
        assert rv.status_code == 201
        rv = client.post("/orders", json={
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_no_profile_at_all_cannot_sell(self, client, food_item_id):
        token = _raw_login(client, "chef1", "ChefPass1!")
        rv = client.post("/orders", json={
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        }, headers=auth(token))
        assert rv.status_code == 403
        assert "profile" in rv.get_json()["error"].lower()

    def test_manual_override_clock_in_re_opens_the_till(
            self, client, manager_token, waiter_profile, food_item_id):
        """GOOD path for the override: manager clocks a waiter in by hand (WiFi
        down), and the waiter can then sell. Confirms the gate reads the same
        ledger the override writes to."""
        token = _raw_login(client, "waiter1", "WaiterPass1!")
        rv = client.post("/orders", json={
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        }, headers=auth(token))
        assert rv.status_code == 403

        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "Router down at 6am",
        }, headers=auth(manager_token))
        assert rv.status_code == 201

        rv = client.post("/orders", json={
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        }, headers=auth(token))
        assert rv.status_code == 201


# ══════════════════════════════════════════════════════════════════════════════
# 3. Manual clock override
# ══════════════════════════════════════════════════════════════════════════════

class TestManualOverride:

    def test_manager_cannot_override_their_own_clock(
            self, client, manager_token, manager_profile):
        """Regression guard on an already-fixed bug: no 'I worked 4 extra hours'."""
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": manager_profile.id, "event_type": "CLOCK_IN",
            "reason": "I forgot",
        }, headers=auth(manager_token))
        assert rv.status_code == 403
        assert "your own" in rv.get_json()["error"]

    def test_override_reason_cannot_be_whitespace(
            self, client, manager_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "     ",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_override_of_unknown_employee_is_404(self, client, manager_token):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": "no-such-profile", "event_type": "CLOCK_IN",
            "reason": "test",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_override_of_disabled_employee_is_refused(
            self, client, owner_token, manager_token, waiter_profile):
        client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "sneaking a fired waiter back on the clock",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_override_rejects_a_made_up_event_type(
            self, client, manager_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_SIDEWAYS",
            "reason": "test",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_owner_may_override_a_manager(self, client, owner_token, manager_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": manager_profile.id, "event_type": "CLOCK_IN",
            "reason": "manager phone lost",
        }, headers=auth(owner_token))
        assert rv.status_code == 201

    def test_override_is_flagged_and_audited(self, client, manager_token, waiter_profile):
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "WiFi outage",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["is_manual_override"] is True
        assert "hr.manual_override" in _audit_actions()

    def test_HOLE_override_needs_no_wifi_and_no_second_signature(
            self, client, manager_token, waiter_profile):
        """HOLE (design-level, low severity). A manager sitting at home, off the
        hotel network, can put anyone on the clock: the override path skips
        is_ip_allowed entirely and needs no counter-signature. The audit log +
        is_manual_override flag are the only controls. SHOULD arguably also
        notify the owner, the way a password reset now does."""
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "from my sofa",
        }, headers=auth(manager_token), environ_base=OFF_NET)
        assert rv.status_code == 201


# ══════════════════════════════════════════════════════════════════════════════
# 4. Shifts
# ══════════════════════════════════════════════════════════════════════════════

class TestShifts:

    def _mk(self, client, token, profile_id, start, end, **extra):
        body = {"employee_id": profile_id,
                "scheduled_start_utc": _iso(start),
                "scheduled_end_utc":   _iso(end)}
        body.update(extra)
        return client.post("/hr/shifts", json=body, headers=auth(token))

    def test_overlap_by_one_minute_is_rejected(
            self, client, manager_token, waiter_profile, sample_shift):
        start = sample_shift.scheduled_end_utc - timedelta(minutes=1)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      start, start + timedelta(hours=8))
        assert rv.status_code == 409
        assert "already has a scheduled shift" in rv.get_json()["error"]

    def test_back_to_back_shifts_are_allowed(
            self, client, manager_token, waiter_profile, sample_shift):
        """GOOD: the conflict window is half-open, so end == next start is fine."""
        start = sample_shift.scheduled_end_utc
        rv = self._mk(client, manager_token, waiter_profile.id,
                      start, start + timedelta(hours=8))
        assert rv.status_code == 201

    def test_cancelled_shift_frees_the_slot(
            self, client, manager_token, waiter_profile, sample_shift):
        client.post(f"/hr/shifts/{sample_shift.id}/cancel", headers=auth(manager_token))
        rv = self._mk(client, manager_token, waiter_profile.id,
                      sample_shift.scheduled_start_utc, sample_shift.scheduled_end_utc)
        assert rv.status_code == 201

    def test_end_before_start_is_rejected(self, client, manager_token, waiter_profile):
        now = datetime.now(timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      now + timedelta(hours=8), now + timedelta(hours=1))
        assert rv.status_code == 400

    def test_zero_length_shift_is_rejected(self, client, manager_token, waiter_profile):
        now = datetime.now(timezone.utc) + timedelta(hours=3)
        rv = self._mk(client, manager_token, waiter_profile.id, now, now)
        assert rv.status_code == 400

    def test_shift_for_a_disabled_employee_is_refused(
            self, client, owner_token, manager_token, waiter_profile):
        client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        now = datetime.now(timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      now + timedelta(days=1), now + timedelta(days=1, hours=8))
        assert rv.status_code == 404

    def test_edit_cannot_create_a_conflict(
            self, client, manager_token, waiter_profile, sample_shift):
        start = sample_shift.scheduled_end_utc + timedelta(hours=1)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      start, start + timedelta(hours=4))
        second_id = rv.get_json()["id"]
        rv = client.patch(f"/hr/shifts/{second_id}", json={
            "scheduled_start_utc": _iso(sample_shift.scheduled_start_utc),
            "scheduled_end_utc":   _iso(sample_shift.scheduled_end_utc),
        }, headers=auth(manager_token))
        assert rv.status_code == 409

    def test_cancelled_shift_cannot_be_edited(
            self, client, manager_token, sample_shift):
        client.post(f"/hr/shifts/{sample_shift.id}/cancel", headers=auth(manager_token))
        rv = client.patch(f"/hr/shifts/{sample_shift.id}", json={
            "role_on_shift": "cashier"}, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_double_cancel_is_refused(self, client, manager_token, sample_shift):
        client.post(f"/hr/shifts/{sample_shift.id}/cancel", headers=auth(manager_token))
        rv = client.post(f"/hr/shifts/{sample_shift.id}/cancel", headers=auth(manager_token))
        assert rv.status_code == 400

    def test_staff_cannot_create_or_list_shifts(
            self, client, waiter_token, waiter_profile):
        now = datetime.now(timezone.utc)
        rv = self._mk(client, waiter_token, waiter_profile.id,
                      now + timedelta(days=1), now + timedelta(days=1, hours=8))
        assert rv.status_code == 403
        assert client.get("/hr/shifts", headers=auth(waiter_token)).status_code == 403

    def test_HOLE_shift_can_be_scheduled_entirely_in_the_past(
            self, client, manager_token, waiter_profile):
        """HOLE. Nothing rejects a shift that ended last year. A manager can
        back-date a roster after the fact — and because performance scoring
        counts shifts in the period (app/services/hr.py:209-214), inventing past
        shifts moves someone's attendance score retroactively.
        SHOULD refuse, or at minimum flag+audit a back-dated shift."""
        past = datetime(2020, 1, 1, 8, 0, tzinfo=timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      past, past + timedelta(hours=8))
        assert rv.status_code == 201                     # <-- should be 400

    def test_unknown_department_is_refused_in_plain_english(
            self, client, manager_token, waiter_profile):
        """WAS a HOLE, now fixed (app/hr/shifts.py). create_shift used to copy
        data['department_id'] straight onto the row with no lookup — unlike POST
        /hr/roster, which checks the department exists AND is active. That either
        died as a bare FOREIGN KEY error (a 500 with nothing readable in it) or,
        where the FK is not enforced, landed a shift pointing at nothing — which
        then never shows up under GET /hr/attendance/today?department_id=...
        Now it 404s with a readable reason, exactly like roster."""
        now = datetime.now(timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      now + timedelta(days=2), now + timedelta(days=2, hours=8),
                      department_id="not-a-real-department")
        assert rv.status_code == 404
        assert "Department not found" in rv.get_json()["error"]
        # And nothing was written — no dangling row left behind.
        from app.models.shift import Shift
        db.session.expire_all()
        assert db.session.query(Shift).filter_by(
            department_id="not-a-real-department").first() is None

    def test_shift_for_a_disabled_department_is_refused(
            self, client, manager_token, waiter_profile, app):
        """Same fix, the other half: a disabled department no longer takes shifts."""
        from app.models.department import Department
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        kitchen.is_active = False
        db.session.commit()
        now = datetime.now(timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      now + timedelta(days=3), now + timedelta(days=3, hours=8),
                      department_id=kitchen.id)
        assert rv.status_code == 404
        assert "disabled" in rv.get_json()["error"]

    def test_a_real_active_department_is_still_accepted(
            self, client, manager_token, waiter_profile, general_dept_id):
        """Guard on the fix above: the check must not reject the good case."""
        now = datetime.now(timezone.utc)
        rv = self._mk(client, manager_token, waiter_profile.id,
                      now + timedelta(days=4), now + timedelta(days=4, hours=8),
                      department_id=general_dept_id)
        assert rv.status_code == 201


# ══════════════════════════════════════════════════════════════════════════════
# 5. Leave
# ══════════════════════════════════════════════════════════════════════════════

class TestLeave:

    def _req(self, client, token, start, end, ltype="ANNUAL"):
        return client.post("/hr/leave-requests", json={
            "leave_type": ltype, "start_date": start, "end_date": end,
        }, headers=auth(token))

    def test_end_before_start_is_rejected(self, client, waiter_token, waiter_profile):
        rv = self._req(client, waiter_token, "2026-06-10", "2026-06-01")
        assert rv.status_code == 400

    def test_unknown_leave_type_is_rejected(self, client, waiter_token, waiter_profile):
        rv = self._req(client, waiter_token, "2026-06-01", "2026-06-02", ltype="SABBATICAL")
        assert rv.status_code == 400

    def test_manager_cannot_approve_own_leave(self, client, manager_token, manager_profile):
        rv = self._req(client, manager_token, "2026-06-01", "2026-06-02")
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_reject_own_leave(self, client, manager_token, manager_profile):
        rv = self._req(client, manager_token, "2026-06-01", "2026-06-02")
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/reject", headers=auth(manager_token))
        assert rv.status_code == 403

    def test_staff_cannot_approve_anyone(self, client, waiter_token, waiter_profile,
                                         manager_token, manager_profile):
        rv = self._req(client, manager_token, "2026-06-01", "2026-06-02")
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_approving_twice_is_refused(self, client, waiter_token, waiter_profile,
                                        manager_token):
        rv = self._req(client, waiter_token, "2026-06-01", "2026-06-02")
        lr_id = rv.get_json()["id"]
        assert client.post(f"/hr/leave-requests/{lr_id}/approve",
                           headers=auth(manager_token)).status_code == 200
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "already APPROVED" in rv.get_json()["error"]

    def test_rejected_leave_cannot_be_approved_afterwards(
            self, client, waiter_token, waiter_profile, manager_token):
        rv = self._req(client, waiter_token, "2026-06-01", "2026-06-02")
        lr_id = rv.get_json()["id"]
        client.post(f"/hr/leave-requests/{lr_id}/reject", headers=auth(manager_token))
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))
        assert rv.status_code == 400

    def test_employee_cannot_cancel_someone_elses_leave(
            self, client, waiter_token, waiter_profile, manager_token, manager_profile):
        rv = self._req(client, manager_token, "2026-07-01", "2026-07-02")
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/cancel", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_staff_only_sees_their_own_leave(
            self, client, waiter_token, waiter_profile, manager_token, manager_profile):
        self._req(client, manager_token, "2026-07-01", "2026-07-02")
        self._req(client, waiter_token, "2026-08-01", "2026-08-02")
        rows = client.get("/hr/leave-requests", headers=auth(waiter_token)).get_json()
        assert len(rows) == 1
        assert rows[0]["employee"] == waiter_profile.full_name

    def test_manager_sees_everyones_leave(
            self, client, waiter_token, waiter_profile, manager_token, manager_profile):
        self._req(client, manager_token, "2026-07-01", "2026-07-02")
        self._req(client, waiter_token, "2026-08-01", "2026-08-02")
        rows = client.get("/hr/leave-requests", headers=auth(manager_token)).get_json()
        assert len(rows) == 2

    def test_HOLE_leave_can_be_requested_for_dates_already_past(
            self, client, waiter_token, waiter_profile, manager_token):
        """HOLE. Nothing checks start_date against today. An employee who was a
        no-show last week can file leave for last week and a manager can approve
        it, which retroactively converts 'absent_no_notice' into 'approved_leave'
        in GET /hr/attendance/summary (app/services/hr.py:110-119 matches purely
        on the date range). SHOULD require manager+ for a back-dated request, or
        at least mark it as back-dated."""
        rv = self._req(client, waiter_token, "2020-01-01", "2020-01-03")
        assert rv.status_code == 201                     # <-- should be 400 for staff
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))
        assert rv.status_code == 200

        from app.services.hr import has_approved_leave
        assert has_approved_leave(waiter_profile.id, date(2020, 1, 2)) is True

    def test_HOLE_duplicate_overlapping_leave_requests_all_stand(
            self, client, waiter_token, waiter_profile, manager_token):
        """HOLE. Three IDENTICAL leave requests for the same two days are all
        created and all approvable — there is no overlap check anywhere in
        app/hr/leave.py. SHOULD be a 409 against an existing PENDING/APPROVED
        request covering the same dates.

        This is not cosmetic; see the next test for what it does to scoring."""
        ids = []
        for _ in range(3):
            rv = self._req(client, waiter_token, "2026-06-01", "2026-06-02")
            assert rv.status_code == 201                 # <-- should be 409 on #2 and #3
            ids.append(rv.get_json()["id"])
        for lr_id in ids:
            assert client.post(f"/hr/leave-requests/{lr_id}/approve",
                               headers=auth(manager_token)).status_code == 200

    def test_HOLE_stacked_leave_requests_wipe_out_the_attendance_score(
            self, client, waiter_token, waiter_profile, manager_token, app):
        """HOLE — the real damage from the two above, chained.

        compute_performance does `expected_shifts = max(len(shifts) -
        len(approved_leave), 0)` (app/services/hr.py:237). That subtracts the
        NUMBER OF LEAVE ROWS, not the number of days covered. So an employee who
        files the same single day off three times, gets all three approved, and
        then attends none of their three scheduled shifts scores 100/100 on
        attendance — the exact opposite of the truth.
        """
        from app.services.hr import compute_performance
        # The whole scenario sits in the FUTURE, starting tomorrow. That is not
        # cosmetic: the waiter_token fixture clocks waiter1 in at `now` as a side
        # effect (conftest._clock_in), and compute_performance counts every
        # clock-in inside the period. A period that reached back over today would
        # pick that stray event up and report shifts_attended=1, which is the
        # fixture leaking into the measurement, not the app scoring wrongly.
        base = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0)
        for d in range(3):
            _add_shift(waiter_profile.id,
                       (base + timedelta(days=d)).replace(tzinfo=None),
                       (base + timedelta(days=d, hours=8)).replace(tzinfo=None))

        the_day = (base + timedelta(days=1)).date().isoformat()
        for _ in range(3):
            rv = self._req(client, waiter_token, the_day, the_day)
            lr_id = rv.get_json()["id"]
            client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))

        period_start = base - timedelta(hours=1)   # starts after today's stray clock-in
        period_end   = base + timedelta(days=5)
        scores = compute_performance(waiter_profile.id,
                                     period_start.replace(tzinfo=None),
                                     period_end.replace(tzinfo=None))
        assert scores["detail"]["shifts_scheduled"] == 3
        assert scores["detail"]["shifts_attended"] == 0
        assert scores["attendance_score"] == "100"       # <-- should be 33.3 or lower

    def test_HOLE_a_manager_can_approve_the_owners_leave(
            self, client, owner_token, manager_token, app):
        """HOLE (hierarchy). Approval is gated on level >= 5 only; there is no
        'must outrank the requester' rule, unlike every account endpoint in
        app/auth/users.py. A manager can therefore sign off the owner's leave.
        Mirror-image of the same gap: two managers can approve each other's."""
        from app.models.employee_profile import EmployeeProfile
        owner_profile = db.session.query(EmployeeProfile).filter_by(
            user_id=_user("owner1").id).first()
        assert owner_profile is not None
        rv = self._req(client, owner_token, "2026-09-01", "2026-09-05")
        lr_id = rv.get_json()["id"]
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=auth(manager_token))
        assert rv.status_code == 200                     # <-- arguably should be 403


# ══════════════════════════════════════════════════════════════════════════════
# 6. Roster
# ══════════════════════════════════════════════════════════════════════════════

class TestRoster:

    def test_roster_overrides_the_home_department(
            self, client, manager_token, waiter_token, general_dept_id):
        """GOOD path: waiter1 lives in Front-of-House; rostered to General today."""
        before = client.get("/hr/roster/me", headers=auth(waiter_token)).get_json()
        assert before["is_rostered"] is False
        assert before["department"] == "Front-of-House"

        rv = client.post("/hr/roster", json={
            "user_id": _user("waiter1").id, "department_id": general_dept_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 200

        after = client.get("/hr/roster/me", headers=auth(waiter_token)).get_json()
        assert after["is_rostered"] is True
        assert after["department_id"] == general_dept_id

    def test_roster_to_a_disabled_department_is_refused(
            self, client, manager_token, app):
        from app.models.department import Department
        bar = db.session.query(Department).filter_by(name="Bar").first()
        bar.is_active = False
        db.session.commit()
        rv = client.post("/hr/roster", json={
            "user_id": _user("waiter1").id, "department_id": bar.id,
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_roster_of_a_deactivated_user_is_refused(
            self, client, owner_token, manager_token, general_dept_id):
        target = _user("waiter1")
        client.post(f"/auth/deactivate/{target.id}", headers=auth(owner_token))
        rv = client.post("/hr/roster", json={
            "user_id": target.id, "department_id": general_dept_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_re_rostering_the_same_day_updates_in_place(
            self, client, manager_token, general_dept_id, app):
        from app.models.station_roster import StationRoster
        from app.models.department import Department
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        uid = _user("waiter1").id
        for dept in (general_dept_id, kitchen.id):
            rv = client.post("/hr/roster", json={"user_id": uid, "department_id": dept},
                             headers=auth(manager_token))
            assert rv.status_code == 200
        db.session.expire_all()
        rows = db.session.query(StationRoster).filter_by(user_id=uid).all()
        assert len(rows) == 1
        assert rows[0].department_id == kitchen.id

    def test_staff_cannot_set_or_read_the_roster(self, client, waiter_token):
        assert client.post("/hr/roster", json={"user_id": "x", "department_id": "y"},
                           headers=auth(waiter_token)).status_code == 403
        assert client.get("/hr/roster", headers=auth(waiter_token)).status_code == 403

    def test_HOLE_a_manager_can_roster_the_owner(
            self, client, manager_token, general_dept_id, app):
        """HOLE (hierarchy, low severity). POST /hr/roster has no outranking
        check, so a manager can move the owner's station for the day. The roster
        governs which dashboard someone lands on, so this is a nuisance/confusion
        vector rather than a money one — but it is the same missing rule as the
        leave-approval gap above."""
        from app.models.department import Department
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        rv = client.post("/hr/roster", json={
            "user_id": _user("owner1").id, "department_id": kitchen.id,
        }, headers=auth(manager_token))
        assert rv.status_code == 200                     # <-- arguably should be 403


# ══════════════════════════════════════════════════════════════════════════════
# 7. Attendance
# ══════════════════════════════════════════════════════════════════════════════

class TestAttendance:

    def test_staff_cannot_see_the_attendance_board(self, client, waiter_token):
        for url in ("/hr/attendance/today", "/hr/attendance/summary"):
            assert client.get(url, headers=auth(waiter_token)).status_code == 403

    def test_staff_cannot_read_another_employees_attendance(
            self, client, waiter_token, manager_profile):
        rv = client.get(f"/hr/attendance/employee/{manager_profile.id}",
                        headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_no_show_shows_as_absent_no_notice(
            self, client, manager_token, waiter_profile, sample_shift):
        rows = client.get("/hr/attendance/today", headers=auth(manager_token)).get_json()
        mine = [r for r in rows if r["employee_id"] == waiter_profile.id]
        assert mine and mine[0]["status"] == "absent_no_notice"

    def test_approved_leave_flips_the_status(
            self, client, manager_token, waiter_token, waiter_profile, sample_shift):
        """Approved leave WINS over a clock event on the board — settled ordering.

        waiter1 is clocked in here (the waiter_token fixture does it), and the
        board used to check the clock first, so an approved leave day silently
        read as a normal working day. Leave is a decision a manager signed off;
        a clock-in is an event anyone on the staff WiFi can produce. Leave wins,
        and the contradiction is surfaced on its own flag rather than swallowed.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "SICK", "start_date": today, "end_date": today,
        }, headers=auth(waiter_token))
        client.post(f"/hr/leave-requests/{rv.get_json()['id']}/approve",
                    headers=auth(manager_token))
        rows = client.get("/hr/attendance/today", headers=auth(manager_token)).get_json()
        mine = [r for r in rows if r["employee_id"] == waiter_profile.id]
        assert mine and mine[0]["status"] == "approved_leave"
        # The stray clock event is not hidden — the manager can see the clash.
        assert mine[0]["clocked_in_while_on_leave"] is True

    def test_clock_in_while_on_approved_leave_is_allowed_but_flagged(
            self, client, manager_token, waiter_token, waiter_profile,
            wifi_allowed, sample_shift):
        """The other half of the rule, and a deliberate NON-block.

        Leave wins the STATUS, but it does not bar the door. Someone on leave
        coming in to cover a gap is ordinary at this resort, and a 403 at 6am
        with no manager on site strands a person who is standing at the post
        ready to work. So the clock-in succeeds, the board flags the clash for
        a manager to reconcile, and the hours still count for pay.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        rv = client.post("/hr/leave-requests", json={
            "leave_type": "SICK", "start_date": today, "end_date": today,
        }, headers=auth(waiter_token))
        client.post(f"/hr/leave-requests/{rv.get_json()['id']}/approve",
                    headers=auth(manager_token))

        # The front door stays open.
        rv = client.post("/hr/clock-in", json={}, headers=auth(waiter_token),
                         environ_overrides=ON_NET)
        assert rv.status_code == 201, rv.get_data(as_text=True)

        # ...but the contradiction is visible, not swallowed: leave still wins
        # the status, and the clash is raised for a manager to settle.
        rows = client.get("/hr/attendance/today",
                          headers=auth(manager_token)).get_json()
        mine = [r for r in rows if r["employee_id"] == waiter_profile.id]
        assert mine and mine[0]["status"] == "approved_leave"
        assert mine[0]["clocked_in_while_on_leave"] is True

        # The audited manual override remains available regardless.
        rv = client.post("/hr/clock-events/manual", json={
            "employee_id": waiter_profile.id, "event_type": "CLOCK_IN",
            "reason": "Called in to cover a no-show.",
        }, headers=auth(manager_token))
        assert rv.status_code == 201

    def test_absence_notice_must_be_for_your_own_shift(
            self, client, waiter_token, waiter_profile, manager_profile, app):
        """BAD path: you cannot file 'I'll be late' against somebody else's shift."""
        other = _add_shift(manager_profile.id,
                           datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2),
                           datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=10))
        rv = client.post("/hr/absence-notices", json={
            "notice_type": "LATE", "expected_shift_id": other.id,
        }, headers=auth(waiter_token))
        assert rv.status_code == 404

    def test_staff_only_see_their_own_absence_notices(
            self, client, waiter_token, waiter_profile, manager_token, manager_profile):
        client.post("/hr/absence-notices", json={"notice_type": "ABSENT"},
                    headers=auth(manager_token))
        client.post("/hr/absence-notices", json={"notice_type": "LATE"},
                    headers=auth(waiter_token))
        rows = client.get("/hr/absence-notices", headers=auth(waiter_token)).get_json()
        assert len(rows) == 1
        assert rows[0]["employee_id"] == waiter_profile.id

    def test_HOLE_staff_can_read_any_employees_absence_notices_by_query_param(
            self, client, waiter_token, waiter_profile, manager_token, manager_profile):
        """Checked and NOT a hole — recorded here because the endpoint takes an
        employee_id query param that looks exploitable. app/hr/absence.py:86-90
        overwrites employee_id with the caller's own profile before the query
        for anyone below manager, so the param is inert."""
        client.post("/hr/absence-notices", json={"notice_type": "ABSENT"},
                    headers=auth(manager_token))
        rows = client.get(f"/hr/absence-notices?employee_id={manager_profile.id}",
                          headers=auth(waiter_token)).get_json()
        assert all(r["employee_id"] == waiter_profile.id for r in rows)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Employee profiles — who may read and edit what
# ══════════════════════════════════════════════════════════════════════════════

class TestProfiles:

    def test_staff_cannot_read_another_employees_profile(
            self, client, waiter_token, manager_profile):
        rv = client.get(f"/hr/profiles/{manager_profile.id}", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_staff_cannot_list_all_profiles(self, client, waiter_token):
        assert client.get("/hr/profiles", headers=auth(waiter_token)).status_code == 403

    def test_staff_can_read_their_own_profile(self, client, waiter_token, waiter_profile):
        rv = client.get("/hr/profiles/me", headers=auth(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["id"] == waiter_profile.id
        # own /me view must not leak the wage
        assert "wage_rate" not in rv.get_json()

    def test_staff_cannot_edit_their_own_wage_through_the_payment_endpoint(
            self, client, waiter_token, waiter_profile):
        """GOOD: /hr/profiles/me/payment reads only two keys; extras are ignored."""
        rv = client.patch("/hr/profiles/me/payment", json={
            "payment_method": "MPESA", "payment_account_number": "+254700000001",
            "wage_rate": "999999", "hire_date": "2000-01-01",
        }, headers=auth(waiter_token))
        assert rv.status_code == 200
        db.session.expire_all()
        from app.models.employee_profile import EmployeeProfile
        p = db.session.get(EmployeeProfile, waiter_profile.id)
        assert p.wage_rate is None
        assert p.hire_date is None

    def test_staff_cannot_edit_their_own_profile_via_the_manager_endpoint(
            self, client, waiter_token, waiter_profile):
        rv = client.patch(f"/hr/profiles/{waiter_profile.id}", json={"wage_rate": "999999"},
                          headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_payment_account_number_never_reaches_the_audit_log(
            self, client, waiter_token, waiter_profile):
        from app.models.audit_log import AuditLog
        client.patch("/hr/profiles/me/payment", json={
            "payment_method": "MPESA", "payment_account_number": "254712345678",
        }, headers=auth(waiter_token))
        db.session.expire_all()
        blob = " ".join(f"{a.action}|{a.target}|{a.details}"
                        for a in db.session.query(AuditLog).all())
        assert "254712345678" not in blob

    def test_bad_payment_method_is_refused(self, client, waiter_token, waiter_profile):
        rv = client.patch("/hr/profiles/me/payment", json={
            "payment_method": "CRYPTO", "payment_account_number": "abc",
        }, headers=auth(waiter_token))
        assert rv.status_code == 400

    def test_profile_for_a_nonexistent_user_is_refused(self, client, manager_token):
        rv = client.post("/hr/profiles", json={
            "user_id": "ghost", "full_name": "Ghost", "phone": "+254700000000",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_manager_cannot_disable_a_profile(self, client, manager_token, waiter_profile):
        rv = client.post(f"/hr/profiles/{waiter_profile.id}/disable",
                         headers=auth(manager_token))
        assert rv.status_code == 403

    def test_HOLE_a_manager_can_raise_their_own_wage(
            self, client, manager_token, manager_profile):
        """HOLE — the sharpest one in this domain.

        PATCH /hr/profiles/<id> (app/hr/profiles.py:195-234) checks only
        `actor.role.level < MANAGER_LEVEL`. It never asks whether the profile
        being edited is the actor's own. A manager can therefore set their own
        wage_rate, and GET /hr/payroll-draft will duly report it.

        Compare app/hr/clock.py:183 (a manager may not override their own clock)
        and app/hr/leave.py:84 (may not approve their own leave) — the same
        self-dealing rule exists two files away, on smaller stakes.

        SHOULD refuse a self-edit of wage_rate/wage_period (owner-only), the way
        the clock override does.
        """
        rv = client.patch(f"/hr/profiles/{manager_profile.id}", json={
            "wage_rate": "999999", "wage_period": "HOURLY",
        }, headers=auth(manager_token))
        assert rv.status_code == 200                     # <-- should be 403

        rv = client.get("/hr/payroll-draft", headers=auth(manager_token))
        row = [r for r in rv.get_json()["employees"]
               if r["employee_id"] == manager_profile.id][0]
        assert row["wage_rate"].startswith("999999")

    def test_HOLE_a_manager_can_rewrite_the_owners_profile(
            self, client, owner_token, manager_token):
        """HOLE (hierarchy). Same missing check, pointed upward: no outranking
        rule on PATCH /hr/profiles/<id>, so a manager can edit the OWNER's
        name, phone, emergency contact and wage."""
        from app.models.employee_profile import EmployeeProfile
        owner_profile = db.session.query(EmployeeProfile).filter_by(
            user_id=_user("owner1").id).first()
        rv = client.patch(f"/hr/profiles/{owner_profile.id}", json={
            "full_name": "Definitely The Owner", "wage_rate": "1",
        }, headers=auth(manager_token))
        assert rv.status_code == 200                     # <-- should be 403
        db.session.expire_all()
        assert db.session.get(EmployeeProfile, owner_profile.id).full_name \
            == "Definitely The Owner"


# ══════════════════════════════════════════════════════════════════════════════
# 9. Performance and payroll
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformanceAndPayroll:

    def test_staff_cannot_read_anyones_performance(
            self, client, waiter_token, waiter_profile):
        rv = client.get(f"/hr/performance/{waiter_profile.id}", headers=auth(waiter_token))
        assert rv.status_code == 403      # not even their own

    def test_staff_cannot_read_the_payroll_draft(self, client, waiter_token):
        assert client.get("/hr/payroll-draft", headers=auth(waiter_token)).status_code == 403

    def test_payroll_draft_rejects_a_malformed_date(self, client, manager_token):
        rv = client.get("/hr/payroll-draft?start_date=June&end_date=2026-06-30",
                        headers=auth(manager_token))
        assert rv.status_code == 400
        assert "YYYY-MM-DD" in rv.get_json()["error"]

    def test_payroll_draft_omits_disabled_employees(
            self, client, owner_token, waiter_profile):
        rv = client.get("/hr/payroll-draft", headers=auth(owner_token))
        assert any(r["employee_id"] == waiter_profile.id
                   for r in rv.get_json()["employees"])
        client.post(f"/hr/profiles/{waiter_profile.id}/disable", headers=auth(owner_token))
        rv = client.get("/hr/payroll-draft", headers=auth(owner_token))
        assert not any(r["employee_id"] == waiter_profile.id
                       for r in rv.get_json()["employees"])

    def test_hours_worked_survives_a_clock_in_clock_out_pair(
            self, client, manager_token, waiter_profile, app):
        base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=5)
        _add_clock_event(waiter_profile.id, "CLOCK_IN",  base)
        _add_clock_event(waiter_profile.id, "CLOCK_OUT", base + timedelta(hours=4))

        # Query from the day the shift STARTED, not blindly from today. Between
        # midnight and 05:00 UTC "five hours ago" is yesterday, so asking for
        # today alone found the CLOCK_OUT with no CLOCK_IN and reported 0 hours
        # — a night-shift-shaped bug in the test that failed for the first five
        # hours of every day and passed the other nineteen.
        start = base.date().isoformat()
        today = datetime.now(timezone.utc).date().isoformat()
        rv = client.get(f"/hr/payroll-draft?start_date={start}&end_date={today}",
                        headers=auth(manager_token))
        row = [r for r in rv.get_json()["employees"]
               if r["employee_id"] == waiter_profile.id][0]
        assert float(row["hours_worked"]) == pytest.approx(4.0, abs=0.01)

    def test_payroll_draft_rejects_an_inverted_date_range(
            self, client, manager_token, waiter_profile):
        """WAS a HOLE, now fixed (app/hr/performance.py:_parse_period).

        _parse_period never checked that end >= start. Asking for 2026-06-30 →
        2026-06-01 returned 200 with every employee at 0.0 hours, which a payroll
        clerk reads as 'nobody worked' rather than 'your dates are backwards' —
        a silent wrong answer on the one screen that must never give one. Every
        other date input in this domain (shifts, leave) already refused an
        inverted range in plain English; now this does too.
        """
        rv = client.get("/hr/payroll-draft?start_date=2026-06-30&end_date=2026-06-01",
                        headers=auth(manager_token))
        assert rv.status_code == 400
        assert "on or after" in rv.get_json()["error"]

    def test_payroll_draft_accepts_a_single_day_period(
            self, client, manager_token, waiter_profile):
        """Guard on the fix above: start == end is one whole day, not an
        inverted range. The period end is exclusive, so it must not be refused."""
        today = datetime.now(timezone.utc).date().isoformat()
        rv = client.get(f"/hr/payroll-draft?start_date={today}&end_date={today}",
                        headers=auth(manager_token))
        assert rv.status_code == 200

    def test_performance_also_rejects_an_inverted_date_range(
            self, client, manager_token, waiter_profile):
        """Same helper, other endpoint — both call sites got the check."""
        rv = client.get(f"/hr/performance/{waiter_profile.id}"
                        "?start_date=2026-06-30&end_date=2026-06-01",
                        headers=auth(manager_token))
        assert rv.status_code == 400

    def test_HOLE_unscheduled_clock_ins_are_scored_as_punctual(
            self, client, manager_token, waiter_profile, app):
        """HOLE. compute_performance (app/services/hr.py:251-257) counts a
        clock-in with NO linked shift as on-time: `else: on_time += 1`.

        Since nothing stops an employee clocking in repeatedly (see
        test_HOLE_clock_in_twice_is_accepted), someone who turns up an hour late
        for their real shift can clock in a second time in the evening, outside
        the ±2h window of any shift, and drag their punctuality from 0% to 50%.

        Events are written directly here because the endpoint always stamps
        `now`, so a scenario spanning a working day cannot be driven over HTTP.
        SHOULD score an unlinked clock-in as neutral (excluded from the ratio),
        not as a point in the employee's favour.
        """
        from app.services.hr import compute_performance
        day = datetime(2026, 3, 2, tzinfo=timezone.utc)
        shift = _add_shift(waiter_profile.id,
                           (day + timedelta(hours=8)).replace(tzinfo=None),
                           (day + timedelta(hours=16)).replace(tzinfo=None))
        # One hour late for the real shift
        _add_clock_event(waiter_profile.id, "CLOCK_IN", day + timedelta(hours=9),
                         shift_id=shift.id)
        p_start = (day - timedelta(days=1)).replace(tzinfo=None)
        p_end   = (day + timedelta(days=2)).replace(tzinfo=None)
        before = compute_performance(waiter_profile.id, p_start, p_end)
        assert before["punctuality_score"] == "0.0"

        # A second, unscheduled clock-in at 22:00 — outside shift_end + 2h
        _add_clock_event(waiter_profile.id, "CLOCK_IN", day + timedelta(hours=22))
        after = compute_performance(waiter_profile.id, p_start, p_end)
        assert after["punctuality_score"] == "50.0"      # <-- should still be 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 10. WiFi allow-list
# ══════════════════════════════════════════════════════════════════════════════

class TestWiFiAllowList:

    def test_manager_cannot_touch_the_allow_list(self, client, manager_token, wifi_allowed):
        assert client.get("/hr/wifi", headers=auth(manager_token)).status_code == 403
        assert client.post("/hr/wifi", json={"ssid": "x", "ip_cidr": "10.0.0.0/8"},
                           headers=auth(manager_token)).status_code == 403
        assert client.post(f"/hr/wifi/{wifi_allowed.id}/disable",
                           headers=auth(manager_token)).status_code == 403

    def test_garbage_cidr_is_refused(self, client, owner_token):
        for bad in ("192.168.1.0/33", "not-an-ip", "192.168.1.0/24 OR 1=1", ""):
            rv = client.post("/hr/wifi", json={"ssid": "s", "ip_cidr": bad},
                             headers=auth(owner_token))
            assert rv.status_code == 400, bad

    def test_disabling_the_network_locks_everyone_out_immediately(
            self, client, owner_token, waiter_token, waiter_profile, wifi_allowed):
        """GOOD: the gate is evaluated per request, not cached."""
        assert client.post("/hr/clock-in", json={}, headers=auth(waiter_token),
                           environ_base=ON_NET).status_code == 201
        client.post(f"/hr/wifi/{wifi_allowed.id}/disable", headers=auth(owner_token))
        rv = client.post("/hr/clock-out", json={}, headers=auth(waiter_token),
                         environ_base=ON_NET)
        assert rv.status_code == 403

    def test_HOLE_owner_can_add_0_0_0_0_slash_0_and_void_the_geofence(
            self, client, owner_token, waiter_token, waiter_profile):
        """HOLE (config foot-gun). `0.0.0.0/0` is a syntactically valid CIDR, so
        _validate_cidr accepts it. One row and clock-in works from anywhere on
        earth — the on-site guarantee that the whole WiFi gate exists to provide
        is gone, with nothing in the response, the audit detail, or GET /hr/wifi
        saying so. SHOULD refuse a prefix that broad, or at minimum warn loudly
        in the response and the audit entry."""
        rv = client.post("/hr/wifi", json={"ssid": "anywhere", "ip_cidr": "0.0.0.0/0"},
                         headers=auth(owner_token))
        assert rv.status_code == 201                     # <-- should refuse or warn
        rv = client.post("/hr/clock-in", json={}, headers=auth(waiter_token),
                         environ_base={"REMOTE_ADDR": "203.0.113.9"})
        assert rv.status_code == 201


# ══════════════════════════════════════════════════════════════════════════════
# 11. Account hierarchy
# ══════════════════════════════════════════════════════════════════════════════

class TestHierarchy:

    def _role_id(self, name):
        from app.models.role import Role
        return db.session.query(Role).filter_by(name=name).first().id

    def test_manager_cannot_create_a_peer(self, client, manager_token, general_dept_id):
        rv = client.post("/auth/users", json={
            "username": "manager2", "password": "Whatever1!",
            "role_id": self._role_id("manager"), "department_id": general_dept_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_create_an_owner(self, client, manager_token, general_dept_id):
        rv = client.post("/auth/users", json={
            "username": "owner2", "password": "Whatever1!",
            "role_id": self._role_id("owner"), "department_id": general_dept_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_promote_a_staffer_to_manager(self, client, manager_token):
        rv = client.patch(f"/auth/users/{_user('waiter1').id}",
                          json={"role_id": self._role_id("manager")},
                          headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_promote_themselves(self, client, manager_token):
        rv = client.patch(f"/auth/users/{_user('manager1').id}",
                          json={"role_id": self._role_id("owner")},
                          headers=auth(manager_token))
        assert rv.status_code == 403
        assert "below your own role level" in rv.get_json()["error"]

    def test_manager_cannot_edit_the_owner(self, client, manager_token):
        rv = client.patch(f"/auth/users/{_user('owner1').id}",
                          json={"password": "NewOwnerPass1!"}, headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_deactivate_the_owner(self, client, manager_token):
        rv = client.post(f"/auth/deactivate/{_user('owner1').id}", headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_reset_their_own_lockout(self, client, manager_token):
        rv = client.post(f"/auth/reset-lockout/{_user('manager1').id}",
                         headers=auth(manager_token))
        assert rv.status_code == 403

    def test_manager_cannot_edit_another_manager(
            self, client, owner_token, manager_token, general_dept_id):
        rv = client.post("/auth/users", json={
            "username": "manager2", "password": "Manager2Pass1!",
            "role_id": self._role_id("manager"), "department_id": general_dept_id,
        }, headers=auth(owner_token))
        assert rv.status_code == 201
        peer_id = rv.get_json()["id"]
        rv = client.patch(f"/auth/users/{peer_id}", json={"password": "Hijacked1!"},
                          headers=auth(manager_token))
        assert rv.status_code == 403

    def test_password_reset_is_logged_as_its_own_action_and_wakes_the_owner(
            self, client, manager_token, app):
        """Regression guard on an already-fixed bug."""
        from app.models.audit_log import AuditLog
        from app.models.notification import Notification
        rv = client.patch(f"/auth/users/{_user('waiter1').id}",
                          json={"password": "ResetByManager1!"}, headers=auth(manager_token))
        assert rv.status_code == 200
        db.session.expire_all()
        rows = db.session.query(AuditLog).filter_by(action="user.password_reset").all()
        assert len(rows) == 1
        assert "PASSWORD RESET" in rows[0].details
        assert "ResetByManager1!" not in (rows[0].details or "")
        notes = db.session.query(Notification).filter(
            Notification.subject.like("Password reset%")).all()
        assert len(notes) == 1
        assert notes[0].recipient_user_id == _user("owner1").id

    def test_meta_only_offers_roles_you_may_actually_assign(self, client, manager_token):
        rv = client.get("/auth/users/meta", headers=auth(manager_token))
        names = {r["name"] for r in rv.get_json()["roles"]}
        assert "owner" not in names and "manager" not in names
        assert "staff" in names

    def test_self_registration_lands_inactive(self, client, general_dept_id):
        rv = client.post("/auth/register", json={
            "username": "walkin", "password": "WalkinPass1", "pin": "9876",
            "full_name": "Walk In", "phone": "+254711111111",
            "department_id": general_dept_id,
        })
        assert rv.status_code == 201
        rv = client.post("/auth/login", json={"username": "walkin", "password": "WalkinPass1"})
        assert rv.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 12. PINs and passwords
# ══════════════════════════════════════════════════════════════════════════════

class TestCredentials:

    def _new_user_without_pin(self, client, owner_token, general_dept_id, username="newbie"):
        from app.models.role import Role
        staff_role = db.session.query(Role).filter_by(name="staff").first()
        rv = client.post("/auth/users", json={
            "username": username, "password": "NewbiePass1!",
            "role_id": staff_role.id, "department_id": general_dept_id,
        }, headers=auth(owner_token))
        assert rv.status_code == 201
        assert rv.get_json()["pin_set"] is False
        return rv.get_json()["id"]

    def test_first_login_returns_a_setup_only_token_that_expires_in_10_minutes(
            self, client, owner_token, general_dept_id, app):
        from flask_jwt_extended import decode_token
        self._new_user_without_pin(client, owner_token, general_dept_id)
        rv = client.post("/auth/login", json={"username": "newbie", "password": "NewbiePass1!"})
        assert rv.get_json()["requires_pin_setup"] is True
        claims = decode_token(rv.get_json()["access_token"])
        assert claims["requires_pin_setup"] is True
        assert claims["exp"] - claims["iat"] == 600

    def test_setup_token_cannot_be_reused_to_set_a_second_pin(
            self, client, owner_token, general_dept_id):
        self._new_user_without_pin(client, owner_token, general_dept_id)
        rv = client.post("/auth/login", json={"username": "newbie", "password": "NewbiePass1!"})
        setup = rv.get_json()["access_token"]
        assert client.post("/auth/set-pin", json={"pin": "4242"},
                           headers=auth(setup)).status_code == 200
        # the SAME setup token still carries requires_pin_setup...
        rv = client.post("/auth/set-pin", json={"pin": "9999"}, headers=auth(setup))
        # ...documented below; the real tokens it issued do not.
        assert rv.status_code in (200, 400)

    def test_a_normal_token_cannot_call_set_pin(self, client, waiter_token):
        rv = client.post("/auth/set-pin", json={"pin": "4242"}, headers=auth(waiter_token))
        assert rv.status_code == 400
        assert "change-pin" in rv.get_json()["error"]

    def test_pin_login_refused_before_a_pin_exists(
            self, client, owner_token, general_dept_id):
        self._new_user_without_pin(client, owner_token, general_dept_id)
        rv = client.post("/auth/pin-login", json={"username": "newbie", "pin": "1234"})
        assert rv.status_code == 403

    def test_pin_must_be_four_plus_digits(self, client, owner_token, general_dept_id):
        self._new_user_without_pin(client, owner_token, general_dept_id)
        rv = client.post("/auth/login", json={"username": "newbie", "password": "NewbiePass1!"})
        setup = rv.get_json()["access_token"]
        for bad in ("12", "abcd", "12a4", ""):
            rv = client.post("/auth/set-pin", json={"pin": bad}, headers=auth(setup))
            assert rv.status_code == 400, bad

    def test_change_pin_needs_the_current_pin(self, client, waiter_token):
        rv = client.post("/auth/change-pin",
                         json={"current_pin": "0000", "new_pin": "7777"},
                         headers=auth(waiter_token))
        assert rv.status_code == 401
        # and the old PIN still works
        assert client.post("/auth/pin-login",
                           json={"username": "waiter1", "pin": "5555"}).status_code == 200

    def test_change_password_needs_the_current_password(self, client, waiter_token):
        rv = client.post("/auth/change-password",
                         json={"current_password": "wrong", "new_password": "Brandnew1!"},
                         headers=auth(waiter_token))
        assert rv.status_code == 401

    def test_HOLE_pin_guessing_via_change_pin_is_not_rate_limited_or_counted(
            self, client, waiter_token, app):
        """HOLE (needs an already-authenticated session, so: low severity).

        /auth/pin-login records a failed attempt and locks the account after N
        tries. /auth/change-pin (app/auth/routes.py:259-260) just returns 401 —
        no record_failed_attempt, no rate limit. Someone holding a borrowed
        unlocked tablet can brute-force the 4-digit PIN of the account already
        signed in on it without ever tripping the lockout that the login screen
        enforces. SHOULD call record_failed_attempt like pin_login does.
        """
        from app.models.user import User
        for guess in ("0000", "1234", "9999", "1111", "2222", "3333"):
            rv = client.post("/auth/change-pin",
                             json={"current_pin": guess, "new_pin": "8888"},
                             headers=auth(waiter_token))
            assert rv.status_code == 401
        db.session.expire_all()
        waiter = db.session.query(User).filter_by(username="waiter1").first()
        assert waiter.failed_attempts == 0                # <-- should have climbed
        assert waiter.is_active is True

    def test_HOLE_a_deactivated_account_can_still_finish_pin_setup(
            self, client, owner_token, general_dept_id, app):
        """HOLE (low severity). /auth/set-pin is guarded by @jwt_required only,
        not @require_active_user — the only endpoint in this domain that isn't.
        A user deactivated inside the 10-minute setup window can still spend
        their setup token to set a PIN AND be handed a full access+refresh
        token pair. Those tokens are inert (every protected endpoint re-checks
        is_active), so this is a hygiene gap rather than an open door — but it
        breaks invariant #7, 'kill switch on every protected endpoint'.
        """
        uid = self._new_user_without_pin(client, owner_token, general_dept_id)
        rv = client.post("/auth/login", json={"username": "newbie", "password": "NewbiePass1!"})
        setup = rv.get_json()["access_token"]

        assert client.post(f"/auth/deactivate/{uid}",
                           headers=auth(owner_token)).status_code == 200

        rv = client.post("/auth/set-pin", json={"pin": "4242"}, headers=auth(setup))
        assert rv.status_code == 200                      # <-- should be 403
        issued = rv.get_json()["access_token"]
        # The consolation prize: the token it hands out is dead on arrival.
        assert client.get("/hr/clock-status", headers=auth(issued)).status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 13. Conduct
# ══════════════════════════════════════════════════════════════════════════════

class TestConduct:

    def _publish(self, client, owner_token, key="no-theft", title="No theft", version_note="v"):
        return client.post("/conduct/rules", json={
            "rule_key": key, "title": title, "body": f"Do not steal. {version_note}",
            "category": "GENERAL",
        }, headers=auth(owner_token))

    def test_manager_cannot_publish_a_conduct_rule(self, client, manager_token):
        rv = self._publish(client, manager_token)
        assert rv.status_code == 403

    def test_rule_needs_a_real_category(self, client, owner_token):
        rv = client.post("/conduct/rules", json={
            "rule_key": "k", "title": "t", "body": "b", "category": "VIBES",
        }, headers=auth(owner_token))
        assert rv.status_code == 400

    def test_republishing_supersedes_the_previous_version(self, client, owner_token):
        v1 = self._publish(client, owner_token).get_json()
        v2 = self._publish(client, owner_token, version_note="v2").get_json()
        assert v1["version"] == 1 and v2["version"] == 2
        active = client.get("/conduct/rules", headers=auth(owner_token)).get_json()
        assert [r["id"] for r in active] == [v2["id"]]

    def test_signing_is_idempotent(self, client, owner_token, waiter_token, waiter_profile):
        rule = self._publish(client, owner_token).get_json()
        a = client.post("/conduct/sign", json={"conduct_rule_id": rule["id"]},
                        headers=auth(waiter_token))
        b = client.post("/conduct/sign", json={"conduct_rule_id": rule["id"]},
                        headers=auth(waiter_token))
        assert a.status_code == 201
        assert b.status_code == 200 and b.get_json()["duplicate"] is True

    def test_signing_an_unknown_rule_is_404(self, client, waiter_token, waiter_profile):
        rv = client.post("/conduct/sign", json={"conduct_rule_id": "nope"},
                         headers=auth(waiter_token))
        assert rv.status_code == 404

    def test_a_signature_cannot_be_filed_for_someone_else(
            self, client, owner_token, waiter_token, waiter_profile, manager_profile):
        """The signing endpoint takes no employee_id at all — it resolves the
        signer from the JWT. Confirmed by signing and checking whose row it is."""
        rule = self._publish(client, owner_token).get_json()
        client.post("/conduct/sign",
                    json={"conduct_rule_id": rule["id"], "employee_id": manager_profile.id},
                    headers=auth(waiter_token))
        from app.models.conduct_signature import ConductSignature
        db.session.expire_all()
        sigs = db.session.query(ConductSignature).all()
        assert len(sigs) == 1 and sigs[0].employee_id == waiter_profile.id

    def test_staff_reading_signatures_always_gets_their_own(
            self, client, owner_token, waiter_token, waiter_profile, manager_profile):
        rule = self._publish(client, owner_token).get_json()
        client.post("/conduct/sign", json={"conduct_rule_id": rule["id"]},
                    headers=auth(waiter_token))
        rows = client.get(f"/conduct/signatures/{manager_profile.id}",
                          headers=auth(waiter_token)).get_json()
        assert len(rows) == 1 and rows[0]["rule_key"] == "no-theft"

    def test_staff_cannot_read_the_compliance_report(self, client, waiter_token):
        assert client.get("/conduct/compliance", headers=auth(waiter_token)).status_code == 403

    def test_compliance_names_who_has_not_signed(
            self, client, owner_token, waiter_profile, manager_profile):
        rule = self._publish(client, owner_token).get_json()
        rows = client.get("/conduct/compliance", headers=auth(owner_token)).get_json()
        entry = [r for r in rows if r["rule_id"] == rule["id"]][0]
        assert waiter_profile.full_name in entry["unsigned_employees"]
        assert "haven't signed" in entry["message"]

    def test_HOLE_an_employee_can_sign_a_superseded_rule_version(
            self, client, owner_token, waiter_token, waiter_profile):
        """HOLE (low severity, but it makes a signature record misleading).
        POST /conduct/sign accepts ANY conduct_rule_id, including a version that
        was deactivated when v2 was published. The employee gets a 201 and a
        signature row that looks like compliance but isn't: the compliance
        report only counts signatures on the ACTIVE version, so they still show
        as unsigned. SHOULD refuse to sign an is_active=False rule and point at
        the current version."""
        v1 = self._publish(client, owner_token).get_json()
        self._publish(client, owner_token, version_note="v2")
        rv = client.post("/conduct/sign", json={"conduct_rule_id": v1["id"]},
                         headers=auth(waiter_token))
        assert rv.status_code == 201                      # <-- should be 400/409
        assert rv.get_json()["version"] == 1
        rows = client.get("/conduct/compliance", headers=auth(owner_token)).get_json()
        assert waiter_profile.full_name in rows[0]["unsigned_employees"]
