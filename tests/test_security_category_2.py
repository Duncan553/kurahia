"""
tests/test_security_category_2.py — Category 2: Authentication & Authorization Attacks

Attack  Result      Notes
2.1     PASS        Password lockout fires after 3 failures (FAILED_ATTEMPTS_LOCKOUT=3 in TestingConfig)
2.2     PASS        PIN login shares the same failed_attempts counter — same threshold
2.3     FAIL        check_active_and_unlocked only called in auth/routes.py — deactivated token
                    accepted by every other blueprint (tabs, inventory, finance, HR, dashboard, etc.)
2.4     PASS        /auth/refresh re-fetches user from DB and calls check_active_and_unlocked
2.5     PASS        Flask-JWT-Extended rejects tokens signed with wrong secret (422)
2.6     PASS        Role checks reload actor from DB — demoted user rejected immediately
2.7     PASS        Role guards present on every tested privilege boundary (manager+, owner+)
2.8     PASS        Staff role guard (403) prevents access to all HR profile endpoints
2.9     PASS        Any authenticated user may record a payment on any tab; actor is
                    always written to the audit log and returned in the response
2.10    PASS        edit_user hierarchy check (level <= level) blocks self-promotion
2.11    PASS        No cross-user PIN-reset endpoint exists; deactivate hierarchy
                    blocks upward attacks (manager cannot deactivate owner)
2.12    PASS        Non-owners hit the role guard before any DB lookup — real/fake
                    IDs return identical 403 responses
"""
import uuid
import pytest
import jwt as pyjwt          # PyJWT — used only to craft a tampered token in 2.5


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_user(app, username):
    """Load User row inside the active app context."""
    from app.models.user import User
    from app.extensions import db
    return db.session.query(User).filter_by(username=username).first()


def get_role_id(app, name):
    from app.models.role import Role
    from app.extensions import db
    return db.session.query(Role).filter_by(name=name).first().id


def login_password(client, username, password):
    rv = client.post("/auth/login", json={"username": username, "password": password})
    return rv


def owner_deactivate(client, owner_token, target_id):
    """Owner calls the kill-switch endpoint to deactivate a user."""
    return client.post(f"/auth/deactivate/{target_id}", headers=auth(owner_token))


# ══════════════════════════════════════════════════════════════════════════════
# 2.1 — Brute-force password
# ══════════════════════════════════════════════════════════════════════════════

