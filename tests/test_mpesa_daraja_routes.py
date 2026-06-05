"""
Tests for the M-Pesa Daraja Flask routes (Step 1.5).

POST /finance/mpesa/charge  — cashier-initiated STK Push (manager auth)
POST /finance/mpesa/callback — Safaricom callback receiver (public)
GET  /finance/mpesa/status  — diagnostic endpoint (manager auth)
"""
import pytest
from app.finance import mpesa_daraja


@pytest.fixture(autouse=True)
def _reset_state(app):
    """Clear OAuth token cache and PendingSTKPush rows before and after each test."""
    mpesa_daraja._clear_token_cache()
    mpesa_daraja._clear_pending_stk()
    yield
    mpesa_daraja._clear_token_cache()
    mpesa_daraja._clear_pending_stk()


@pytest.fixture
def configured_env(monkeypatch):
    """Set all required env vars and pre-seed the token cache so no HTTP calls go out."""
    monkeypatch.setenv("MPESA_CONSUMER_KEY", "fake_key")
    monkeypatch.setenv("MPESA_CONSUMER_SECRET", "fake_secret")
    monkeypatch.setenv("MPESA_SHORTCODE", "174379")
    monkeypatch.setenv("MPESA_PASSKEY", "fake_passkey_value")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://example.com/callback")
    monkeypatch.setenv("MPESA_ENV", "sandbox")
    mpesa_daraja._token_cache["token"] = "fake_oauth_token"
    mpesa_daraja._token_cache["expires_at"] = 9_999_999_999


# ── POST /finance/mpesa/charge — auth ────────────────────────────────────────

def test_charge_requires_manager_role(client, waiter_token):
    """Waiter (role level < 5) → 403."""
    rv = client.post(
        "/finance/mpesa/charge",
        json={"amount": 100, "phone_number": "0712345678", "tab_id": "t1", "payment_id": "p1"},
        headers={"Authorization": f"Bearer {waiter_token}"},
    )
    assert rv.status_code == 403


def test_charge_requires_auth(client):
    """No token → 401."""
    rv = client.post(
        "/finance/mpesa/charge",
        json={"amount": 100, "phone_number": "0712345678", "tab_id": "t1", "payment_id": "p1"},
    )
    assert rv.status_code == 401


# ── POST /finance/mpesa/charge — dormant ─────────────────────────────────────

def test_charge_dormant_returns_503(client, manager_token, monkeypatch):
    """No env vars → 503 with plain-English error + fallback hint."""
    for var in mpesa_daraja.REQUIRED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    rv = client.post(
        "/finance/mpesa/charge",
        json={"amount": 100, "phone_number": "0712345678", "tab_id": "t1", "payment_id": "p1"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 503
    body = rv.get_json()
    assert "not configured" in body["error"].lower()
    assert "fallback" in body


# ── POST /finance/mpesa/charge — body validation ─────────────────────────────

def test_charge_missing_body_field(client, manager_token, configured_env):
    """Missing required field → 400 naming the missing field."""
    rv = client.post(
        "/finance/mpesa/charge",
        json={"amount": 100, "phone_number": "0712345678", "tab_id": "t1"},
        # payment_id absent
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 400
    assert "payment_id" in rv.get_json()["error"]


# ── POST /finance/mpesa/callback — public ────────────────────────────────────

def test_callback_public_no_auth_required(client):
    """No Authorization header → endpoint still accepts and returns 200."""
    # STK failure payload — callback handler writes audit log but no Payment row
    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_CO_TEST_001",
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user.",
            }
        }
    }
    rv = client.post("/finance/mpesa/callback", json=payload)
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["ResultCode"] == 0   # always 0 — Safaricom must not retry


# ── GET /finance/mpesa/status ─────────────────────────────────────────────────

def test_status_dormant(client, manager_token, monkeypatch):
    """No env vars → {"configured": false}."""
    for var in mpesa_daraja.REQUIRED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    rv = client.get(
        "/finance/mpesa/status",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["configured"] is False
    assert "message" in body


def test_status_configured(client, manager_token, configured_env):
    """All env vars present → {"configured": true}."""
    rv = client.get(
        "/finance/mpesa/status",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["configured"] is True
    assert "message" in body
