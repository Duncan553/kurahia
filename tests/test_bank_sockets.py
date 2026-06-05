"""
Tests for bank socket — manual reconciliation routes (bank.py) and SMS forwarder (bank_transfer.py).

Manual routes: hit via test client (HTTP).
SMS forwarder: call handle_sms_forward() directly (Flask routes added in Step 2.5).
"""
import uuid
import pytest
import httpx
from decimal import Decimal
from datetime import datetime, timezone

from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.judge_alert import JudgeAlert
from app.finance import bank_transfer


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sms_env(monkeypatch):
    """Set the SMS webhook secret so is_sms_configured() returns True."""
    monkeypatch.setenv("BANK_SMS_WEBHOOK_SECRET", "test-secret-abc")


@pytest.fixture
def bank_payment(app):
    """A BANK_TRANSFER Payment with no reconciliation row — shows as pending."""
    p = Payment(
        method=PaymentMethod.BANK_TRANSFER.value,
        amount=Decimal("5000.00"),
        bank_ref="FT2606050001",
        idempotency_key=f"test-bank-{uuid.uuid4()}",
        description="Test bank transfer",
    )
    db.session.add(p)
    db.session.commit()
    return p


def _equity_sms(ref="EQT20260605X1", amount="2,400.00"):
    return {
        "secret": "test-secret-abc",
        "from": "+254719000001",
        "body": (
            f"Equity Bank: KES {amount} received from JOHN DOE. "
            f"Ref: {ref} on 05/06/2026 at 22:00."
        ),
    }


def _kcb_sms(ref="KCB98765ABC", amount="1,500.00"):
    return {
        "secret": "test-secret-abc",
        "from": "+254711000001",
        "body": (
            f"KCB Bank: Ksh{amount} received from 254712000001 "
            f"on 05/06/2026. Ref {ref}."
        ),
    }


# ── Manual route tests ────────────────────────────────────────────────────────

def test_bank_pending_requires_manager_role(client, waiter_token):
    """Waiter (role level < 5) → 403 on GET /finance/bank/pending."""
    rv = client.get(
        "/finance/bank/pending?date=2026-06-05",
        headers={"Authorization": f"Bearer {waiter_token}"},
    )
    assert rv.status_code == 403


