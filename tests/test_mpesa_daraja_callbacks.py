"""
Tests for handle_c2b_callback() and handle_stk_callback().
Uses the `app` fixture from conftest (in-memory SQLite) — real DB writes, no mocking.
"""
import pytest
from app.finance import mpesa_daraja
from app.models.payment import Payment
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.pending_stk_push import PendingSTKPush
from app.models.audit_log import AuditLog
from app.extensions import db


@pytest.fixture(autouse=True)
def _reset_state(app):
    """Clear OAuth token cache and PendingSTKPush rows before and after each test."""
    mpesa_daraja._clear_token_cache()
    mpesa_daraja._clear_pending_stk()
    yield
    mpesa_daraja._clear_token_cache()
    mpesa_daraja._clear_pending_stk()


def _c2b_payload(trans_id="QJN4X3P1ZB", amount="1500.00", msisdn="254712345678"):
    return {
        "TransactionType": "Pay Bill",
        "TransID": trans_id,
        "TransAmount": amount,
        "BusinessShortCode": "123456",
        "BillRefNumber": "",
        "MSISDN": msisdn,
        "FirstName": "WACHIRA",
    }


def _stk_success_payload(checkout_id="ws_CO_99999", receipt="LMN8Z5A3VB", amount=750):
    return {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": amount},
                        {"Name": "MpesaReceiptNumber", "Value": receipt},
                        {"Name": "TransactionDate", "Value": 20260604120000},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                    ]
                },
            }
        }
    }


# ── C2B tests ─────────────────────────────────────────────────────────────────

def test_c2b_callback_success(app):
    """Valid C2B payload → Payment + Reconciliation created atomically."""
    ok, payment_id = mpesa_daraja.handle_c2b_callback(_c2b_payload())

    assert ok is True
    assert payment_id is not None

    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.mpesa_code == "QJN4X3P1ZB"
    assert p.method == "MPESA"
    assert p.received_by_id is None

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=payment_id).first()
    assert recon is not None
    assert recon.status == PaymentReconciliationStatus.MATCHED.value
    assert recon.matched is True
    assert recon.statement_ref == "QJN4X3P1ZB"


def test_c2b_callback_idempotent(app):
    """Same TransID twice → second call returns same payment_id, exactly 1 Payment row."""
    payload = _c2b_payload(trans_id="RKP7Y2Q4WC")

    ok1, pid1 = mpesa_daraja.handle_c2b_callback(payload)
    ok2, pid2 = mpesa_daraja.handle_c2b_callback(payload)

    assert ok1 is True
    assert ok2 is True
    assert pid1 == pid2

    count = db.session.query(Payment).filter_by(idempotency_key="RKP7Y2Q4WC").count()
    assert count == 1


# ── STK callback tests ────────────────────────────────────────────────────────

def test_stk_callback_success_links_tab(app):
    """STK success callback → Payment + Recon created, tab_id linked via checkout_request_id."""
    mpesa_daraja._register_pending_stk("ws_CO_99999", "tab-uuid-abc")

    ok, payment_id = mpesa_daraja.handle_stk_callback(
        _stk_success_payload(checkout_id="ws_CO_99999", receipt="LMN8Z5A3VB", amount=750)
    )

    assert ok is True

    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.mpesa_code == "LMN8Z5A3VB"
    assert p.tab_id == "tab-uuid-abc"

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=payment_id).first()
    assert recon is not None
    assert recon.status == PaymentReconciliationStatus.MATCHED.value

    # checkout_request_id should be deleted from the pending table after success
    row = db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_99999"
    ).first()
    assert row is None


# ── Invalid payload test ──────────────────────────────────────────────────────

def test_callback_invalid_payload_no_write(app):
    """Malformed C2B payload → (False, error), zero Payment/Recon rows written."""
    pmt_before   = db.session.query(Payment).count()
    recon_before = db.session.query(PaymentReconciliation).count()
    audit_before = db.session.query(AuditLog).count()

    ok, msg = mpesa_daraja.handle_c2b_callback({})   # empty — missing all required fields

    assert ok is False
    assert msg

    assert db.session.query(Payment).count()               == pmt_before
    assert db.session.query(PaymentReconciliation).count() == recon_before
    assert db.session.query(AuditLog).count()              == audit_before


# ── PendingSTKPush persistence tests ─────────────────────────────────────────

def test_pending_stk_persists_across_simulated_restart(app):
    """
    PendingSTKPush row survives a module-state reset (simulates server restart).
    After restart, handle_stk_callback still finds the tab_id via DB.
    """
    from datetime import datetime, timezone, timedelta

    # Directly insert a row (simulating what initiate_stk_push would have done
    # before the "restart")
    row = PendingSTKPush(
        checkout_request_id="ws_CO_RESTART_001",
        tab_id="tab-persist-abc",
        expires_at_utc=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.session.add(row)
    db.session.commit()

    # Module-level dict no longer exists — DB is the source of truth
    # (No state to clear since we use DB now — this assertion confirms it)
    assert db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_RESTART_001"
    ).count() == 1

    # Callback arrives and finds the tab_id
    ok, payment_id = mpesa_daraja.handle_stk_callback({
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_CO_RESTART_001",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 500},
                        {"Name": "MpesaReceiptNumber", "Value": "XYZ_PERSIST_001"},
                        {"Name": "TransactionDate", "Value": 20260605220000},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                    ]
                },
            }
        }
    })

    assert ok is True
    p = db.session.get(Payment, payment_id)
    assert p.tab_id == "tab-persist-abc"

    # Row cleaned up after successful callback
    assert db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_RESTART_001"
    ).count() == 0


def test_pending_stk_cleanup_removes_expired(app):
    """Cleanup function deletes expired rows and leaves non-expired rows intact."""
    from datetime import datetime, timezone, timedelta
    from app.finance.mpesa_daraja import cleanup_expired_pending_stk

    now = datetime.now(timezone.utc)
    # Insert one expired row and one non-expired row
    expired = PendingSTKPush(
        checkout_request_id="ws_CO_EXPIRED_001",
        tab_id="tab-expired",
        expires_at_utc=now - timedelta(minutes=10),   # already expired
    )
    fresh = PendingSTKPush(
        checkout_request_id="ws_CO_FRESH_001",
        tab_id="tab-fresh",
        expires_at_utc=now + timedelta(hours=1),       # not yet expired
    )
    db.session.add_all([expired, fresh])
    db.session.commit()

    deleted = cleanup_expired_pending_stk()

    assert deleted == 1
    assert db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_EXPIRED_001"
    ).count() == 0
    assert db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_FRESH_001"
    ).count() == 1


def test_pending_stk_unique_checkout_request_id(app):
    """Inserting a duplicate checkout_request_id raises an IntegrityError."""
    import pytest
    from datetime import datetime, timezone, timedelta
    from sqlalchemy.exc import IntegrityError

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    row1 = PendingSTKPush(
        checkout_request_id="ws_CO_DUP_001",
        tab_id="tab-a",
        expires_at_utc=expires,
    )
    db.session.add(row1)
    db.session.commit()

    row2 = PendingSTKPush(
        checkout_request_id="ws_CO_DUP_001",   # same checkout_request_id
        tab_id="tab-b",
        expires_at_utc=expires,
    )
    db.session.add(row2)
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
