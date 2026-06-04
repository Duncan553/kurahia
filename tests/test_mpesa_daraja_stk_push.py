"""
Tests for initiate_stk_push().
Uses monkeypatch + httpx mocking — no real Daraja calls.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.finance import mpesa_daraja


@pytest.fixture(autouse=True)
def _clear_cache():
    mpesa_daraja._clear_token_cache()
    yield
    mpesa_daraja._clear_token_cache()


@pytest.fixture
def configured_env(monkeypatch):
    """Full configuration set so STK Push proceeds past dormancy + OAuth bails."""
    monkeypatch.setenv("MPESA_CONSUMER_KEY", "fake_key")
    monkeypatch.setenv("MPESA_CONSUMER_SECRET", "fake_secret")
    monkeypatch.setenv("MPESA_SHORTCODE", "174379")
    monkeypatch.setenv("MPESA_PASSKEY", "fake_passkey_value")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://example.com/callback")
    monkeypatch.setenv("MPESA_ENV", "sandbox")
    # Pre-load the cache so _get_oauth_token() returns instantly without httpx
    mpesa_daraja._token_cache["token"] = "fake_oauth_token"
    mpesa_daraja._token_cache["expires_at"] = 9_999_999_999


def test_stk_push_dormant_returns_error(monkeypatch):
    """No env vars → returns (False, 'not configured')."""
    for var in mpesa_daraja.REQUIRED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    ok, msg = mpesa_daraja.initiate_stk_push(100, "254712345678", "tab1", "pay1")
    assert ok is False
    assert "not configured" in msg.lower()


def test_stk_push_invalid_phone(configured_env):
    """Non-Kenyan format → returns (False, 'Invalid Kenyan phone')."""
    ok, msg = mpesa_daraja.initiate_stk_push(100, "12345", "tab1", "pay1")
    assert ok is False
    assert "invalid" in msg.lower() and "phone" in msg.lower()


def test_stk_push_invalid_amount(configured_env):
    """Non-int or zero amount → returns (False, 'positive integer')."""
    for bad_amount in [0, -100, 99.5, "100", None]:
        ok, msg = mpesa_daraja.initiate_stk_push(bad_amount, "254712345678", "tab1", "pay1")
        assert ok is False
        assert "positive integer" in msg.lower()


def test_stk_push_success(configured_env):
    """Valid input + Daraja success → returns (True, {checkout_request_id...})."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "ResponseCode": "0",
        "CheckoutRequestID": "ws_CO_12345",
        "MerchantRequestID": "29115-34620561-1",
        "CustomerMessage": "Success. Request accepted for processing",
    }
    fake_response.raise_for_status = MagicMock()

    with patch("app.finance.mpesa_daraja.httpx.post", return_value=fake_response):
        ok, data = mpesa_daraja.initiate_stk_push(100, "0712345678", "tab1", "pay1")
        assert ok is True
        assert data["checkout_request_id"] == "ws_CO_12345"
        assert "customer_message" in data


def test_stk_push_daraja_rejection(configured_env):
    """Daraja returns non-zero ResponseCode → returns (False, 'rejected by Daraja')."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "ResponseCode": "1",
        "ResponseDescription": "The balance is insufficient",
    }
    fake_response.raise_for_status = MagicMock()

    with patch("app.finance.mpesa_daraja.httpx.post", return_value=fake_response):
        ok, msg = mpesa_daraja.initiate_stk_push(100, "254712345678", "tab1", "pay1")
        assert ok is False
        assert "rejected by daraja" in msg.lower()
        assert "balance is insufficient" in msg.lower()


def test_stk_push_phone_normalization(configured_env):
    """All Kenyan formats normalize to 254... in PartyA / PhoneNumber."""
    captured_payloads = []

    def capture_post(*args, **kwargs):
        captured_payloads.append(kwargs.get("json"))
        fake = MagicMock()
        fake.json.return_value = {
            "ResponseCode": "0",
            "CheckoutRequestID": "x",
            "MerchantRequestID": "y",
            "CustomerMessage": "z",
        }
        fake.raise_for_status = MagicMock()
        return fake

    with patch("app.finance.mpesa_daraja.httpx.post", side_effect=capture_post):
        for input_phone in ["0712345678", "+254712345678", "254712345678"]:
            captured_payloads.clear()
            mpesa_daraja.initiate_stk_push(100, input_phone, "tab1", "pay1")
            assert captured_payloads[0]["PhoneNumber"] == "254712345678"
            assert captured_payloads[0]["PartyA"] == "254712345678"
