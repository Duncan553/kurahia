"""
Tests for OAuth token caching in mpesa_daraja socket.
Uses monkeypatch + httpx mocking — no real Daraja calls.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.finance import mpesa_daraja


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the OAuth token cache before each test."""
    mpesa_daraja._clear_token_cache()
    yield
    mpesa_daraja._clear_token_cache()


@pytest.fixture
def configured_env(monkeypatch):
    """Set the credentials env vars so OAuth proceeds past the early bail."""
    monkeypatch.setenv("MPESA_CONSUMER_KEY", "fake_key")
    monkeypatch.setenv("MPESA_CONSUMER_SECRET", "fake_secret")
    monkeypatch.setenv("MPESA_ENV", "sandbox")


def test_oauth_token_returns_error_when_credentials_missing(monkeypatch):
    """No env vars set → returns (None, plain English error)."""
    monkeypatch.delenv("MPESA_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("MPESA_CONSUMER_SECRET", raising=False)
    token, err = mpesa_daraja._get_oauth_token()
    assert token is None
    assert err is not None
    assert "credentials" in err.lower() or "not configured" in err.lower()


def test_oauth_token_fetch_success(configured_env):
    """Successful API call → returns (token, None) and caches."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"access_token": "fake_token_123", "expires_in": "3599"}
    fake_response.raise_for_status = MagicMock()

    with patch("app.finance.mpesa_daraja.httpx.get", return_value=fake_response) as mock_get:
        token, err = mpesa_daraja._get_oauth_token()
        assert token == "fake_token_123"
        assert err is None
        assert mock_get.call_count == 1


def test_oauth_token_cached_on_second_call(configured_env):
    """Second call within cache window does NOT re-hit the API."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"access_token": "fake_token_456"}
    fake_response.raise_for_status = MagicMock()

    with patch("app.finance.mpesa_daraja.httpx.get", return_value=fake_response) as mock_get:
        token1, _ = mpesa_daraja._get_oauth_token()
        token2, _ = mpesa_daraja._get_oauth_token()
        assert token1 == token2 == "fake_token_456"
        assert mock_get.call_count == 1  # ← THE critical assertion: only ONE network call


def test_oauth_token_timeout_returns_error(configured_env):
    """Network timeout → returns (None, timeout error message)."""
    import httpx as real_httpx
    with patch(
        "app.finance.mpesa_daraja.httpx.get",
        side_effect=real_httpx.TimeoutException("timed out"),
    ):
        token, err = mpesa_daraja._get_oauth_token()
        assert token is None
        assert "timed out" in err.lower() or "timeout" in err.lower()
