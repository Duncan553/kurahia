"""
test_admin_settings.py — Tests for GET /admin/settings and PATCH /admin/settings.

Owner only (level 10). Covers role gating, value persistence,
range validation, type validation, unknown-key tolerance, and audit log.
"""
import pytest
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.system_setting import SystemSetting


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── GET /admin/settings ────────────────────────────────────────────────────────

def test_owner_gets_settings(client, owner_token):
    """Owner receives 200 with all known keys present."""
    rv = client.get("/admin/settings", headers=auth(owner_token))
    assert rv.status_code == 200
    data = rv.get_json()
    assert "business_day_start_hour" in data


def test_manager_cannot_get_settings(client, manager_token):
    """Level-5 manager is refused — 403."""
    rv = client.get("/admin/settings", headers=auth(manager_token))
    assert rv.status_code == 403


def test_waiter_cannot_get_settings(client, waiter_token):
    """Level-1 waiter is refused — 403."""
    rv = client.get("/admin/settings", headers=auth(waiter_token))
    assert rv.status_code == 403


def test_get_settings_returns_default_when_not_customised(app, client, owner_token):
    """When no DB row exists the code falls back to the meta default ("6")."""
    # Remove the row seeded by conftest so the handler hits the else-branch
    with app.app_context():
        row = db.session.get(SystemSetting, "business_day_start_hour")
        if row:
            db.session.delete(row)
            db.session.commit()

    rv = client.get("/admin/settings", headers=auth(owner_token))
    assert rv.status_code == 200
    assert rv.get_json()["business_day_start_hour"] == "6"


# ── PATCH /admin/settings ──────────────────────────────────────────────────────

def test_owner_updates_setting(client, owner_token):
    """Owner PATCH returns 200 and the updated key appears in the 'updated' list."""
    rv = client.patch(
        "/admin/settings",
        json={"business_day_start_hour": 8},
        headers=auth(owner_token),
    )
    assert rv.status_code == 200
    assert "business_day_start_hour" in rv.get_json()["updated"]


def test_updated_value_persists(client, owner_token):
    """GET after a PATCH reflects the new value."""
    client.patch(
        "/admin/settings",
        json={"business_day_start_hour": 9},
        headers=auth(owner_token),
    )
    rv = client.get("/admin/settings", headers=auth(owner_token))
    assert rv.status_code == 200
    # The handler stores values as strings
    assert rv.get_json()["business_day_start_hour"] == "9"


def test_value_below_min_rejected(client, owner_token):
    """business_day_start_hour must be >= 0. -1 → 400."""
    rv = client.patch(
        "/admin/settings",
        json={"business_day_start_hour": -1},
        headers=auth(owner_token),
    )
    assert rv.status_code == 400


def test_value_above_max_rejected(client, owner_token):
    """business_day_start_hour must be <= 23. 25 → 400."""
    rv = client.patch(
        "/admin/settings",
        json={"business_day_start_hour": 25},
        headers=auth(owner_token),
    )
    assert rv.status_code == 400


def test_non_integer_value_rejected(client, owner_token):
    """Non-castable string value → 400."""
    rv = client.patch(
        "/admin/settings",
        json={"business_day_start_hour": "noon"},
        headers=auth(owner_token),
    )
    assert rv.status_code == 400


def test_unknown_key_silently_ignored(client, owner_token):
    """Keys not in KNOWN_KEYS are skipped without error; 'updated' is empty."""
    rv = client.patch(
        "/admin/settings",
        json={"nonexistent_key": "whatever"},
        headers=auth(owner_token),
    )
    assert rv.status_code == 200
    assert rv.get_json()["updated"] == []


def test_manager_cannot_update_settings(client, manager_token):
    """Level-5 manager cannot PATCH settings — 403."""
    rv = client.patch(
        "/admin/settings",
        json={"business_day_start_hour": 8},
        headers=auth(manager_token),
    )
    assert rv.status_code == 403


def test_audit_log_written_on_successful_update(app, client, owner_token):
    """A successful PATCH writes an audit log row tagged admin.setting.update."""
    client.patch(
        "/admin/settings",
        json={"business_day_start_hour": 7},
        headers=auth(owner_token),
    )
    with app.app_context():
        log = (
            db.session.query(AuditLog)
            .filter_by(action="admin.setting.update", target="business_day_start_hour")
            .first()
        )
        assert log is not None
        assert log.actor == "owner1"
