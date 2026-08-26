"""
tests/test_security_category_4.py — Category 4: Information Leaks

Pre-run predictions:
4.1  PARTIAL — messages identical ("Invalid credentials.") but timing oracle:
               no-user path skips Argon2.verify (~50-100ms saved) → username enumerable
4.2  PARTIAL — same timing leak as 4.1 for PIN login path
4.3  PARTIAL — 400/401/403/404 errors are clean {"error":"..."} JSON with no
               stack traces; no custom JSON 500 handler — unhandled exceptions
               return Flask's default HTML page in production mode
4.4  PASS    — invalid path params handled gracefully; no raw DB/SQLAlchemy error
               text exposed
4.5  PASS    — Suggestion OWNER_PRIVATE + Dispute is_owner_only both return
               structural 404 for non-owners; real and fake IDs indistinguishable
4.6  PASS    — HR profile 403 contains only {"error": "Manager or above required."}
4.7  PASS    — waiter 403'd before any booking data returned; authenticated list
               responses contain only legitimately-accessible rows
4.8  PASS    — /notifications/inbox filters by JWT identity (server-side);
               other users' notifications structurally absent
4.9  N/A     — audit log is CLI-only (audit_cli_bp registered); no HTTP endpoint
"""
import uuid
import time
import statistics
import pytest
from unittest.mock import patch


def auth(token):
    return {"Authorization": f"Bearer {token}"}


TIMING_GAP_THRESHOLD_MS = 50   # difference larger than this is a meaningful leak


