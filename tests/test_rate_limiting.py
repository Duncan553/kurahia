"""
Tests for login rate limiting (Q-2.1).
Rate limiting is DISABLED in TestingConfig by default to protect other tests.
The `rate_limit_client` fixture enables it for just these tests.
"""
import pytest
from app.models.audit_log import AuditLog
from app.extensions import db, limiter


@pytest.fixture
def rate_limit_client(app, client):
    """
    Opt into rate limiting for this test (exempt by default in testing).
    Reset state before and after to ensure clean counts.
    """
    app.config["TEST_RATELIMIT"] = True
    limiter.reset()
    yield client
    limiter.reset()
    app.config["TEST_RATELIMIT"] = False


def _login(client, username="manager1", password="ManagerPass1!"):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_login_rate_limit_blocks_after_5_attempts(rate_limit_client):
    """5 requests from same IP → 6th returns 429 regardless of credentials."""
    for _ in range(5):
        _login(rate_limit_client)

    rv = _login(rate_limit_client)
    assert rv.status_code == 429
    assert "too many" in rv.get_json()["error"].lower()


def test_login_rate_limit_resets_after_window(rate_limit_client, app):
    """After hitting the limit, resetting the storage allows login again."""
    for _ in range(5):
        _login(rate_limit_client)

    assert _login(rate_limit_client).status_code == 429

    # Simulate window expiry by resetting limiter storage
    limiter.reset()

    rv = _login(rate_limit_client)
    # After reset, a valid login should succeed (200) or fail on credentials (401)
    # — either way, NOT 429
    assert rv.status_code != 429


def test_login_rate_limit_per_ip_not_per_user(rate_limit_client):
    """
    Rate limit is per IP, not per username. Same IP with different usernames
    is still blocked collectively after 5 attempts.
    """
    users = ["manager1", "owner1", "waiter1", "kitchen1", "manager1"]
    passwords = ["ManagerPass1!", "OwnerPass1!", "WaiterPass1!", "KitchenPass1!", "ManagerPass1!"]
    for u, p in zip(users, passwords):
        client_post = rate_limit_client.post(
            "/auth/login", json={"username": u, "password": p}
        )

    # 6th attempt from same IP — different username, still blocked
    rv = rate_limit_client.post(
        "/auth/login", json={"username": "owner1", "password": "OwnerPass1!"}
    )
    assert rv.status_code == 429


def test_login_rate_limit_logged_to_audit(rate_limit_client, app):
    """Hitting the rate limit creates an AuditLog entry with action=auth.login.rate_limited."""
    audit_before = db.session.query(AuditLog).filter_by(
        action="auth.login.rate_limited"
    ).count()

    for _ in range(5):
        _login(rate_limit_client)
    _login(rate_limit_client)   # triggers limit

    audit_after = db.session.query(AuditLog).filter_by(
        action="auth.login.rate_limited"
    ).count()
    assert audit_after > audit_before
