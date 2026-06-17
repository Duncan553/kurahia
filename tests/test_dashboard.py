"""
tests/test_dashboard.py — Chunk 10 dashboard, equipment, alerts, audit-chain tests.

Coverage:
  1.  Dashboard overview: returns correct shape, owner-only
  2.  Dashboard finance: revenue total, reconciliation status
  3.  Dashboard bookings: arrivals/departures shape
  4.  Dashboard staff: employee counts, suggestion/dispute counts
  5.  Dashboard conduct: compliance percentages
  6.  Dashboard feedback: averages aggregated correctly
  7.  Dashboard alerts: returns judge alerts in unified feed
  8.  Alert acknowledge: flips status, audit-logged
  9.  Alert action-taken: requires notes, flips to RESOLVED
 10.  Dashboard equipment: service-due flag computed correctly
 11.  Equipment CRUD: create, log maintenance, safety check, disable
 12.  Audit chain: verify_chain passes on fresh DB
 13.  Role enforcement: manager cannot access owner-only dashboard
 14.  Retrofit: edit_event now writes audit log
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def judge_alert(app):
    from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
    from app.extensions import db
    a = JudgeAlert(
        item_id=None,
        alert_type="TEST_ALERT",
        severity=AlertSeverity.MEDIUM.value,
        description="A test alert for dashboard testing.",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        status=AlertStatus.OPEN.value,
    )
    db.session.add(a)
    db.session.commit()
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Overview
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverview:
    def test_returns_correct_shape(self, client, owner_token):
        rv = client.get("/dashboard/overview", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "revenue" in data
        assert "staff" in data
        assert "bookings" in data
        assert "inventory_alerts" in data
        assert "top_alerts" in data
        assert "week_calendar" in data

    def test_manager_can_access(self, client, manager_token):
        rv = client.get("/dashboard/overview", headers=auth(manager_token))
        assert rv.status_code == 200

    def test_week_period(self, client, owner_token):
        rv = client.get("/dashboard/overview?period=week", headers=auth(owner_token))
        assert rv.status_code == 200
        assert rv.get_json()["period"] == "week"

    def test_month_period(self, client, owner_token):
        rv = client.get("/dashboard/overview?period=month", headers=auth(owner_token))
        assert rv.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Finance
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinanceDashboard:
    def test_returns_shape(self, client, owner_token):
        rv = client.get("/dashboard/finance", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "total_revenue" in data
        assert "reconciliation_status" in data
        assert "open_shortfalls" in data

    def test_reconciliation_status_green_with_no_shortfalls(self, client, owner_token):
        rv = client.get("/dashboard/finance", headers=auth(owner_token))
        assert rv.get_json()["reconciliation_status"] == "green"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Bookings
# ═══════════════════════════════════════════════════════════════════════════════

class TestBookingsDashboard:
    def test_returns_shape(self, client, owner_token):
        rv = client.get("/dashboard/bookings", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "occupancy_by_type" in data
        assert "arrivals_today" in data
        assert "departures_today" in data
        assert "pending_deposits" in data
        assert "villa_revenue" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Staff
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaffDashboard:
    def test_returns_shape(self, client, owner_token):
        rv = client.get("/dashboard/staff", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "active_employees" in data
        assert "on_duty" in data
        assert "open_disputes" in data
        assert "new_suggestions" in data

    def test_counts_owner_private_separately(self, client, owner_token, manager_token):
        # Submit an OWNER_PRIVATE suggestion
        client.post("/suggestions", json={
            "category": "OWNER_PRIVATE",
            "subject": "Private matter",
            "body": "Sensitive.",
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(manager_token))

        rv = client.get("/dashboard/staff", headers=auth(owner_token))
        data = rv.get_json()
        # owner_private count should be >= 1
        assert data["new_suggestions"]["owner_private"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Conduct
# ═══════════════════════════════════════════════════════════════════════════════

class TestConductDashboard:
    def test_returns_shape(self, client, owner_token, manager_token):
        # Seed a rule first
        client.post("/conduct/rules", json={
            "rule_key": "dash-test-rule",
            "title": "Dashboard Test Rule",
            "body": "Test body.",
            "category": "GENERAL",
        }, headers=auth(owner_token))

        rv = client.get("/dashboard/conduct", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "active_rules" in data
        assert "compliance" in data
        assert "overall_compliance_pct" in data
        assert data["active_rules"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Feedback
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackDashboard:
    def test_returns_shape_with_no_data(self, client, owner_token):
        rv = client.get("/dashboard/feedback", headers=auth(owner_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "overall_avg" in data
        assert "by_department" in data
        assert "by_staff" in data

    def test_aggregates_feedback_correctly(self, client, owner_token, waiter_token, app):
        from app.models.guest_feedback import GuestFeedback
        from app.extensions import db
        with app.app_context():
            for score in [5, 3, 4]:
                db.session.add(GuestFeedback(
                    guest_name="Tester",
                    score=score,
                    idempotency_key=f"dash-fb-{score}-{uuid.uuid4()}",
                ))
            db.session.commit()

        rv = client.get("/dashboard/feedback?period=month", headers=auth(owner_token))
        data = rv.get_json()
        # avg(5,3,4) = 4.00
        assert Decimal(data["overall_avg"]) == Decimal("4.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Alerts feed
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsFeed:
    def test_returns_open_alerts(self, client, owner_token, judge_alert):
        rv = client.get("/dashboard/alerts", headers=auth(owner_token))
        assert rv.status_code == 200
        ids = [a["id"] for a in rv.get_json()]
        assert judge_alert.id in ids

    def test_has_recommended_action(self, client, owner_token, judge_alert):
        rv = client.get("/dashboard/alerts", headers=auth(owner_token))
        for alert in rv.get_json():
            assert "recommended_action" in alert

    def test_manager_cannot_view_alerts(self, client, manager_token, judge_alert):
        rv = client.get("/dashboard/alerts", headers=auth(manager_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 8 & 9. Alert acknowledge and action-taken
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertActions:
    def test_acknowledge_alert(self, client, owner_token, judge_alert):
        rv = client.post(f"/dashboard/alerts/{judge_alert.id}/acknowledge",
                         headers=auth(owner_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "ACKNOWLEDGED"

    def test_action_taken_requires_notes(self, client, owner_token, judge_alert):
        rv = client.post(f"/dashboard/alerts/{judge_alert.id}/action-taken",
                         json={}, headers=auth(owner_token))
        assert rv.status_code == 400
        assert "notes" in rv.get_json()["error"].lower()

    def test_action_taken_resolves(self, client, owner_token, judge_alert):
        rv = client.post(f"/dashboard/alerts/{judge_alert.id}/action-taken",
                         json={"notes": "Investigated and resolved the variance."},
                         headers=auth(owner_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "RESOLVED"


# ═══════════════════════════════════════════════════════════════════════════════
# 10 & 11. Equipment
# ═══════════════════════════════════════════════════════════════════════════════

class TestEquipment:
    def _create(self, client, token, name="Jetski A"):
        return client.post("/equipment", json={
            "name": name,
            "equipment_type": "Jetski",
            "service_interval_days": 30,
        }, headers=auth(token))

    def test_create_equipment(self, client, manager_token):
        rv = self._create(client, manager_token)
        assert rv.status_code == 201
        assert rv.get_json()["name"] == "Jetski A"
        assert rv.get_json()["is_due_service"] is False  # no last service → False

    def test_staff_cannot_create(self, client, waiter_token):
        rv = self._create(client, waiter_token)
        assert rv.status_code == 403

    def test_log_maintenance_clears_due_flag(self, client, manager_token, owner_token, app):
        rv = self._create(client, manager_token, name="Jetski B")
        eq_id = rv.get_json()["id"]

        # Set last_service to 40 days ago (past 30-day interval → due)
        from app.models.equipment import Equipment
        from app.extensions import db
        with app.app_context():
            eq = db.session.get(Equipment, eq_id)
            eq.last_service_utc = datetime.now(timezone.utc) - timedelta(days=40)
            db.session.commit()

        # Verify it shows as due on dashboard (owner-only endpoint)
        rv_dash = client.get("/dashboard/equipment", headers=auth(owner_token))
        assert rv_dash.status_code == 200
        due_ids = [e["id"] for e in rv_dash.get_json()["due_service"]]
        assert eq_id in due_ids

        # Log maintenance → no longer due
        client.post(f"/equipment/{eq_id}/maintenance",
                    json={"notes": "Routine service completed.",
                          "performed_at_utc": datetime.now(timezone.utc).isoformat()},
                    headers=auth(manager_token))

        with app.app_context():
            eq = db.session.get(Equipment, eq_id)
        assert eq.is_due_service is False

    def test_safety_check_succeeds_with_full_jetski_checklist(self, client, manager_token):
        rv = self._create(client, manager_token, name="Jetski C")
        eq_id = rv.get_json()["id"]
        rv = client.post(f"/equipment/{eq_id}/safety-check",
                         json={"check_items": {
                             "life_jackets_on_board":      {"checked": True, "note": ""},
                             "engine_oil_level_checked":   {"checked": True, "note": ""},
                             "fuel_level_ok":              {"checked": True, "note": ""},
                             "kill_switch_lanyard_present":{"checked": True, "note": ""},
                             "guest_waiver_confirmed":     {"checked": True, "note": ""},
                         }},
                         headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["passed"] is True

    def test_disable_equipment(self, client, manager_token):
        rv = self._create(client, manager_token, name="Jetski D")
        eq_id = rv.get_json()["id"]
        rv = client.post(f"/equipment/{eq_id}/disable", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Audit chain verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditChain:
    def test_verify_chain_passes_on_clean_db(self, app):
        from app.models.audit_log import AuditLog
        from app.extensions import db
        with app.app_context():
            ok, message = AuditLog.verify_chain()
        assert ok is True
        assert message == "ok"

    def test_chain_broken_if_row_tampered(self, app):
        from app.models.audit_log import AuditLog
        from app.extensions import db
        with app.app_context():
            # Write a real audit entry
            AuditLog.log(actor="test", action="test.audit")
            db.session.commit()
            # Tamper with the actor field — breaks the hash
            entry = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
            entry.actor = "TAMPERED"
            db.session.commit()
            ok, message = AuditLog.verify_chain()
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Retrofit — edit_event audit log
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetrofit:
    def test_edit_event_writes_audit_log(self, client, manager_token, owner_token, app):
        from app.models.audit_log import AuditLog
        from app.models.event_type import EventType
        from app.extensions import db

        with app.app_context():
            et = EventType(name="RETROFIT_TEST")
            db.session.add(et)
            db.session.commit()
            et_id = et.id

        now = datetime.now(timezone.utc)
        rv = client.post("/events", json={
            "title": "Retrofit Test Event",
            "event_type_id": et_id,
            "starts_at_utc": (now + timedelta(days=5)).isoformat(),
            "ends_at_utc":   (now + timedelta(days=5, hours=4)).isoformat(),
            "expected_guests": 20,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=auth(manager_token))
        event_id = rv.get_json()["id"]

        count_before = 0
        with app.app_context():
            count_before = db.session.query(AuditLog).filter_by(action="event.edit").count()

        client.patch(f"/events/{event_id}",
                     json={"title": "Updated Title"},
                     headers=auth(manager_token))

        with app.app_context():
            count_after = db.session.query(AuditLog).filter_by(action="event.edit").count()
        assert count_after == count_before + 1
