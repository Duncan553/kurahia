"""
Tests for card gateway socket (card_gateway.py).
Covers: config helpers, provider dispatch, initiation (mocked httpx), IPN handlers (real DB).
"""
import uuid
import pytest
import httpx
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.finance import card_gateway


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_pesapal_cache():
    """Clear Pesapal token cache before and after each test."""
    card_gateway._pesapal_token_cache["token"] = None
    card_gateway._pesapal_token_cache["expires_at"] = 0
    yield
    card_gateway._pesapal_token_cache["token"] = None
    card_gateway._pesapal_token_cache["expires_at"] = 0


@pytest.fixture
def base_card_env(monkeypatch):
    """Shared env vars required by all providers."""
    monkeypatch.setenv("CARD_PROVIDER", "pesapal")
    monkeypatch.setenv("CARD_API_KEY", "fake-api-key")
    monkeypatch.setenv("CARD_MERCHANT_ID", "fake-merchant-id")
    monkeypatch.setenv("CARD_IPN_URL", "https://relay.kurahia.com/finance/card/callback")


@pytest.fixture
def pesapal_env(monkeypatch, base_card_env):
    """Full Pesapal env + pre-seeded token cache."""
    monkeypatch.setenv("CARD_PESAPAL_API_BASE", "https://cybqa.pesapal.com/pesapalv3")
    card_gateway._pesapal_token_cache["token"] = "fake-pesapal-token"
    card_gateway._pesapal_token_cache["expires_at"] = 9_999_999_999


@pytest.fixture
def dpo_env(monkeypatch):
    """Full DPO env vars."""
    monkeypatch.setenv("CARD_PROVIDER", "dpo")
    monkeypatch.setenv("CARD_API_KEY", "fake-dpo-key")
    monkeypatch.setenv("CARD_MERCHANT_ID", "fake-dpo-merchant")
    monkeypatch.setenv("CARD_IPN_URL", "https://relay.kurahia.com/finance/card/callback")
    monkeypatch.setenv("CARD_DPO_COMPANY_TOKEN", "fake-company-token")
    monkeypatch.setenv("CARD_DPO_API_BASE", "https://secure.3gdirectpay.com")


@pytest.fixture
def cellulant_env(monkeypatch):
    """Full Cellulant env vars."""
    monkeypatch.setenv("CARD_PROVIDER", "cellulant")
    monkeypatch.setenv("CARD_API_KEY", "fake-cellulant-key")
    monkeypatch.setenv("CARD_MERCHANT_ID", "MERCH001")
    monkeypatch.setenv("CARD_IPN_URL", "https://relay.kurahia.com/finance/card/callback")
    monkeypatch.setenv("CARD_CELLULANT_API_BASE", "https://apis.cellulant.io")
    monkeypatch.setenv("CARD_CELLULANT_CLIENT_ID", "fake-client-id")


def _mock_resp(json_data, status_code=200):
    m = MagicMock()
    m.json.return_value = json_data
    m.status_code = status_code
    m.raise_for_status.return_value = None
    return m


def _mock_xml_resp(xml_text):
    m = MagicMock()
    m.text = xml_text
    m.status_code = 200
    m.raise_for_status.return_value = None
    return m


# ── Config helper tests ───────────────────────────────────────────────────────

def test_card_dormant_when_no_provider(monkeypatch):
    """CARD_PROVIDER unset → is_configured() False."""
    monkeypatch.delenv("CARD_PROVIDER", raising=False)
    assert card_gateway.is_configured() is False
    ok, msg = card_gateway.initiate_card_payment(100, "tab1", "pay1", customer_email="a@b.com")
    assert ok is False
    assert "not configured" in msg.lower()


def test_card_dormant_when_invalid_provider(monkeypatch):
    """CARD_PROVIDER=xyz (not supported) → is_configured() False."""
    monkeypatch.setenv("CARD_PROVIDER", "xyz")
    monkeypatch.setenv("CARD_API_KEY", "k")
    monkeypatch.setenv("CARD_MERCHANT_ID", "m")
    monkeypatch.setenv("CARD_IPN_URL", "https://example.com")
    assert card_gateway.is_configured() is False
    _, msg = card_gateway.configuration_status()
    assert "not supported" in msg.lower()


# ── Initiation dispatch tests ─────────────────────────────────────────────────

def test_initiate_pesapal_success(pesapal_env):
    """Valid Pesapal response → (True, dict with payment_url)."""
    mock_data = {
        "order_tracking_id": "TRACK-001",
        "redirect_url": "https://cybqa.pesapal.com/pay?id=TRACK-001",
        "merchant_reference": "pay1",
        "error": {"code": None, "message": None},
    }
    with patch("app.finance.card_gateway.httpx.post", return_value=_mock_resp(mock_data)):
        ok, result = card_gateway.initiate_card_payment(
            1500, "tab1", "pay1", customer_email="guest@hotel.com"
        )
    assert ok is True
    assert result["provider"] == "pesapal"
    assert "cybqa.pesapal.com" in result["payment_url"]
    assert result["transaction_ref"] == "TRACK-001"