# ══════════════════════════════════════════════════════════════════════════════
# 4.1  Username enumeration via login timing
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.production_hashing  # measures REAL Argon2 timing — see conftest.py
class TestUsernameEnumerationLogin:
    def _median_ms(self, client, url, payload, n=5) -> float:
        samples = []
        for _ in range(n):
            t0 = time.perf_counter()
            client.post(url, json=payload)
            samples.append((time.perf_counter() - t0) * 1000)
        return statistics.median(samples)

    def test_nonexistent_vs_wrong_password_same_message(self, app, client):
        """Both paths return identical message and status code."""
        rv_no_user   = client.post("/auth/login",
                                   json={"username": "ghost_xyz_999", "password": "any"})
        rv_wrong_pw  = client.post("/auth/login",
                                   json={"username": "owner1", "password": "wrong"})

        assert rv_no_user.status_code == rv_wrong_pw.status_code, (
            f"Status codes differ: no-user={rv_no_user.status_code}, "
            f"wrong-pw={rv_wrong_pw.status_code} — attacker can enumerate usernames"
        )
        body_no_user  = rv_no_user.get_json().get("error", "")
        body_wrong_pw = rv_wrong_pw.get_json().get("error", "")
        assert body_no_user == body_wrong_pw, (
            f"Error messages differ:\n  no-user: {body_no_user!r}\n"
            f"  wrong-pw: {body_wrong_pw!r} — attacker can enumerate usernames"
        )

    def test_nonexistent_vs_wrong_password_no_timing_leak(self, app, client):
        """
        Dummy Argon2.verify on the no-user path equalises timing.
        Both paths should now take ~same time (within 30% of each other).
        Argon2 has natural jitter — 30% tolerance avoids flakiness.
        """
        median_no_user  = self._median_ms(
            client, "/auth/login",
            {"username": "ghost_xyz_999", "password": "any"},
        )
        median_wrong_pw = self._median_ms(
            client, "/auth/login",
            {"username": "owner1", "password": "wrong_password"},
        )
        # Both paths must be within 30% of the slower one
        slower = max(median_no_user, median_wrong_pw)
        gap_ms = abs(median_wrong_pw - median_no_user)
        tolerance_ms = slower * 0.30
        assert gap_ms < tolerance_ms, (
            f"Timing still diverges after fix: no-user={median_no_user:.1f}ms, "
            f"wrong-pw={median_wrong_pw:.1f}ms, gap={gap_ms:.1f}ms, "
            f"tolerance={tolerance_ms:.1f}ms (30% of slower path). "
            "Dummy _ph.verify() may not be running."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4.2  PIN-login enumeration timing
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.production_hashing  # measures REAL Argon2 timing — see conftest.py
class TestPINLoginEnumeration:
    def _median_ms(self, client, url, payload, n=5) -> float:
        samples = []
        for _ in range(n):
            t0 = time.perf_counter()
            client.post(url, json=payload)
            samples.append((time.perf_counter() - t0) * 1000)
        return statistics.median(samples)

    def test_nonexistent_vs_wrong_pin_same_message(self, app, client):
        """Both paths return identical status and message."""
        rv_no_user  = client.post("/auth/pin-login",
                                  json={"username": "ghost_xyz_999", "pin": "0000"})
        rv_wrong_pin = client.post("/auth/pin-login",
                                   json={"username": "waiter1", "pin": "9999"})

        assert rv_no_user.status_code == rv_wrong_pin.status_code, (
            f"Status codes differ: no-user={rv_no_user.status_code}, "
            f"wrong-pin={rv_wrong_pin.status_code}"
        )
        assert rv_no_user.get_json().get("error") == rv_wrong_pin.get_json().get("error"), (
            f"Error messages differ:\n  no-user: {rv_no_user.get_json()!r}\n"
            f"  wrong-pin: {rv_wrong_pin.get_json()!r}"
        )

    def test_nonexistent_vs_wrong_pin_no_timing_leak(self, app, client):
        """
        Dummy Argon2.verify on the no-user PIN path equalises timing.
        Within 30% tolerance to account for Argon2 natural jitter.
        """
        median_no_user  = self._median_ms(
            client, "/auth/pin-login",
            {"username": "ghost_xyz_999", "pin": "0000"},
        )
        median_wrong_pin = self._median_ms(
            client, "/auth/pin-login",
            {"username": "waiter1", "pin": "9999"},
        )
        slower = max(median_no_user, median_wrong_pin)
        gap_ms = abs(median_wrong_pin - median_no_user)
        tolerance_ms = slower * 0.30
        assert gap_ms < tolerance_ms, (
            f"Timing still diverges: no-user={median_no_user:.1f}ms, "
            f"wrong-pin={median_wrong_pin:.1f}ms, gap={gap_ms:.1f}ms, "
            f"tolerance={tolerance_ms:.1f}ms (30% of slower path)."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4.3  Stack trace leak in error responses
# ══════════════════════════════════════════════════════════════════════════════

STACK_TRACE_MARKERS = ["Traceback", "File \"/", "line ", "KeyError", "AttributeError",
                       "TypeError", "sqlalchemy", "flask", "werkzeug"]


class TestStackTraceLeak:
    def test_400_errors_contain_no_stack_trace(self, app, client, manager_token):
        """Malformed / invalid requests return clean {"error":"..."} with no internals."""
        cases = [
            # Missing required fields
            ("/auth/login",            "POST", {}),
            ("/tabs",                  "POST", {"tab_type": "INVALID_TYPE"}, manager_token),
            ("/inventory/movements/spoilage", "POST", {"quantity": "abc"}, manager_token),
        ]
        for case in cases:
            url, method = case[0], case[1]
            payload = case[2] if len(case) > 2 else {}
            token   = case[3] if len(case) > 3 else None
            headers = auth(token) if token else {}

            rv = client.post(url, json=payload, headers=headers)
            body = rv.get_data(as_text=True)
            for marker in STACK_TRACE_MARKERS:
                assert marker not in body, (
                    f"Stack trace marker {marker!r} found in {url} response: {body[:200]}"
                )
            # Must be JSON {"error": "..."}
            assert rv.is_json, f"{url} returned non-JSON response: {body[:100]}"
            assert "error" in rv.get_json(), f"{url} missing 'error' key: {rv.get_json()}"

    def test_404_contains_no_stack_trace(self, app, client, manager_token):
        """GET of non-existent resource returns clean {"error":"..."} JSON."""
        rv = client.get(f"/tabs/{uuid.uuid4()}", headers=auth(manager_token))
        body = rv.get_data(as_text=True)
        assert rv.status_code == 404
        for marker in STACK_TRACE_MARKERS:
            assert marker not in body, (
                f"Stack trace marker {marker!r} in 404 response: {body[:200]}"
            )

    def test_500_returns_json_not_html(self, app, client, manager_token):
        """
        @app.errorhandler(Exception) now catches unhandled errors.
        500 must return JSON {"error": ..., "message": ...}, no stack trace,
        no Flask HTML page.
        """
        app.config["TESTING"] = False
        app.config["PROPAGATE_EXCEPTIONS"] = False
        try:
            with patch("app.auth.routes.check_active_and_unlocked",
                       side_effect=RuntimeError("simulated server fault")):
                rv = client.post("/auth/login",
                                 json={"username": "manager1",
                                       "password": "ManagerPass1!"})

            assert rv.status_code == 500, f"Expected 500, got {rv.status_code}"

            # Must be JSON
            assert rv.is_json, (
                f"500 response is not JSON: {rv.get_data(as_text=True)[:200]}"
            )
            body = rv.get_json()
            assert "error" in body,   f"Missing 'error' key in 500 JSON: {body}"
            assert "message" in body, f"Missing 'message' key in 500 JSON: {body}"

            # No internal details in body
            body_str = rv.get_data(as_text=True)
            for marker in ["Traceback", "File \"/", "RuntimeError",
                           "simulated server fault", "werkzeug"]:
                assert marker not in body_str, (
                    f"Sensitive marker {marker!r} leaked in 500 response: {body_str[:300]}"
                )
        finally:
            app.config["TESTING"] = True
            app.config["PROPAGATE_EXCEPTIONS"] = True


# ══════════════════════════════════════════════════════════════════════════════
# 4.4  Database error leak
# ══════════════════════════════════════════════════════════════════════════════

DB_ERROR_MARKERS = ["IntegrityError", "OperationalError", "psycopg2",
                    "sqlite3", "column", "relation", "syntax error",
                    "UNIQUE constraint", "NOT NULL constraint"]


class TestDatabaseErrorLeak:
    def test_invalid_uuid_path_param_returns_404_not_db_error(self, app, client, manager_token):
        """Non-UUID / garbage path params handled gracefully — no raw DB errors."""
        bad_ids = [
            "' OR 1=1 --",
            "not-a-uuid",
            "a" * 1000,
            "../../../etc/passwd",
        ]
        endpoints = [
            "/tabs/{}",
            "/bookings/{}",
        ]
        for endpoint in endpoints:
            for bad_id in bad_ids:
                rv = client.get(endpoint.format(bad_id), headers=auth(manager_token))
                body = rv.get_data(as_text=True)
                assert rv.status_code in (400, 404, 405), (
                    f"{endpoint.format(bad_id)} returned {rv.status_code}: {body[:100]}"
                )
                for marker in DB_ERROR_MARKERS:
                    assert marker not in body, (
                        f"DB error marker {marker!r} leaked for bad id {bad_id!r}: {body[:200]}"
                    )

    def test_invalid_integer_path_param_returns_404(self, app, client, manager_token):
        """/gate/deactivate-band/<int:n> rejects non-integers at routing level."""
        rv = client.post("/gate/deactivate-band/not-a-number",
                         headers=auth(manager_token))
        # Flask returns 404 when route type conversion fails
        assert rv.status_code == 404, (
            f"Expected 404 for non-integer band number, got {rv.status_code}"
        )
        body = rv.get_data(as_text=True)
        for marker in DB_ERROR_MARKERS:
            assert marker not in body, f"DB marker {marker!r} in routing error: {body[:200]}"


# ══════════════════════════════════════════════════════════════════════════════
# 4.5  OWNER_PRIVATE 404 / 403 consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestOwnerPrivateConsistency:
    def test_suggestion_owner_private_indistinguishable_for_manager(
            self, app, client, manager_token, owner_token):
        """
        Manager cannot tell real OWNER_PRIVATE suggestion ID from fake ID.
        Both return 404 with identical body.
        """
        # Create an OWNER_PRIVATE suggestion as owner
        rv = client.post("/suggestions",
                         json={"category": "OWNER_PRIVATE",
                               "subject": "Secret suggestion",
                               "body": "Private content",
                               "idempotency_key": str(uuid.uuid4())},
                         headers=auth(owner_token))
        assert rv.status_code == 201, f"Suggestion create failed: {rv.get_json()}"
        real_id = rv.get_json()["id"]
        fake_id = str(uuid.uuid4())

        rv_real = client.get(f"/suggestions/{real_id}", headers=auth(manager_token))
        rv_fake = client.get(f"/suggestions/{fake_id}", headers=auth(manager_token))

        assert rv_real.status_code == 404, (
            f"Manager got {rv_real.status_code} on real OWNER_PRIVATE suggestion — "
            f"should be structural 404: {rv_real.get_json()}"
        )
        assert rv_fake.status_code == 404
        assert rv_real.get_json() == rv_fake.get_json(), (
            f"Bodies differ — real: {rv_real.get_json()}, fake: {rv_fake.get_json()}"
        )

    def test_dispute_owner_only_indistinguishable_for_manager(
            self, app, client, manager_token):
        """
        Manager cannot tell real is_owner_only dispute from fake ID.
        _get_dispute_visible() returns None for both — both yield 404.
        """
        from app.models.dispute import Dispute, DisputeCategory
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        from app.extensions import db

        # Dispute.reporter_employee_id is FK to employee_profiles (not users)
        owner = db.session.query(User).filter_by(username="owner1").first()
        profile = EmployeeProfile(user_id=owner.id, full_name="Owner Profile",
                                  phone="+254700000099")
        db.session.add(profile)
        db.session.flush()

        dispute = Dispute(
            reporter_employee_id=profile.id,
            category=DisputeCategory.OTHER.value,
            description="Owner-only private dispute",
            priority="MEDIUM",
            is_owner_only=True,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(dispute)
        db.session.commit()
        real_id = dispute.id
        fake_id = str(uuid.uuid4())

        rv_real = client.post(f"/disputes/{real_id}/claim",
                              headers=auth(manager_token))
        rv_fake = client.post(f"/disputes/{fake_id}/claim",
                              headers=auth(manager_token))

        assert rv_real.status_code == 404, (
            f"Manager got {rv_real.status_code} for real owner-only dispute — "
            "should be structural 404"
        )
        assert rv_fake.status_code == 404
        assert rv_real.get_json() == rv_fake.get_json(), (
            f"Bodies differ — real: {rv_real.get_json()}, fake: {rv_fake.get_json()}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4.6  IDOR response shape — 403 leaks no target user data
# ══════════════════════════════════════════════════════════════════════════════

class TestIDORResponseShape:
    def test_hr_profile_403_contains_no_target_data(
            self, app, client, waiter_token, manager_profile):
        """
        Waiter hits role guard on GET /hr/profiles/<id>. The 403 response must
        not contain any data about the target employee (name, role, phone, etc.).
        """
        rv = client.get(f"/hr/profiles/{manager_profile.id}",
                        headers=auth(waiter_token))
        assert rv.status_code == 403
        body = rv.get_json()

        # These strings should not appear in the 403 body
        sensitive_fragments = [
            "Test Manager",       # manager_profile.full_name from conftest
            "manager1",           # username
            "+254700000002",      # phone from conftest
            manager_profile.id,   # profile ID
        ]
        body_str = str(body)
        for fragment in sensitive_fragments:
            assert fragment not in body_str, (
                f"403 response leaked target user data {fragment!r}: {body}"
            )
        # Must be a single plain-English error
        assert "error" in body
        assert len(body) == 1, f"403 response has extra keys beyond 'error': {body}"


# ══════════════════════════════════════════════════════════════════════════════
# 4.7  Listing endpoint access control
# ══════════════════════════════════════════════════════════════════════════════

class TestListingEndpointLeak:
    def test_waiter_gets_403_on_bookings_list_with_no_data(self, app, client, waiter_token):
        """
        GET /bookings requires FRONT_DESK_LEVEL=3. Waiter (level=1) gets 403
        with no booking data in the body.
        """
        rv = client.get("/bookings", headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Waiter accessed booking list — got {rv.status_code}: {rv.get_json()}"
        )
        body = rv.get_json()
        # Response must be only {"error": "..."} — no booking rows
        assert "error" in body
        assert "id" not in str(body), "Booking data leaked in 403 response"
        assert "guest_name" not in str(body), "Guest data leaked in 403 response"

    def test_manager_booking_list_contains_only_real_bookings(
            self, app, client, manager_token):
        """
        GET /bookings for an authorized manager returns only bookings that
        actually exist — no phantom rows, no cross-user injection.
        """
        from app.models.booking import Booking
        from app.extensions import db

        db_count = db.session.query(Booking).count()
        rv = client.get("/bookings", headers=auth(manager_token))
        assert rv.status_code == 200
        api_count = len(rv.get_json())
        assert api_count == db_count, (
            f"API returned {api_count} bookings but DB has {db_count} — "
            "listing endpoint is either leaking or hiding rows"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4.8  Notification cross-user leak
# ══════════════════════════════════════════════════════════════════════════════

class TestNotificationCrossUserLeak:
    def test_inbox_shows_only_own_notifications(self, app, client, manager_token, waiter_token):
        """
        Manager's notification is not visible in waiter's inbox.
        inbox() filters strictly by recipient_user_id = get_jwt_identity().
        """
        from app.models.notification import Notification, NotificationStatus
        from app.models.user import User
        from app.extensions import db

        manager = db.session.query(User).filter_by(username="manager1").first()
        waiter  = db.session.query(User).filter_by(username="waiter1").first()

        from app.models.notification import NotificationReferenceType
        from datetime import timezone
        # Seed a notification for manager only
        notif = Notification(
            recipient_user_id=manager.id,
            reference_type=NotificationReferenceType.GENERAL.value,
            subject="Manager secret",
            body="Only for manager",
            status=NotificationStatus.DELIVERED.value,
            channel="IN_APP",
            scheduled_for_utc=__import__("datetime").datetime.now(timezone.utc),
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(notif)
        db.session.commit()

        # Manager sees their notification
        rv_manager = client.get("/notifications/inbox", headers=auth(manager_token))
        assert rv_manager.status_code == 200
        manager_ids = {n["id"] for n in rv_manager.get_json()}
        assert notif.id in manager_ids, "Manager's own notification not in inbox"

        # Waiter's inbox is empty (or contains only their own)
        rv_waiter = client.get("/notifications/inbox", headers=auth(waiter_token))
        assert rv_waiter.status_code == 200
        waiter_ids = {n["id"] for n in rv_waiter.get_json()}
        assert notif.id not in waiter_ids, (
            f"Manager's notification {notif.id!r} appeared in waiter's inbox — "
            "cross-user notification leak"
        )

    def test_mark_read_rejects_cross_user_access(self, app, client, manager_token, waiter_token):
        """
        Waiter cannot mark manager's notification as read — ownership check fires.
        """
        from app.models.notification import Notification, NotificationStatus
        from app.models.user import User
        from app.extensions import db

        manager = db.session.query(User).filter_by(username="manager1").first()
        from app.models.notification import NotificationReferenceType
        from datetime import timezone
        notif = Notification(
            recipient_user_id=manager.id,
            reference_type=NotificationReferenceType.GENERAL.value,
            subject="Manager-only",
            body="Private",
            status=NotificationStatus.DELIVERED.value,
            channel="IN_APP",
            scheduled_for_utc=__import__("datetime").datetime.now(timezone.utc),
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(notif)
        db.session.commit()

        rv = client.post(f"/notifications/{notif.id}/mark-read",
                         headers=auth(waiter_token))
        assert rv.status_code == 403, (
            f"Waiter marked manager's notification as read — got {rv.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4.9  Audit log HTTP access — N/A
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditLogAccess:
    def test_no_http_audit_log_endpoint(self, app, client, manager_token, waiter_token):
        """
        N/A: audit log is registered as audit_cli_bp (Flask CLI command only).
        No HTTP route exposes audit log data. Both common probe URLs return 404.
        This test documents the structural absence.
        """
        probes = ["/audit-log", "/audit/log", "/audit", "/admin/audit"]
        for url in probes:
            rv_manager = client.get(url, headers=auth(manager_token))
            rv_waiter  = client.get(url, headers=auth(waiter_token))
            assert rv_manager.status_code == 404, (
                f"GET {url} returned {rv_manager.status_code} — "
                "unexpected HTTP audit log endpoint found"
            )
            assert rv_waiter.status_code == 404
