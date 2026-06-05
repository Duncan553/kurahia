"""
Tests for bank socket — manual reconciliation routes (bank.py) and SMS forwarder (bank_transfer.py).

Manual routes: hit via test client (HTTP).
SMS forwarder: call handle_sms_forward() directly (Flask routes added in Step 2.5).
"""
import uuid
import pytest
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
    """BANK_PROVIDER=equity → dispatches to _verify_equity (confirmed by NotImplementedError)."""
    # _verify_equity raises NotImplementedError — that's the proof it was reached
    with pytest.raises(NotImplementedError, match="Equity"):
        bank_transfer.verify_bank_transfer(Decimal("1000"), "EQTREF001")


def test_verify_bank_transfer_dispatches_to_kcb(monkeypatch):
    """BANK_PROVIDER=kcb → dispatches to _verify_kcb."""
    monkeypatch.setenv("BANK_PROVIDER", "kcb")
    monkeypatch.setenv("BANK_API_KEY", "fake-api-key-002")
    with pytest.raises(NotImplementedError, match="KCB"):
        bank_transfer.verify_bank_transfer(Decimal("1000"), "KCBREF001")


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
