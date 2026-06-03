"""Tests for mpesa_daraja.py dormant-socket behaviour."""
import pytest
from app.finance.mpesa_daraja import (
    REQUIRED_ENV_VARS,
    is_configured,
    configuration_status,
    initiate_stk_push,
)


def test_is_configured_false_when_no_env(monkeypatch):
    for k in REQUIRED_ENV_VARS:
        monkeypatch.delenv(k, raising=False)

    assert is_configured() is False

    ready, msg = configuration_status()
    assert ready is False
    assert "missing env vars" in msg


def test_initiate_stk_push_dormant_returns_false(monkeypatch):
    for k in REQUIRED_ENV_VARS:
        monkeypatch.delenv(k, raising=False)

    success, msg = initiate_stk_push(100, "254712345678", "tab1", "pay1")
    assert success is False
    assert msg == "M-Pesa Daraja integration not configured."
