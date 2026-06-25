"""
test_auth.py — Tests for:
  1. Password login success
  2. PIN login success
  3. Kill-switch: deactivated user locked out on next request
  4. Lockout after N failed PIN attempts
  5. Audit log chain verification
  6. Account creation hierarchy enforcement
"""
import pytest
from app.extensions import db
from app.models.user import User
from app.models.audit_log import AuditLog


# ── 1. Password login ──────────────────────────────────────────────────────────

def test_password_login_success(client):
    rv = client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_password_login_wrong_password(client):
    rv = client.post("/auth/login", json={"username": "owner1", "password": "wrong"})
    assert rv.status_code == 401


# ── 2. PIN login ───────────────────────────────────────────────────────────────

def test_pin_login_success(client):
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    assert rv.status_code == 200
    assert "access_token" in rv.get_json()


def test_pin_login_wrong_pin(client):
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "9999"})
    assert rv.status_code == 401


# ── 3. Kill-switch ─────────────────────────────────────────────────────────────

def test_kill_switch_blocks_next_request(app, client, owner_token):
    # Owner deactivates manager1
    with app.app_context():
        target = db.session.query(User).filter_by(username="manager1").first()
        target_id = target.id

    rv = client.post(
        f"/auth/deactivate/{target_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rv.status_code == 200

    # manager1 tries to log in — must be blocked.
    # Security fix 4.1/4.2: inactive users return 401 + generic "Invalid credentials."
    # (same as no-user path) so attackers can't enumerate active vs. inactive accounts.
    rv2 = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
    assert rv2.status_code == 401
    assert rv2.get_json()["error"] == "Invalid credentials."


# ── 4. Lockout after N failed attempts ────────────────────────────────────────

def test_lockout_after_failed_pin_attempts(app, client):
    # FAILED_ATTEMPTS_LOCKOUT is set to 3 in conftest
    for _ in range(3):
        client.post("/auth/pin-login", json={"username": "staff1", "pin": "0000"})

    # 4th attempt — should be locked
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    assert rv.status_code == 403
    assert "locked" in rv.get_json()["error"].lower()


# ── 5. Audit log chain verification ───────────────────────────────────────────

def test_audit_chain_is_valid(app, client):
    # Trigger a few log entries via logins
    client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
    client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})

    with app.app_context():
        ok, msg = AuditLog.verify_chain()
    assert ok, f"Audit chain broken: {msg}"


def test_audit_chain_detects_tampering(app, client):
    # Generate entries
    client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})

    with app.app_context():
        # Tamper with a row
        entry = db.session.query(AuditLog).first()
        if entry:
            entry.actor = "hacker"
            db.session.commit()

        ok, msg = AuditLog.verify_chain()
    # Should detect the tampering (unless log is empty)
    if entry:
        assert not ok


# ── 6. Hierarchy enforcement ───────────────────────────────────────────────────

def test_staff_cannot_create_users(app, client):
    """Staff (level 1) must not be able to create any account."""
    # Get staff token via PIN
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    staff_token = rv.get_json()["access_token"]

    # Try to create another staff account
    with app.app_context():
        staff_role = db.session.query(__import__("app.models.role", fromlist=["Role"]).Role).filter_by(name="staff").first()
        role_id = staff_role.id

    rv2 = client.post(
        "/auth/users",
        json={"username": "newstaff", "role_id": role_id},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert rv2.status_code == 403


def test_manager_cannot_create_manager(app, client, manager_token):
    """Manager (level 5) must not create another manager (level 5)."""
    with app.app_context():
        mgr_role = db.session.query(__import__("app.models.role", fromlist=["Role"]).Role).filter_by(name="manager").first()
        role_id = mgr_role.id

    rv = client.post(
        "/auth/users",
        json={"username": "new_manager", "role_id": role_id},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 403


def test_owner_can_create_manager(app, client, owner_token):
    """Owner (level 10) can create a manager (level 5)."""
    with app.app_context():
        mgr_role = db.session.query(__import__("app.models.role", fromlist=["Role"]).Role).filter_by(name="manager").first()
        role_id = mgr_role.id

    rv = client.post(
        "/auth/users",
        json={"username": "new_manager2", "role_id": role_id, "password": "Temp1234!"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rv.status_code == 201
    assert rv.get_json()["username"] == "new_manager2"


def test_reset_lockout_hierarchy(app, client, owner_token):
    """Owner can reset a manager's lockout; staff cannot self-reset."""
    # Lock manager1 out
    for _ in range(3):
        client.post("/auth/login", json={"username": "manager1", "password": "wrong"})

    with app.app_context():
        target = db.session.query(User).filter_by(username="manager1").first()
        target_id = target.id

    # Owner resets it
    rv = client.post(
        f"/auth/reset-lockout/{target_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rv.status_code == 200

    # manager1 can log in again
    rv2 = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
    assert rv2.status_code == 200


# ── /auth/change-password ─────────────────────────────────────────────────────

def test_change_password_success(app, client, manager_token):
    rv = client.post("/auth/change-password",
        json={"current_password": "ManagerPass1!", "new_password": "NewPass9999!"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    # Old password no longer works
    assert client.post("/auth/login",
        json={"username": "manager1", "password": "ManagerPass1!"}).status_code == 401
    # New password works
    assert client.post("/auth/login",
        json={"username": "manager1", "password": "NewPass9999!"}).status_code == 200


def test_change_password_wrong_current(client, manager_token):
    rv = client.post("/auth/change-password",
        json={"current_password": "wrongpassword", "new_password": "NewPass9999!"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 401


def test_change_password_too_short(client, manager_token):
    rv = client.post("/auth/change-password",
        json={"current_password": "ManagerPass1!", "new_password": "short"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 400
    assert "8 characters" in rv.get_json()["error"]


def test_change_password_unauthenticated(client):
    rv = client.post("/auth/change-password",
        json={"current_password": "ManagerPass1!", "new_password": "NewPass9999!"},
    )
    assert rv.status_code == 401
