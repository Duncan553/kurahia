"""
Tests for public webhook payload validation (Q-2.2).

All three public callback endpoints:
  POST /finance/mpesa/callback
  POST /finance/bank/sms-forward
  POST /finance/card/callback

Validation failures always return 200 (never trigger retries).
No Payment row is created from a rejected payload.
"""
import pytest
from app.models.payment import Payment, PaymentMethod
from app.extensions import db


def _oversized_body():
    """Generate a JSON payload just over 100KB."""
    # 100KB of 'x' packed into a string value
    padding = "x" * 102_400
    return {"data": padding}


# ── POST /finance/mpesa/callback ─────────────────────────────────────────────

def test_mpesa_callback_rejects_oversized_payload(client):
    """200KB payload → logged, 200 returned, no Payment written."""
    before = db.session.query(Payment).count()

    rv = client.post(
        "/finance/mpesa/callback",
        json=_oversized_body(),
    )
    assert rv.status_code == 200   # always-200 rule

    assert db.session.query(Payment).count() == before


def test_mpesa_callback_rejects_wrong_content_type(client):
    """text/plain Content-Type → validation rejected, 200 returned."""
    before = db.session.query(Payment).count()

    rv = client.post(
        "/finance/mpesa/callback",
        data="TransID=ABC&TransAmount=1000",
        content_type="text/plain",
    )
    assert rv.status_code == 200
    assert db.session.query(Payment).count() == before


# ── POST /finance/bank/sms-forward ───────────────────────────────────────────

def test_bank_sms_forward_rejects_oversized_payload(client, monkeypatch):
    """200KB payload → logged, 200 returned, no Payment written."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count()

    rv = client.post(
        "/finance/bank/sms-forward",
        json=_oversized_body(),
    )
    assert rv.status_code == 200

    assert db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count() == before


def test_bank_sms_forward_rejects_wrong_content_type(client, monkeypatch):
    """text/plain Content-Type → validation rejected, 200 returned."""
    monkeypatch.delenv("BANK_SMS_WEBHOOK_SECRET", raising=False)
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count()

    rv = client.post(
        "/finance/bank/sms-forward",
        data="from=+254700000001&body=test",
        content_type="text/plain",
    )
    assert rv.status_code == 200
    assert db.session.query(Payment).filter_by(
        method=PaymentMethod.BANK_TRANSFER.value
    ).count() == before


# ── POST /finance/card/callback ───────────────────────────────────────────────

def test_card_callback_rejects_oversized_payload(client):
    """200KB payload → logged, 200 returned, no Payment written."""
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count()

    rv = client.post(
        "/finance/card/callback",
        json=_oversized_body(),
    )
    assert rv.status_code == 200

    assert db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count() == before


def test_card_callback_rejects_wrong_content_type(client):
    """text/plain Content-Type → validation rejected, 200 returned."""
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count()

    rv = client.post(
        "/finance/card/callback",
        data="OrderTrackingId=TRACK001&Amount=1500",
        content_type="text/plain",
    )
    assert rv.status_code == 200
    assert db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count() == before
