"""
tests/test_incidents.py — Incident logging endpoint tests.
"""
import pytest
from app.models.incident import Incident
from app.models.audit_log import AuditLog


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def log_payload(**kwargs):
    base = {
        "description": "Guest slipped near the pool.",
        "location": "Pool area",
        "severity": "MEDIUM",
        "idempotency_key": "test-idem-001",
    }
    base.update(kwargs)
    return base


# ── POST /incidents ───────────────────────────────────────────────────────────

def test_any_staff_can_log_incident(client, waiter_token, app):
    r = client.post("/incidents", json=log_payload(), headers=auth(waiter_token))
    assert r.status_code == 201
    d = r.get_json()
    assert d["severity"] == "MEDIUM"
    assert d["location"] == "Pool area"
    assert d["actioned"] is False

def test_log_with_involved_guest(client, waiter_token):
    r = client.post("/incidents", json=log_payload(
        involved_guest="John Doe",
        idempotency_key="idem-guest-001",
    ), headers=auth(waiter_token))
    assert r.status_code == 201
    assert r.get_json()["involved_guest"] == "John Doe"

def test_missing_description_returns_400(client, waiter_token):
    r = client.post("/incidents", json=log_payload(description=""), headers=auth(waiter_token))
    assert r.status_code == 400
    assert "description" in r.get_json()["error"].lower()

def test_missing_location_returns_400(client, waiter_token):
    r = client.post("/incidents", json=log_payload(location=""), headers=auth(waiter_token))
    assert r.status_code == 400
    assert "location" in r.get_json()["error"].lower()

def test_invalid_severity_returns_400(client, waiter_token):
    r = client.post("/incidents", json=log_payload(severity="CRITICAL"), headers=auth(waiter_token))
    assert r.status_code == 400
    assert "severity" in r.get_json()["error"].lower()

def test_missing_idempotency_key_returns_400(client, waiter_token):
    r = client.post("/incidents", json=log_payload(idempotency_key=""), headers=auth(waiter_token))
    assert r.status_code == 400
    assert "idempotency_key" in r.get_json()["error"].lower()

def test_idempotency_same_key_returns_duplicate(client, waiter_token, app):
    payload = log_payload(idempotency_key="idem-dup-001")
    r1 = client.post("/incidents", json=payload, headers=auth(waiter_token))
    r2 = client.post("/incidents", json=payload, headers=auth(waiter_token))
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.get_json()["duplicate"] is True
    with app.app_context():
        from app.extensions import db
        count = db.session.query(Incident).filter_by(idempotency_key="idem-dup-001").count()
        assert count == 1

def test_audit_log_written_on_create(client, waiter_token, app):
    client.post("/incidents", json=log_payload(idempotency_key="idem-audit-001"),
                headers=auth(waiter_token))
    with app.app_context():
        from app.extensions import db
        log = db.session.query(AuditLog).filter_by(action="incident.log").first()
        assert log is not None

def test_all_severities_accepted(client, waiter_token):
    for i, sev in enumerate(["LOW", "MEDIUM", "HIGH"]):
        r = client.post("/incidents", json=log_payload(
            severity=sev, idempotency_key=f"idem-sev-{i}"
        ), headers=auth(waiter_token))
        assert r.status_code == 201, f"Severity {sev} rejected"

def test_unauthenticated_returns_401(client):
    r = client.post("/incidents", json=log_payload())
    assert r.status_code == 401


# ── GET /incidents ────────────────────────────────────────────────────────────

def test_waiter_cannot_list_incidents(client, waiter_token):
    r = client.get("/incidents", headers=auth(waiter_token))
    assert r.status_code == 403

def test_manager_can_list_incidents(client, manager_token, waiter_token):
    client.post("/incidents", json=log_payload(idempotency_key="list-01"), headers=auth(waiter_token))
    r = client.get("/incidents", headers=auth(manager_token))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
    assert len(r.get_json()) >= 1

def test_filter_by_severity(client, manager_token, waiter_token):
    client.post("/incidents", json=log_payload(severity="HIGH", idempotency_key="filt-high-01"),
                headers=auth(waiter_token))
    client.post("/incidents", json=log_payload(severity="LOW", idempotency_key="filt-low-01"),
                headers=auth(waiter_token))
    r = client.get("/incidents?severity=HIGH", headers=auth(manager_token))
    assert r.status_code == 200
    data = r.get_json()
    assert all(i["severity"] == "HIGH" for i in data)

def test_filter_by_actioned_false(client, manager_token, waiter_token):
    client.post("/incidents", json=log_payload(idempotency_key="filt-act-01"),
                headers=auth(waiter_token))
    r = client.get("/incidents?actioned=false", headers=auth(manager_token))
    assert r.status_code == 200
    assert all(i["actioned"] is False for i in r.get_json())


# ── PATCH /incidents/<id>/action ──────────────────────────────────────────────

def test_manager_can_action_incident(client, manager_token, waiter_token):
    r = client.post("/incidents", json=log_payload(idempotency_key="act-01"),
                    headers=auth(waiter_token))
    inc_id = r.get_json()["id"]
    r2 = client.patch(f"/incidents/{inc_id}/action", headers=auth(manager_token))
    assert r2.status_code == 200
    assert r2.get_json()["actioned"] is True
    assert r2.get_json()["actioned_by"] is not None

def test_waiter_cannot_action_incident(client, manager_token, waiter_token):
    r = client.post("/incidents", json=log_payload(idempotency_key="act-02"),
                    headers=auth(waiter_token))
    inc_id = r.get_json()["id"]
    r2 = client.patch(f"/incidents/{inc_id}/action", headers=auth(waiter_token))
    assert r2.status_code == 403

def test_action_idempotency(client, manager_token, waiter_token, app):
    r = client.post("/incidents", json=log_payload(idempotency_key="act-idem-01"),
                    headers=auth(waiter_token))
    inc_id = r.get_json()["id"]
    r1 = client.patch(f"/incidents/{inc_id}/action", headers=auth(manager_token))
    first_actioned_at = r1.get_json()["actioned_at"]
    r2 = client.patch(f"/incidents/{inc_id}/action", headers=auth(manager_token))
    assert r2.status_code == 200
    assert r2.get_json()["duplicate"] is True
    assert r2.get_json()["actioned_at"] == first_actioned_at

def test_audit_log_written_on_action(client, manager_token, waiter_token, app):
    r = client.post("/incidents", json=log_payload(idempotency_key="act-audit-01"),
                    headers=auth(waiter_token))
    inc_id = r.get_json()["id"]
    client.patch(f"/incidents/{inc_id}/action", headers=auth(manager_token))
    with app.app_context():
        from app.extensions import db
        log = db.session.query(AuditLog).filter_by(
            action="incident.action", target=inc_id
        ).first()
        assert log is not None

def test_action_nonexistent_incident_returns_404(client, manager_token):
    r = client.patch("/incidents/does-not-exist/action", headers=auth(manager_token))
    assert r.status_code == 404