def test_initiate_pesapal_missing_env_vars(monkeypatch, base_card_env):
    """CARD_PESAPAL_API_BASE missing → (False, 'env vars missing')."""
    monkeypatch.delenv("CARD_PESAPAL_API_BASE", raising=False)
    ok, msg = card_gateway._initiate_pesapal(
        Decimal("500"), "tab1", "pay1", "a@b.com", None
    )
    assert ok is False
    assert "env vars missing" in msg.lower()


def test_initiate_dpo_success(dpo_env):
    """DPO createToken success → (True, dict with payv2 URL)."""
    xml_resp = (
        '<?xml version="1.0"?><API3G>'
        "<Result>000</Result>"
        "<ResultExplanation>Token created</ResultExplanation>"
        "<TransToken>DPOTOKEN123</TransToken>"
        "<TransRef>REF001</TransRef>"
        "</API3G>"
    )
    with patch("app.finance.card_gateway.httpx.post", return_value=_mock_xml_resp(xml_resp)):
        ok, result = card_gateway.initiate_card_payment(
            2000, "tab2", "pay2", customer_email="guest@hotel.com"
        )
    assert ok is True
    assert result["provider"] == "dpo"
    assert "DPOTOKEN123" in result["payment_url"]
    assert result["transaction_ref"] == "DPOTOKEN123"


def test_initiate_cellulant_success(cellulant_env):
    """Valid Cellulant response → (True, dict with checkoutUrl)."""
    mock_data = {
        "statusCode": 200,
        "statusDescription": "Payment initiated",
        "checkoutUrl": "https://checkout.tingg.africa/pay?id=TX001",
        "merchantTransactionID": "pay3",
    }
    with patch("app.finance.card_gateway.httpx.post", return_value=_mock_resp(mock_data)):
        ok, result = card_gateway.initiate_card_payment(
            3000, "tab3", "pay3", customer_phone="0712345678"
        )
    assert ok is True
    assert result["provider"] == "cellulant"
    assert "tingg.africa" in result["payment_url"]


def test_initiate_validates_amount_positive_integer(pesapal_env):
    """amount=0 → (False, 'positive') BEFORE reaching provider."""
    ok, msg = card_gateway.initiate_card_payment(0, "tab1", "pay1", customer_email="a@b.com")
    assert ok is False
    assert "positive" in msg.lower()


def test_initiate_requires_customer_contact(pesapal_env):
    """No email AND no phone → (False, error) BEFORE reaching provider."""
    ok, msg = card_gateway.initiate_card_payment(500, "tab1", "pay1")
    assert ok is False
    assert "email" in msg.lower() or "phone" in msg.lower() or "contact" in msg.lower()


# ── IPN handler tests ─────────────────────────────────────────────────────────

def test_ipn_pesapal_creates_payment_and_reconciliation(app):
    """Valid Pesapal IPN → Payment + PaymentReconciliation created."""
    payload = {
        "OrderTrackingId": "TRACK-IPN-001",
        "OrderMerchantReference": "pay-pesapal-001",
        "OrderNotificationType": "IPNCHANGE",
        "Amount": "1500.00",
    }
    ok, payment_id = card_gateway.handle_card_ipn(payload)

    assert ok is True
    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.method == PaymentMethod.CARD.value
    assert p.amount == Decimal("1500.00")
    assert p.card_ref == "TRACK-IPN-001"
    assert p.idempotency_key == "cardipn-pesapal-TRACK-IPN-001"

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=payment_id).first()
    assert recon is not None
    assert recon.status == PaymentReconciliationStatus.MATCHED.value
    assert recon.matched is True


def test_ipn_dpo_creates_payment_and_reconciliation(app):
    """Valid DPO IPN → Payment + PaymentReconciliation created."""
    payload = {
        "TransactionApproval": "YES",
        "TransactionToken": "DPOTOKEN-IPN-001",
        "TransactionRef": "DPO-REF-001",
        "TransactionFinalAmount": "2000.00",
        "TransactionCurrency": "KES",
    }
    ok, payment_id = card_gateway.handle_card_ipn(payload)

    assert ok is True
    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.method == PaymentMethod.CARD.value
    assert p.amount == Decimal("2000.00")
    assert p.idempotency_key == "cardipn-dpo-DPOTOKEN-IPN-001"

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=payment_id).first()
    assert recon.status == PaymentReconciliationStatus.MATCHED.value


def test_ipn_duplicate_transaction_ref_idempotent(app):
    """Same IPN payload twice → only 1 Payment row, both calls return same payment_id."""
    payload = {
        "OrderTrackingId": "TRACK-IDEM-001",
        "OrderMerchantReference": "pay-idem",
        "Amount": "750.00",
    }
    ok1, pid1 = card_gateway.handle_card_ipn(payload)
    ok2, pid2 = card_gateway.handle_card_ipn(payload)

    assert ok1 is True
    assert ok2 is True
    assert pid1 == pid2

    count = db.session.query(Payment).filter_by(
        idempotency_key="cardipn-pesapal-TRACK-IDEM-001"
    ).count()
    assert count == 1


def test_ipn_unrecognized_format_no_writes(app):
    """Unknown IPN payload → (False, error), no Payment row created."""
    before = db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count()

    ok, msg = card_gateway.handle_card_ipn({"some_random_field": "value"})

    assert ok is False
    assert "unrecognized" in msg.lower()

    after = db.session.query(Payment).filter_by(
        method=PaymentMethod.CARD.value
    ).count()
    assert after == before
