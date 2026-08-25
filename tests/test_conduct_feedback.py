"""
tests/test_conduct_feedback.py — Chunk 9 Conduct, Disputes, Feedback, Calendar tests.

Coverage:
  1.  Conduct versioning: editing creates new version; prior deactivated; history preserved
  2.  Signing idempotency: re-signing same version is no-op
  3.  Compliance report: identifies unsigned employees per current version
  4.  Dispute lifecycle: OPEN → UNDER_REVIEW → RESOLVED; illegal moves rejected
  5.  Dispute confidentiality: is_owner_only invisible to manager (query-level)
  6.  Dispute role: employees see only their own; managers see non-owner-only
  7.  Feedback recording: score stored, idempotent
  8.  Feedback aggregation: averages correct, per-staff filtering works
  9.  Performance socket activated: guest_rating returns real average from GuestFeedback
 10.  Calendar entry creation: planning trigger schedules notification at correct time
 11.  Role enforcement throughout
 12.  Plain-English errors
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def employee_profile(app):
    """Idempotent — waiter_token (conftest.py) may already have created this
    same row so require_clocked_in passes elsewhere in the same test."""
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
def conduct_rule(app, owner_token, client):
    """A single active conduct rule (v1)."""
    rv = client.post("/conduct/rules", json={
        "rule_key": "test-punctuality",
        "title": "Punctuality Policy",
        "body":  "Always arrive on time.",
        "category": "PUNCTUALITY",
    }, headers=auth(owner_token))
    return rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Conduct versioning
# ═══════════════════════════════════════════════════════════════════════════════

class TestConductVersioning:
    def test_create_rule_v1(self, client, owner_token, conduct_rule):
        assert conduct_rule["version"] == 1
        assert conduct_rule["is_active"] is True

    def test_update_creates_new_version(self, client, owner_token, conduct_rule):
        rv = client.post("/conduct/rules", json={
            "rule_key": "test-punctuality",
            "title":    "Punctuality Policy (Updated)",
            "body":     "Arrive 5 minutes early.",
            "category": "PUNCTUALITY",
        }, headers=auth(owner_token))
        assert rv.status_code == 201
        v2 = rv.get_json()
        assert v2["version"] == 2
        assert v2["is_active"] is True

    def test_prior_version_deactivated_after_update(self, client, owner_token, conduct_rule, app):
        from app.models.conduct_rule import ConductRule
        from app.extensions import db
        rule_id_v1 = conduct_rule["id"]

        client.post("/conduct/rules", json={
            "rule_key": "test-punctuality",
            "title": "Punctuality Policy v2",
            "body": "New body",
            "category": "PUNCTUALITY",
        }, headers=auth(owner_token))

        with app.app_context():
            v1 = db.session.get(ConductRule, rule_id_v1)
        assert v1.is_active is False

    def test_version_history_preserved(self, client, owner_token, conduct_rule):
        client.post("/conduct/rules", json={
            "rule_key": "test-punctuality", "title": "v2",
            "body": "body2", "category": "PUNCTUALITY",
        }, headers=auth(owner_token))
        rule_id = conduct_rule["id"]
        rv = client.get(f"/conduct/rules/{rule_id}/versions", headers=auth(owner_token))
        assert rv.status_code == 200
        assert len(rv.get_json()) == 2

    def test_staff_cannot_create_rule(self, client, waiter_token):
        rv = client.post("/conduct/rules", json={
            "rule_key": "test-x", "title": "X", "body": "Y", "category": "GENERAL",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Signing idempotency
# ═══════════════════════════════════════════════════════════════════════════════

class TestConductSigning:
    def test_employee_signs_rule(self, client, waiter_token, conduct_rule, employee_profile):
        rv = client.post("/conduct/sign", json={
            "conduct_rule_id": conduct_rule["id"],
            "signed_proof": "Test Waiter",
        }, headers=auth(waiter_token))
        assert rv.status_code == 201

    def test_sign_twice_is_idempotent(self, client, waiter_token, conduct_rule, employee_profile):
        client.post("/conduct/sign", json={"conduct_rule_id": conduct_rule["id"]},
                    headers=auth(waiter_token))
        rv2 = client.post("/conduct/sign", json={"conduct_rule_id": conduct_rule["id"]},
                          headers=auth(waiter_token))
        assert rv2.status_code == 200
        assert rv2.get_json()["duplicate"] is True

    def test_signature_tracks_version(self, client, waiter_token, conduct_rule, employee_profile, app):
        from app.models.conduct_signature import ConductSignature
        from app.extensions import db
        client.post("/conduct/sign", json={"conduct_rule_id": conduct_rule["id"]},
                    headers=auth(waiter_token))
        with app.app_context():
            sig = db.session.query(ConductSignature).filter_by(
                conduct_rule_id=conduct_rule["id"]
            ).first()
        assert sig is not None
        assert sig.conduct_rule_id == conduct_rule["id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Compliance report
# ═══════════════════════════════════════════════════════════════════════════════

class TestComplianceReport:
    def test_compliance_shows_unsigned_employee(
            self, client, manager_token, conduct_rule, employee_profile):
        rv = client.get("/conduct/compliance", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        rule_report = next((r for r in data if r["rule_key"] == "test-punctuality"), None)
        assert rule_report is not None
        assert rule_report["unsigned_count"] >= 1
        assert "Test Waiter" in rule_report["unsigned_employees"]

    def test_compliance_clears_after_signing(
            self, client, manager_token, waiter_token, conduct_rule, employee_profile):
        client.post("/conduct/sign", json={"conduct_rule_id": conduct_rule["id"]},
                    headers=auth(waiter_token))
        rv = client.get("/conduct/compliance", headers=auth(manager_token))
        rule_report = next(
            (r for r in rv.get_json() if r["rule_key"] == "test-punctuality"), None
        )
        if rule_report:
            assert "Test Waiter" not in rule_report["unsigned_employees"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Dispute lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisputeLifecycle:
    def _create(self, client, token, employee_profile, idem=None):
        return client.post("/disputes", json={
            "category": "INTERPERSONAL",
            "description": "Ongoing conflict with colleague.",
            "idempotency_key": idem or str(uuid.uuid4()),
        }, headers=auth(token))

    def test_employee_creates_dispute(self, client, waiter_token, employee_profile):
        rv = self._create(client, waiter_token, employee_profile)
        assert rv.status_code == 201
        assert rv.get_json()["status"] == "OPEN"

    def test_full_lifecycle(self, client, manager_token, waiter_token, employee_profile):
        rv = self._create(client, waiter_token, employee_profile)
        did = rv.get_json()["id"]
        rv = client.post(f"/disputes/{did}/claim",   headers=auth(manager_token))
        assert rv.get_json()["status"] == "UNDER_REVIEW"
        rv = client.post(f"/disputes/{did}/resolve",
                         json={"resolution_notes": "Mediation completed."},
                         headers=auth(manager_token))
        assert rv.get_json()["status"] == "RESOLVED"

    def test_illegal_transition_rejected(self, client, manager_token, waiter_token,
                                          employee_profile):
        rv = self._create(client, waiter_token, employee_profile)
        did = rv.get_json()["id"]
        # Can't go OPEN → RESOLVED directly
        rv = client.post(f"/disputes/{did}/resolve",
                         json={"resolution_notes": "Skip."},
                         headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Dispute confidentiality
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisputeConfidentiality:
    def _create_owner_only(self, client, token, employee_profile):
        return client.post("/disputes", json={
            "category": "CONDUCT_VIOLATION",
            "description": "Sensitive private report.",
            "is_owner_only": True,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(token))

    def test_owner_only_invisible_to_manager_list(
            self, client, manager_token, waiter_token, owner_token, employee_profile):
        self._create_owner_only(client, waiter_token, employee_profile)
        rv = client.get("/disputes", headers=auth(manager_token))
        assert rv.status_code == 200
        assert all(not d["is_owner_only"] for d in rv.get_json())

    def test_owner_only_visible_to_owner(
            self, client, waiter_token, owner_token, employee_profile):
        self._create_owner_only(client, waiter_token, employee_profile)
        rv = client.get("/disputes", headers=auth(owner_token))
        assert any(d["is_owner_only"] for d in rv.get_json())

    def test_employee_sees_only_own_disputes(
            self, client, waiter_token, employee_profile, app):
        self._create_owner_only(client, waiter_token, employee_profile)
        rv = client.get("/disputes", headers=auth(waiter_token))
        assert rv.status_code == 200
        # Employee only sees their own (reporter) disputes
        for d in rv.get_json():
            assert d["reporter"] == "Test Waiter"


# ═══════════════════════════════════════════════════════════════════════════════
# 7 & 8. Guest feedback
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuestFeedback:
    def _submit(self, client, token, score=5, emp_id=None):
        return client.post("/feedback", json={
            "guest_name": "Anonymous Guest",
            "score": score,
            "served_by_employee_id": emp_id,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(token))

    def test_record_feedback(self, client, waiter_token):
        rv = self._submit(client, waiter_token, score=4)
        assert rv.status_code == 201
        assert rv.get_json()["score"] == 4

    def test_invalid_score_rejected(self, client, waiter_token):
        rv = client.post("/feedback", json={
            "guest_name": "Test", "score": 6,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(waiter_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_idempotent_submit(self, client, waiter_token):
        idem = str(uuid.uuid4())
        rv1 = client.post("/feedback", json={
            "guest_name": "Test", "score": 3,
            "idempotency_key": idem,
        }, headers=auth(waiter_token))
        rv2 = client.post("/feedback", json={
            "guest_name": "Test", "score": 3,
            "idempotency_key": idem,
        }, headers=auth(waiter_token))
        assert rv1.status_code == 201
        assert rv2.status_code == 200
        assert rv2.get_json()["duplicate"] is True

    def test_aggregate_average_correct(self, client, manager_token, waiter_token):
        self._submit(client, waiter_token, score=4)
        self._submit(client, waiter_token, score=2)
        rv = client.get("/feedback", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] >= 2
        # avg of 4 + 2 = 3.0
        avg = Decimal(data["average_score"])
        assert avg == Decimal("3.00")

    def test_per_staff_feedback(self, client, manager_token, waiter_token, employee_profile):
        self._submit(client, waiter_token, score=5, emp_id=employee_profile.id)
        self._submit(client, waiter_token, score=3, emp_id=employee_profile.id)
        rv = client.get(f"/feedback/staff/{employee_profile.id}", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 2
        assert Decimal(data["average_score"]) == Decimal("4.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Performance socket activated — guest_rating returns real average
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerformanceSocket:
    def test_guest_rating_populated_from_feedback(
            self, client, manager_token, waiter_token, employee_profile, app):
        from app.models.guest_feedback import GuestFeedback
        from app.extensions import db

        # Seed feedback linked to this employee
        with app.app_context():
            for score in [5, 4, 5]:
                db.session.add(GuestFeedback(
                    guest_name="Test Guest",
                    score=score,
                    served_by_employee_id=employee_profile.id,
                    idempotency_key=f"perf-test-{score}-{uuid.uuid4()}",
                ))
            db.session.commit()

        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end   = now.strftime("%Y-%m-%d")
        rv = client.get(
            f"/hr/performance/{employee_profile.id}?start_date={start}&end_date={end}",
            headers=auth(manager_token),
        )
        assert rv.status_code == 200
        detail = rv.get_json()["detail"]
        # Previously None — now a real average (5+4+5)/3 = 4.67
        assert detail["guest_rating"] is not None
        assert Decimal(detail["guest_rating"]) == Decimal("4.67")

    def test_no_feedback_returns_none(
            self, client, manager_token, employee_profile):
        now = datetime.now(timezone.utc)
        rv = client.get(
            f"/hr/performance/{employee_profile.id}"
            f"?start_date={now.strftime('%Y-%m-%d')}&end_date={now.strftime('%Y-%m-%d')}",
            headers=auth(manager_token),
        )
        assert rv.get_json()["detail"]["guest_rating"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Calendar planning trigger
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalendarTrigger:
    def test_planning_trigger_creates_notification(self, client, manager_token, owner_token, app):
        from app.models.notification import Notification, NotificationReferenceType
        from app.extensions import db

        now = datetime.now(timezone.utc)
        future = now + timedelta(days=30)

        rv = client.post("/calendar", json={
            "title": "Madaraka Day",
            "entry_type": "HOLIDAY",
            "date_start": future.isoformat(),
            "date_end":   (future + timedelta(days=1)).isoformat(),
            "is_peak": True,
            "planning_trigger_offset_days": 14,
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        entry_id = rv.get_json()["id"]

        with app.app_context():
            from app.models.user import User
            owner = db.session.query(User).filter_by(username="owner1").first()
            notif = db.session.query(Notification).filter_by(
                reference_id=entry_id,
                recipient_user_id=owner.id,
            ).first()
        assert notif is not None
        # Should be scheduled 14 days before the event
        expected_trigger = future - timedelta(days=14)
        actual = notif.scheduled_for_utc.replace(tzinfo=timezone.utc) \
            if notif.scheduled_for_utc.tzinfo is None else notif.scheduled_for_utc
        diff = abs((actual - expected_trigger).total_seconds())
        assert diff < 10

    def test_no_trigger_without_offset(self, client, manager_token, app):
        from app.models.notification import Notification
        from app.extensions import db

        now = datetime.now(timezone.utc)
        rv = client.post("/calendar", json={
            "title": "Regular Meeting",
            "entry_type": "PLANNING_MEETING",
            "date_start": (now + timedelta(days=7)).isoformat(),
            "date_end":   (now + timedelta(days=7, hours=2)).isoformat(),
        }, headers=auth(manager_token))
        entry_id = rv.get_json()["id"]

        with app.app_context():
            notif = db.session.query(Notification).filter_by(
                reference_id=entry_id
            ).first()
        assert notif is None

    def test_calendar_list_returns_entries(self, client, manager_token):
        now = datetime.now(timezone.utc)
        client.post("/calendar", json={
            "title": "Peak Season",
            "entry_type": "PEAK",
            "date_start": now.isoformat(),
            "date_end":   (now + timedelta(days=7)).isoformat(),
        }, headers=auth(manager_token))
        rv = client.get("/calendar", headers=auth(manager_token))
        assert rv.status_code == 200
        assert len(rv.get_json()) >= 1