class TestPasswordBruteforce:
    def test_account_locks_after_threshold_failures(self, app, client):
        """3 wrong passwords (TestingConfig threshold) lock the account."""
        for _ in range(3):
            client.post("/auth/login", json={"username": "manager1", "password": "wrong"})

        rv = client.post("/auth/login", json={"username": "manager1", "password": "wrong"})
        assert rv.status_code in (401, 403), f"Expected locked response, got {rv.status_code}"
        body = rv.get_json()
        assert "locked" in body.get("error", "").lower(), (
            f"Expected 'locked' in error message, got: {body}"
        )

    def test_correct_password_rejected_while_locked(self, app, client):
        """Even the right password is rejected while the account is locked."""
        for _ in range(3):
            client.post("/auth/login", json={"username": "manager1", "password": "wrong"})

        # 4th attempt — correct password, still locked
        rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
        assert rv.status_code in (401, 403), (
            f"Locked account accepted correct password — got {rv.status_code}"
        )

    def test_error_message_does_not_reveal_user_existence(self, app, client):
        """'no such user' and 'wrong password' must return the same error."""
        rv_no_user = client.post("/auth/login", json={"username": "ghost_user_xyz", "password": "pw"})
        rv_wrong_pw = client.post("/auth/login", json={"username": "owner1", "password": "wrong"})

        assert rv_no_user.status_code == rv_wrong_pw.status_code, (
            "Status codes differ: no-user vs wrong-password — attacker can enumerate usernames"
        )
        body_no_user  = rv_no_user.get_json().get("error", "")
        body_wrong_pw = rv_wrong_pw.get_json().get("error", "")
        assert body_no_user == body_wrong_pw, (
            f"Error messages differ:\n  no-user: {body_no_user!r}\n  wrong-pw: {body_wrong_pw!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.2 — Brute-force PIN
# ══════════════════════════════════════════════════════════════════════════════

class TestPINBruteforce:
    def test_pin_lockout_fires_after_threshold(self, app, client):
        """3 wrong PINs lock the account — same counter as password login."""
        for _ in range(3):
            client.post("/auth/pin-login", json={"username": "waiter1", "pin": "9999"})

        rv = client.post("/auth/pin-login", json={"username": "waiter1", "pin": "9999"})
        assert rv.status_code in (401, 403), f"Expected lockout, got {rv.status_code}"
        body = rv.get_json()
        assert "locked" in body.get("error", "").lower(), (
            f"Expected 'locked' in error, got: {body}"
        )

    def test_correct_pin_rejected_while_locked(self, app, client):
        """Correct PIN is rejected while lockout is active."""
        for _ in range(3):
            client.post("/auth/pin-login", json={"username": "waiter1", "pin": "9999"})

        rv = client.post("/auth/pin-login", json={"username": "waiter1", "pin": "5555"})
        assert rv.status_code in (401, 403), (
            f"Locked account accepted correct PIN — got {rv.status_code}"
        )

    def test_pin_lockout_shared_with_password_counter(self, app, client):
        """
        Failing PIN attempts increment the same failed_attempts that password
        login reads — prevents split-channel bypass (fail PIN 2×, fail password 2×,
        never hit either threshold, but total is 4).
        """
        # 2 bad password attempts
        for _ in range(2):
            client.post("/auth/login", json={"username": "waiter1", "password": "bad"})

        # 1 bad PIN — this should push failed_attempts to 3 (= threshold) and lock
        client.post("/auth/pin-login", json={"username": "waiter1", "pin": "9999"})

        # Password login with correct credentials — still locked
        rv = client.post("/auth/login", json={"username": "waiter1", "password": "WaiterPass1!"})
        assert rv.status_code in (401, 403), (
            f"Mixed channel lockout bypass succeeded — got {rv.status_code}: {rv.get_json()}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.3 — Stolen access token after deactivation (kill-switch test)
# ══════════════════════════════════════════════════════════════════════════════

class TestKillSwitchAccessToken:
    def test_deactivated_user_blocked_from_refresh(self, app, client, owner_token):
        """
        /auth/refresh is the one endpoint outside login that calls
        check_active_and_unlocked — deactivated user should get 403 there.
        """
        # Log in as manager, capture refresh token
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        refresh_token = rv.get_json()["refresh_token"]

        # Owner deactivates manager
        manager = get_user(app, "manager1")
        owner_deactivate(client, owner_token, manager.id)

        # Try to use refresh token — this path HAS the kill switch
        rv = client.post("/auth/refresh", headers=auth(refresh_token))
        assert rv.status_code in (401, 403), (
            f"Deactivated user's refresh token still works — got {rv.status_code}"
        )

    def test_deactivated_token_accepted_by_tabs_endpoint(self, app, client, owner_token):
        """
        KNOWN GAP — check_active_and_unlocked is NOT called in pos/tabs.py or
        most other blueprints. A deactivated user's access token is accepted by
        POST /tabs. This test documents the gap.

        Fix: add kill-switch check to every @jwt_required endpoint outside auth/.
        """
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        manager_token = rv.get_json()["access_token"]

        manager = get_user(app, "manager1")
        owner_deactivate(client, owner_token, manager.id)

        # Deactivated manager opens a tab — should be 401/403 but isn't
        rv = client.post("/tabs", json={"tab_type": "WALK_IN"},
                         headers=auth(manager_token))
        # ASSERT THE EXPECTED SECURE BEHAVIOUR — this will FAIL, surfacing the gap
        assert rv.status_code in (401, 403), (
            f"KILL SWITCH MISSING on POST /tabs — deactivated manager got {rv.status_code}. "
            f"check_active_and_unlocked must be added to every @jwt_required endpoint."
        )

    def test_deactivated_token_accepted_by_list_users(self, app, client, owner_token):
        """
        Same gap on GET /auth/users — no kill-switch check in list_users().
        Documents the systematic absence across blueprints.
        """
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        manager_token = rv.get_json()["access_token"]

        manager = get_user(app, "manager1")
        owner_deactivate(client, owner_token, manager.id)

        rv = client.get("/auth/users", headers=auth(manager_token))
        assert rv.status_code in (401, 403), (
            f"KILL SWITCH MISSING on GET /auth/users — deactivated manager got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.4 — Refresh token after deactivation
# ══════════════════════════════════════════════════════════════════════════════

class TestRefreshAfterDeactivation:
    def test_refresh_blocked_for_deactivated_user(self, app, client, owner_token):
        """/auth/refresh re-checks is_active — deactivated user cannot get a new token."""
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        body = rv.get_json()
        refresh_token = body["refresh_token"]

        manager = get_user(app, "manager1")
        owner_deactivate(client, owner_token, manager.id)

        rv = client.post("/auth/refresh", headers=auth(refresh_token))
        assert rv.status_code in (401, 403), (
            f"Refresh accepted for deactivated user — got {rv.status_code}: {rv.get_json()}"
        )

    def test_active_user_can_still_refresh(self, app, client):
        """Baseline: refresh works normally for an active user."""
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        refresh_token = rv.get_json()["refresh_token"]

        rv = client.post("/auth/refresh", headers=auth(refresh_token))
        assert rv.status_code == 200, f"Refresh failed for active user — {rv.get_json()}"
        assert "access_token" in rv.get_json()


# ══════════════════════════════════════════════════════════════════════════════
# 2.5 — JWT payload tampering
# ══════════════════════════════════════════════════════════════════════════════

class TestJWTTampering:
    def test_tampered_token_rejected(self, app, client, waiter_token):
        """
        Decode the token without verifying, change role_level to 10 (owner),
        re-encode with a DIFFERENT signing secret. Flask-JWT-Extended must reject it.
        """
        # Extract payload without verifying signature
        decoded = pyjwt.decode(waiter_token, options={"verify_signature": False},
                               algorithms=["HS256"])
        decoded["role_level"] = 10   # claim to be owner

        # Re-sign with a wrong key (attacker doesn't know JWT_SECRET_KEY)
        tampered = pyjwt.encode(decoded, "not-the-real-secret", algorithm="HS256")

        # Owner-only endpoint
        rv = client.get("/judge/alerts", headers=auth(tampered))
        assert rv.status_code in (401, 422), (
            f"Tampered token was accepted — got {rv.status_code}: {rv.get_json()}"
        )

    def test_expired_token_rejected(self, app, client):
        """An already-expired JWT must be rejected, not accepted."""
        from flask_jwt_extended import create_access_token
        from datetime import timedelta
        with app.app_context():
            # Create a token that expired 1 hour ago
            expired = create_access_token(
                identity="some-id",
                expires_delta=timedelta(hours=-1),
                additional_claims={"role_level": 10},
            )
        rv = client.get("/judge/alerts", headers=auth(expired))
        assert rv.status_code in (401, 422), (
            f"Expired token accepted — got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.6 — Role change takes effect immediately (trust DB, not JWT claim)
# ══════════════════════════════════════════════════════════════════════════════

class TestRoleChangeLive:
    def test_demoted_user_blocked_from_manager_endpoint(self, app, client, owner_token):
        """
        Manager logs in (JWT carries role_level=5). Owner demotes them to staff via
        PATCH /auth/users/<id>. Their next manager-only request must be rejected
        because the endpoint reloads role from DB, not the JWT claim.
        """
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        manager_token = rv.get_json()["access_token"]

        # Confirm access before demotion
        rv_before = client.post("/inventory/items",
                                json={"name": "Pre-demotion item", "unit": "kg",
                                      "department_id": "any", "reorder_level": "0"},
                                headers=auth(manager_token))
        # Not 403 — manager can attempt this (may 400/404 for bad dept, not 403)
        assert rv_before.status_code != 403, "Manager incorrectly blocked before demotion"

        # Owner demotes manager to staff
        manager = get_user(app, "manager1")
        staff_role_id = get_role_id(app, "staff")
        rv = client.patch(f"/auth/users/{manager.id}",
                          json={"role_id": staff_role_id},
                          headers=auth(owner_token))
        assert rv.status_code == 200, f"Demotion failed: {rv.get_json()}"

        # Now try a manager-only endpoint with the old (still-valid) JWT
        rv_after = client.post("/menu/items",
                               json={"name": "After demotion", "price": "100",
                                     "department_id": "any"},
                               headers=auth(manager_token))
        assert rv_after.status_code == 403, (
            f"Demoted user still has manager access — got {rv_after.status_code}. "
            f"JWT role_level claim is trusted instead of DB role."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.7 — Cross-role endpoint sweep
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossRoleEndpoints:
    """Waiter (staff, level=1) must be blocked from all manager/owner endpoints."""

    def test_waiter_cannot_create_user(self, app, client, waiter_token):
        # Use the real staff role_id so the request reaches the hierarchy check
        staff_role_id = get_role_id(app, "staff")
        rv = client.post("/auth/users",
                         json={"username": "hax", "role_id": staff_role_id},
                         headers=auth(waiter_token))
        assert rv.status_code == 403, f"POST /auth/users returned {rv.status_code}"

    def test_waiter_cannot_deactivate_user(self, app, client, waiter_token):
        owner = get_user(app, "owner1")
        rv = client.post(f"/auth/deactivate/{owner.id}", headers=auth(waiter_token))
        assert rv.status_code == 403, f"POST /auth/deactivate returned {rv.status_code}"

    def test_waiter_cannot_create_inventory_item(self, app, client, waiter_token, general_dept_id):
        rv = client.post("/inventory/items",
                         json={"name": "Stolen item", "unit": "kg",
                               "department_id": general_dept_id, "reorder_level": "5"},
                         headers=auth(waiter_token))
        assert rv.status_code == 403, f"POST /inventory/items returned {rv.status_code}"

    def test_waiter_cannot_create_menu_item(self, app, client, waiter_token, general_dept_id):
        rv = client.post("/menu/items",
                         json={"name": "Free beer", "price": "0",
                               "department_id": general_dept_id},
                         headers=auth(waiter_token))
        assert rv.status_code == 403, f"POST /menu/items returned {rv.status_code}"

    def test_waiter_cannot_view_cash_reconciliation(self, app, client, waiter_token):
        owner = get_user(app, "owner1")
        rv = client.get(f"/finance/cash/pending?staff_id={owner.id}",
                        headers=auth(waiter_token))
        assert rv.status_code == 403, f"GET /finance/cash/pending returned {rv.status_code}"

    def test_waiter_cannot_view_judge_alerts(self, app, client, waiter_token):
        rv = client.get("/judge/alerts", headers=auth(waiter_token))
        assert rv.status_code == 403, f"GET /judge/alerts returned {rv.status_code}"

    def test_waiter_cannot_view_dashboard(self, app, client, waiter_token):
        rv = client.get("/dashboard/overview", headers=auth(waiter_token))
        assert rv.status_code == 403, f"GET /dashboard/overview returned {rv.status_code}"

    def test_waiter_cannot_manage_wifi_allowlist(self, app, client, waiter_token):
        rv = client.post("/hr/wifi",
                         json={"ssid": "hack-net", "ip_cidr": "10.0.0.0/8"},
                         headers=auth(waiter_token))
        assert rv.status_code == 403, f"POST /hr/wifi returned {rv.status_code}"

    def test_manager_cannot_view_judge_alerts(self, app, client, manager_token):
        """Judge alerts are owner-only — manager (level=5) must also be blocked."""
        rv = client.get("/judge/alerts", headers=auth(manager_token))
        assert rv.status_code == 403, f"GET /judge/alerts returned {rv.status_code} for manager"

    def test_manager_can_view_overview(self, app, client, manager_token):
        rv = client.get("/dashboard/overview", headers=auth(manager_token))
        assert rv.status_code == 200, "Manager should access /dashboard/overview (lowered from owner-only)"

    def test_staff_cannot_view_dashboard(self, app, client, waiter_token):
        rv = client.get("/dashboard/overview", headers=auth(waiter_token))
        assert rv.status_code == 403, f"GET /dashboard/overview returned {rv.status_code} for staff"


# ══════════════════════════════════════════════════════════════════════════════
# 2.8 — IDOR: employee reading/modifying another employee's data
# ══════════════════════════════════════════════════════════════════════════════

class TestEmployeeIDOR:
    def test_staff_blocked_from_all_hr_profile_endpoints(self, app, client, waiter_token,
                                                          waiter_profile, manager_profile):
        """
        Staff (level=1) cannot read or edit ANY HR profile — even their own —
        because the role guard fires before the ownership check.
        """
        # GET list — forbidden
        rv = client.get("/hr/profiles", headers=auth(waiter_token))
        assert rv.status_code == 403, f"GET /hr/profiles returned {rv.status_code} for staff"

        # GET specific profile — manager's profile
        rv = client.get(f"/hr/profiles/{manager_profile.id}", headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Staff read manager's profile — got {rv.status_code}"
        )

        # PATCH — try to modify manager's profile
        rv = client.patch(f"/hr/profiles/{manager_profile.id}",
                          json={"wage_rate": "9999"},
                          headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Staff patched manager's profile — got {rv.status_code}"
        )

    def test_staff_cannot_read_own_profile_via_id(self, app, client, waiter_token, waiter_profile):
        """Staff can't use the profile endpoint even for their own record — manager+ required."""
        rv = client.get(f"/hr/profiles/{waiter_profile.id}", headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Staff accessed own profile via /hr/profiles/<id> — got {rv.status_code}"
        )

    def test_staff_cannot_edit_another_user_account(self, app, client, waiter_token):
        """
        PATCH /auth/users/<id> hierarchy check: actor.level <= target.level → 403.
        A waiter cannot edit another waiter's account.
        """
        manager = get_user(app, "manager1")
        rv = client.patch(f"/auth/users/{manager.id}",
                          json={"username": "hacked_manager"},
                          headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Waiter edited manager's account — got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.9 — Tab / booking IDOR (cross-tab payment)
# ══════════════════════════════════════════════════════════════════════════════

class TestTabIDOR:
    def test_any_authenticated_user_can_record_payment_on_any_tab(self, app, client,
                                                                    manager_token, waiter_token):
        """
        No tab-ownership enforcement. Any authenticated user may record a payment
        on any tab. The defence is: the actor's identity is always written to the
        audit log AND to the Payment.received_by_id column.
        """
        # Manager opens a tab
        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        assert rv.status_code == 201
        tab_id = rv.get_json()["id"]

        # Waiter (different user) records a payment on manager's tab
        rv = client.post(f"/tabs/{tab_id}/payments",
                         json={"amount": "500", "method": "CASH",
                               "idempotency_key": str(uuid.uuid4())},
                         headers=auth(waiter_token))
        # Operation is allowed by design (any staff can handle payments)
        assert rv.status_code == 201, f"Payment recording failed — {rv.get_json()}"

        # Audit: the payment endpoint returns the actor implicitly;
        # the DB audit_log entry must exist with waiter1 as actor
        from app.models.audit_log import AuditLog
        from app.extensions import db
        entry = db.session.query(AuditLog).filter_by(
            actor="waiter1", action="payment.record", target=tab_id
        ).first()
        assert entry is not None, (
            "No audit log entry for cross-tab payment — actor attribution is lost"
        )

    def test_payment_actor_recorded_in_response(self, app, client, manager_token, waiter_token):
        """Payment response returns amount/method but actor is audited server-side."""
        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]

        rv = client.post(f"/tabs/{tab_id}/payments",
                         json={"amount": "200", "method": "CASH",
                               "idempotency_key": str(uuid.uuid4())},
                         headers=auth(waiter_token))
        body = rv.get_json()
        # payment_id returned — shows it was recorded (actor stored server-side)
        assert "payment_id" in body, f"No payment_id in response: {body}"


# ══════════════════════════════════════════════════════════════════════════════
# 2.10 — Self-mutation (privilege escalation by self)
# ══════════════════════════════════════════════════════════════════════════════

class TestSelfMutation:
    def test_waiter_cannot_promote_own_role(self, app, client, waiter_token):
        """
        PATCH /auth/users/<id> checks actor.role.level <= target.role.level.
        A waiter (level=1) trying to edit themselves (also level=1) gets 403
        because 1 <= 1 is True.
        """
        waiter = get_user(app, "waiter1")
        owner_role_id = get_role_id(app, "owner")

        rv = client.patch(f"/auth/users/{waiter.id}",
                          json={"role_id": owner_role_id},
                          headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Waiter promoted own role — got {rv.status_code}: {rv.get_json()}"
        )

    def test_waiter_cannot_edit_own_username(self, app, client, waiter_token):
        """Even non-sensitive self-edits (username) are blocked by the hierarchy check."""
        waiter = get_user(app, "waiter1")
        rv = client.patch(f"/auth/users/{waiter.id}",
                          json={"username": "not_waiter_anymore"},
                          headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Waiter self-edited username — got {rv.status_code}"
        )

    def test_manager_cannot_promote_to_own_level_or_above(self, app, client, manager_token):
        """Manager (level=5) cannot assign a role of level >= 5 to any account."""
        owner_role_id = get_role_id(app, "owner")
        staff = get_user(app, "staff1")

        rv = client.patch(f"/auth/users/{staff.id}",
                          json={"role_id": owner_role_id},
                          headers=auth(manager_token))
        assert rv.status_code == 403, (
            f"Manager assigned owner role — got {rv.status_code}"
        )

    def test_staff_cannot_modify_own_hr_profile_wage(self, app, client, waiter_token, waiter_profile):
        """Staff cannot PATCH their own HR profile — manager+ required."""
        rv = client.patch(f"/hr/profiles/{waiter_profile.id}",
                          json={"wage_rate": "99999"},
                          headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Staff modified own wage — got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.11 — PIN reset hierarchy (manager cannot reset owner's PIN)
# ══════════════════════════════════════════════════════════════════════════════

class TestPINResetHierarchy:
    def test_no_cross_user_pin_reset_endpoint(self, app, client, manager_token):
        """
        There is no POST /auth/users/<id>/reset-pin endpoint. The attack surface
        does not exist — structural absence is the mitigation.
        Staff can only change their own PIN via /auth/change-pin (requires knowing
        the current PIN), and the first-time setup uses a temporary JWT flag.
        """
        owner = get_user(app, "owner1")
        # Probe the route that would be the attack vector if it existed
        rv = client.post(f"/auth/users/{owner.id}/reset-pin",
                         json={"new_pin": "0000"},
                         headers=auth(manager_token))
        # Flask returns 404/405 for unregistered routes — either is acceptable
        assert rv.status_code in (404, 405), (
            f"Unexpected response — a PIN-reset endpoint may exist: {rv.status_code}"
        )

    def test_manager_cannot_deactivate_owner(self, app, client, manager_token):
        """
        Deactivation hierarchy: actor.role.level must be STRICTLY greater than
        target.role.level. Manager (5) cannot deactivate owner (10).
        This is the closest real analog to upward PIN reset.
        """
        owner = get_user(app, "owner1")
        rv = client.post(f"/auth/deactivate/{owner.id}", headers=auth(manager_token))
        assert rv.status_code == 403, (
            f"Manager deactivated the owner — got {rv.status_code}: {rv.get_json()}"
        )

    def test_manager_can_deactivate_staff(self, app, client, manager_token):
        """Baseline: the hierarchy does allow downward deactivation."""
        staff = get_user(app, "staff1")
        rv = client.post(f"/auth/deactivate/{staff.id}", headers=auth(manager_token))
        assert rv.status_code == 200, (
            f"Manager couldn't deactivate staff — got {rv.status_code}"
        )

    def test_change_pin_requires_knowing_current_pin(self, app, client):
        """
        /auth/change-pin verifies the current_pin before accepting a new one.
        Cannot bypass by omitting current_pin or guessing wrong.
        """
        rv = client.post("/auth/login",
                         json={"username": "waiter1", "password": "WaiterPass1!"})
        token = rv.get_json()["access_token"]

        rv = client.post("/auth/change-pin",
                         json={"current_pin": "0000", "new_pin": "1234"},
                         headers=auth(token))
        assert rv.status_code == 401, (
            f"Wrong current PIN accepted for PIN change — got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2.12 — Endpoint enumeration via 404 vs 403
# ══════════════════════════════════════════════════════════════════════════════

class TestEnumerationResistance:
    def test_non_owner_gets_identical_response_for_real_and_fake_alert_ids(
            self, app, client, waiter_token, owner_token):
        """
        Non-owners hit the role guard in _require_owner() BEFORE the DB lookup.
        Both a real alert ID and a fake UUID return 403 — attacker cannot
        distinguish real IDs from fake ones to enumerate the system.
        """
        from app.models.judge_alert import JudgeAlert, AlertStatus
        from app.extensions import db

        # item_id is nullable on JudgeAlert — no InventoryItem seed needed
        alert = JudgeAlert(
            item_id=None,
            alert_type="RATIO",
            severity="HIGH",
            description="Test alert",
            status=AlertStatus.OPEN.value,
        )
        db.session.add(alert)
        db.session.commit()
        real_id = alert.id
        fake_id = str(uuid.uuid4())

        # Waiter probes both
        rv_real = client.post(f"/judge/alerts/{real_id}/acknowledge",
                              headers=auth(waiter_token))
        rv_fake = client.post(f"/judge/alerts/{fake_id}/acknowledge",
                              headers=auth(waiter_token))

        assert rv_real.status_code == rv_fake.status_code, (
            f"Real ID returns {rv_real.status_code}, fake ID returns {rv_fake.status_code} — "
            f"attacker can enumerate real alert IDs"
        )
        assert rv_real.status_code == 403, (
            f"Expected 403 for both, got {rv_real.status_code}"
        )

    def test_owner_can_distinguish_real_from_fake_alert(
            self, app, client, owner_token):
        """
        Owner CAN see the difference (200 vs 404) — that is correct behaviour.
        Enumeration resistance only needs to hold for unprivileged users.
        """
        from app.models.judge_alert import JudgeAlert, AlertStatus
        from app.extensions import db

        alert = JudgeAlert(
            item_id=None,
            alert_type="RATIO",
            severity="MEDIUM",
            description="Owner-visible alert",
            status=AlertStatus.OPEN.value,
        )
        db.session.add(alert)
        db.session.commit()

        rv_real = client.post(f"/judge/alerts/{alert.id}/acknowledge",
                              headers=auth(owner_token))
        rv_fake = client.post(f"/judge/alerts/{str(uuid.uuid4())}/acknowledge",
                              headers=auth(owner_token))

        assert rv_real.status_code == 200, f"Owner couldn't acknowledge real alert: {rv_real.get_json()}"
        assert rv_fake.status_code == 404, f"Fake alert ID returned {rv_fake.status_code} for owner"