def test_bank_reconcile_match_creates_reconciliation(client, manager_token, bank_payment):
    """POST /finance/bank/reconcile with action=MATCH → PaymentReconciliation row MATCHED."""
    rv = client.post(
        "/finance/bank/reconcile",
        json={"entries": [{
            "payment_id":    bank_payment.id,
            "action":        "MATCH",
            "statement_ref": "FT2606050001",
            "notes":         "Confirmed on bank statement",
        }]},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["reconciled"] == 1
    assert body["flagged"] == 0

    recon = db.session.query(PaymentReconciliation).filter_by(
        payment_id=bank_payment.id
    ).first()
    assert recon is not None
    assert recon.status == PaymentReconciliationStatus.MATCHED.value
    assert recon.matched is True
    assert recon.statement_ref == "FT2606050001"


def test_bank_reconcile_flag_fires_judge_alert(client, manager_token, bank_payment):
    """POST /finance/bank/reconcile with action=FLAG → FLAGGED recon + JudgeAlert."""
    rv = client.post(
        "/finance/bank/reconcile",
        json={"entries": [{
            "payment_id":    bank_payment.id,
            "action":        "FLAG",
            "statement_ref": None,
            "notes":         "Could not verify on statement",
        }]},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["flagged"] == 1

    recon = db.session.query(PaymentReconciliation).filter_by(
        payment_id=bank_payment.id
    ).first()
    assert recon.status == PaymentReconciliationStatus.FLAGGED.value
    assert recon.matched is False

    alert = db.session.query(JudgeAlert).filter_by(alert_type="BANK_FLAGGED").first()
    assert alert is not None
    assert "flagged" in alert.description.lower()


# ── SMS forwarder tests ───────────────────────────────────────────────────────

def test_sms_forward_dormant_returns_error(app, monkeypatch):
    """No BANK_SMS_WEBHOOK_SECRET → (False, 'not configured')."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    ok, msg = bank_transfer.handle_sms_forward(_equity_sms(), "any-secret")
    assert ok is False
    assert "not configured" in msg.lower()


def test_sms_forward_equity_bank_parses_correctly(app, sms_env):
    """Valid Equity SMS → Payment + PaymentReconciliation created with correct values."""
    payload = _equity_sms(ref="EQT2026060501", amount="2,400.00")
    ok, payment_id = bank_transfer.handle_sms_forward(payload, "test-secret-abc")

    assert ok is True
    assert payment_id is not None

    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.method == PaymentMethod.BANK_TRANSFER.value
    assert p.amount == Decimal("2400.00")
    assert p.bank_ref == "EQT2026060501"
    assert p.idempotency_key == "banksms-EQT2026060501"

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=payment_id).first()
    assert recon is not None
    assert recon.status == PaymentReconciliationStatus.MATCHED.value
    assert recon.matched is True


def test_sms_forward_kcb_parses_correctly(app, sms_env):
    """Valid KCB SMS → Payment created with correct bank_ref and amount."""
    payload = _kcb_sms(ref="KCB20260605X2", amount="3,750.00")
    ok, payment_id = bank_transfer.handle_sms_forward(payload, "test-secret-abc")

    assert ok is True
    p = db.session.get(Payment, payment_id)
    assert p.method == PaymentMethod.BANK_TRANSFER.value
    assert p.amount == Decimal("3750.00")
    assert p.bank_ref == "KCB20260605X2"


def test_sms_forward_duplicate_bank_ref_idempotent(app, sms_env):
    """Same bank_ref twice → second call returns same payment_id, exactly 1 Payment row."""
    payload = _equity_sms(ref="EQTIDEM0001")
    ok1, pid1 = bank_transfer.handle_sms_forward(payload, "test-secret-abc")
    ok2, pid2 = bank_transfer.handle_sms_forward(payload, "test-secret-abc")

    assert ok1 is True
    assert ok2 is True
    assert pid1 == pid2

    count = db.session.query(Payment).filter_by(idempotency_key="banksms-EQTIDEM0001").count()
    assert count == 1


def test_sms_forward_unrecognized_format_returns_error_no_writes(app, sms_env):
    """Garbage SMS body → (False, error message), no Payment row created."""
    payload = {
        "secret": "test-secret-abc",
        "from":   "+254700000000",
        "body":   "Your OTP is 123456. Do not share it.",
    }
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count()

    ok, msg = bank_transfer.handle_sms_forward(payload, "test-secret-abc")

    assert ok is False
    assert "not recognized" in msg.lower()

    after = db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count()
    assert after == before   # no new Payment row written


# ── Step 2.2: provider dispatch tests ────────────────────────────

@pytest.fixture
def api_env(monkeypatch):
    """Set env vars for a valid bank API configuration (Equity)."""
    monkeypatch.setenv("BANK_PROVIDER", "equity")
    monkeypatch.setenv("BANK_API_KEY", "fake-api-key-001")


def test_verify_bank_transfer_dormant_no_provider(monkeypatch):
    """BANK_PROVIDER unset → is_api_configured() False → verify returns dormancy error."""
    monkeypatch.delenv("BANK_PROVIDER", raising=False)
    monkeypatch.delenv("BANK_API_KEY", raising=False)
    ok, msg = bank_transfer.verify_bank_transfer(Decimal("500"), "REF001")
    assert ok is False
    assert "not configured" in msg.lower()


def test_verify_bank_transfer_invalid_provider(monkeypatch):
    """BANK_PROVIDER=xyz (not in SUPPORTED_PROVIDERS) → treated as dormant."""
    monkeypatch.setenv("BANK_PROVIDER", "xyz")
    monkeypatch.setenv("BANK_API_KEY", "fake-key")
    assert bank_transfer.is_api_configured() is False
    ok, msg = bank_transfer.verify_bank_transfer(Decimal("500"), "REF001")
    assert ok is False
    assert "not configured" in msg.lower()


def test_verify_bank_transfer_dispatches_to_equity(monkeypatch, api_env):
    """BANK_PROVIDER=equity → reaches _verify_equity (proven by Equity-specific env var error)."""
    # No BANK_EQUITY_* vars set — _verify_equity returns its own env var error, not the generic one
    monkeypatch.delenv("BANK_EQUITY_API_KEY", raising=False)
    ok, msg = bank_transfer.verify_bank_transfer(Decimal("1000"), "EQTREF001")
    assert ok is False
    assert "equity api env vars missing" in msg.lower()


def test_verify_bank_transfer_dispatches_to_kcb(monkeypatch):
    """BANK_PROVIDER=kcb → reaches _verify_kcb (proven by KCB-specific env var error)."""
    monkeypatch.setenv("BANK_PROVIDER", "kcb")
    monkeypatch.setenv("BANK_API_KEY", "fake-api-key-002")
    monkeypatch.delenv("BANK_KCB_CLIENT_ID", raising=False)
    ok, msg = bank_transfer.verify_bank_transfer(Decimal("1000"), "KCBREF001")
    assert ok is False
    assert "kcb api env vars missing" in msg.lower()


def test_verify_bank_transfer_invalid_amount(api_env):
    """amount=0 → (False, 'Amount must be a positive number.') BEFORE reaching provider."""
    ok, msg = bank_transfer.verify_bank_transfer(0, "EQTREF002")
    assert ok is False
    assert "positive" in msg.lower()


def test_configuration_status_includes_provider_name(monkeypatch, api_env):
    """BANK_PROVIDER=equity → status message contains 'equity'."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    sms_ready, api_ready, msg = bank_transfer.configuration_status()
    assert api_ready is True
    assert "equity" in msg.lower()


# ── Step 2.3: provider HTTP implementation tests ──────────────────

from unittest.mock import patch, MagicMock


def _mock_resp(json_data, status_code=200):
    """Build a mock httpx response."""
    m = MagicMock()
    m.json.return_value = json_data
    m.status_code = status_code
    m.raise_for_status.return_value = None
    return m


@pytest.fixture
def equity_env(monkeypatch, api_env):
    """Add Equity-specific env vars on top of the base api_env fixture."""
    monkeypatch.setenv("BANK_EQUITY_API_BASE", "https://sandbox.equitybankgroup.com")
    monkeypatch.setenv("BANK_EQUITY_API_KEY", "fake-equity-key")
    monkeypatch.setenv("BANK_EQUITY_MERCHANT_CODE", "MERCH001")


@pytest.fixture
def kcb_env(monkeypatch):
    """Set env vars for KCB provider (includes BANK_PROVIDER + API creds)."""
    monkeypatch.setenv("BANK_PROVIDER", "kcb")
    monkeypatch.setenv("BANK_API_KEY", "fake-kcb-api-key")
    monkeypatch.setenv("BANK_KCB_API_BASE", "https://uat.buni.kcbgroup.com")
    monkeypatch.setenv("BANK_KCB_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("BANK_KCB_CLIENT_SECRET", "fake-client-secret")
    # Clear token cache so each test starts fresh
    bank_transfer._kcb_token_cache["token"] = None
    bank_transfer._kcb_token_cache["expires_at"] = 0


@pytest.fixture
def coop_env(monkeypatch):
    monkeypatch.setenv("BANK_PROVIDER", "coop")
    monkeypatch.setenv("BANK_API_KEY", "fake-coop-api-key")
    monkeypatch.setenv("BANK_COOP_API_BASE", "https://developer.co-opbank.co.ke:8243")
    monkeypatch.setenv("BANK_COOP_USERNAME", "fake-coop-user")
    monkeypatch.setenv("BANK_COOP_PASSWORD", "fake-coop-pass")


def test_verify_equity_success(equity_env):
    """Valid Equity response → (True, dict) with correct provider and amount."""
    mock_data = {"status": "SUCCESS", "amount": "1500.00", "transactionDate": "2026-06-05"}
    with patch("app.finance.bank_transfer.httpx.get", return_value=_mock_resp(mock_data)):
        ok, result = bank_transfer._verify_equity(Decimal("1500.00"), "EQTREF001", "")
    assert ok is True
    assert result["provider"] == "equity"
    assert result["details"]["confirmed_amount"] == "1500.00"
    assert "verified_at" in result


def test_verify_equity_amount_mismatch(equity_env):
    """Equity confirms different amount → (False, 'Amount mismatch')."""
    mock_data = {"status": "SUCCESS", "amount": "999.00", "transactionDate": "2026-06-05"}
    with patch("app.finance.bank_transfer.httpx.get", return_value=_mock_resp(mock_data)):
        ok, msg = bank_transfer._verify_equity(Decimal("1500.00"), "EQTREF002", "")
    assert ok is False
    assert "mismatch" in msg.lower()


def test_verify_kcb_success(kcb_env):
    """KCB: token fetch + query both succeed → (True, dict)."""
    token_resp = _mock_resp({"access_token": "tok-abc", "expires_in": 3600})
    query_resp = _mock_resp({"status": "SUCCESS", "amount": "2000.00", "transactionDate": "2026-06-05"})
    with patch("app.finance.bank_transfer.httpx.post", return_value=token_resp), \
         patch("app.finance.bank_transfer.httpx.get", return_value=query_resp):
        ok, result = bank_transfer._verify_kcb(Decimal("2000.00"), "KCBREF001", "")
    assert ok is True
    assert result["provider"] == "kcb"
    assert result["details"]["confirmed_amount"] == "2000.00"


def test_verify_coop_success(coop_env):
    """Co-op confirms transfer → (True, dict)."""
    mock_data = {"Successful": True, "Amount": "3500.00", "TransactionDate": "2026-06-05"}
    with patch("app.finance.bank_transfer.httpx.get", return_value=_mock_resp(mock_data)):
        ok, result = bank_transfer._verify_coop(Decimal("3500.00"), "COOPREF001", "")
    assert ok is True
    assert result["provider"] == "coop"
    assert result["details"]["confirmed_amount"] == "3500.00"


def test_verify_provider_network_timeout(equity_env):
    """httpx.TimeoutException → (False, '...timed out...')."""
    with patch("app.finance.bank_transfer.httpx.get", side_effect=httpx.TimeoutException("timeout")):
        ok, msg = bank_transfer._verify_equity(Decimal("1000.00"), "EQTREF003", "")
    assert ok is False
    assert "timed out" in msg.lower()


def test_verify_provider_missing_env_vars(monkeypatch, api_env):
    """BANK_PROVIDER=equity + BANK_API_KEY set but Equity-specific vars missing → plain error."""
    # api_env sets BANK_PROVIDER=equity and BANK_API_KEY — is_api_configured() is True
    # but _verify_equity's own env check catches missing BANK_EQUITY_API_KEY etc.
    monkeypatch.delenv("BANK_EQUITY_API_KEY", raising=False)
    monkeypatch.delenv("BANK_EQUITY_API_BASE", raising=False)
    monkeypatch.delenv("BANK_EQUITY_MERCHANT_CODE", raising=False)
    ok, msg = bank_transfer._verify_equity(Decimal("1000.00"), "EQTREF004", "")
    assert ok is False
    assert "env vars missing" in msg.lower()


# ── Step 2.4: Flask route tests ───────────────────────────────────

def test_bank_sms_forward_public_no_auth_required(client, monkeypatch):
    """No BANK_SMS_WEBHOOK_SECRET set → endpoint accepts without any header, returns 200."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    rv = client.post(
        "/finance/bank/sms-forward",
        json={"from": "+254700000001", "body": "Some random text."},
    )
    assert rv.status_code == 200


def test_bank_sms_forward_with_webhook_secret_required(client, monkeypatch):
    """BANK_SMS_WEBHOOK_SECRET set, X-Webhook-Secret header missing → 401."""
    monkeypatch.setenv("BANK_SMS_WEBHOOK_SECRET", "super-secret-key")
    rv = client.post(
        "/finance/bank/sms-forward",
        json={"from": "+254700000001", "body": "Some random text."},
        # no X-Webhook-Secret header
    )
    assert rv.status_code == 401


def test_bank_sms_forward_with_correct_secret(client, monkeypatch):
    """BANK_SMS_WEBHOOK_SECRET set, correct X-Webhook-Secret header → 200 regardless of SMS content."""
    monkeypatch.setenv("BANK_SMS_WEBHOOK_SECRET", "super-secret-key")
    rv = client.post(
        "/finance/bank/sms-forward",
        json={"from": "+254700000001", "body": "Unrecognized SMS format."},
        headers={"X-Webhook-Secret": "super-secret-key"},
    )
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "accepted"


def test_bank_verify_requires_manager_role(client, waiter_token):
    """Waiter token → 403 on POST /finance/bank/verify."""
    rv = client.post(
        "/finance/bank/verify",
        json={"amount": 1000, "bank_ref": "EQTREF001"},
        headers={"Authorization": f"Bearer {waiter_token}"},
    )
    assert rv.status_code == 403


def test_bank_verify_dormant_returns_503(client, manager_token, monkeypatch):
    """No bank API configured → 503 with fallback message."""
    monkeypatch.delenv("BANK_PROVIDER", raising=False)
    monkeypatch.delenv("BANK_API_KEY", raising=False)
    rv = client.post(
        "/finance/bank/verify",
        json={"amount": 1000, "bank_ref": "EQTREF001"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 503
    body = rv.get_json()
    assert "not configured" in body["error"].lower()
    assert "fallback" in body


def test_bank_status_returns_dual_state(client, manager_token, monkeypatch):
    """GET /finance/bank/status returns both sms_configured and api_configured fields."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("BANK_PROVIDER", raising=False)
    monkeypatch.delenv("BANK_API_KEY", raising=False)
    rv = client.get(
        "/finance/bank/status",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert "sms_configured" in body
    assert "api_configured" in body
    assert body["sms_configured"] is False
    assert body["api_configured"] is False
    assert "message" in body
