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
    from app.models.tab import Tab
    from app.models.user import User
    user = db.session.query(User).first()
    tab = Tab(status="OPEN", opened_by_id=user.id)
    db.session.add(tab)
    db.session.flush()

    mpesa_daraja._register_pending_stk("ws_CO_99999", tab.id)

    ok, payment_id = mpesa_daraja.handle_stk_callback(
        _stk_success_payload(checkout_id="ws_CO_99999", receipt="LMN8Z5A3VB", amount=750)
    )

    assert ok is True

    p = db.session.get(Payment, payment_id)
    assert p is not None
    assert p.mpesa_code == "LMN8Z5A3VB"
    assert p.tab_id == tab.id

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

    from app.models.tab import Tab
    from app.models.user import User
    user = db.session.query(User).first()
    tab = Tab(status="OPEN", opened_by_id=user.id)
    db.session.add(tab)
    db.session.flush()

    row = PendingSTKPush(
        checkout_request_id="ws_CO_RESTART_001",
        tab_id=tab.id,
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
    assert p.tab_id == tab.id

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


def test_stk_callback_claims_the_till_payment_instead_of_doubling(app):
    """
    The till creates the Payment row before asking for the prompt (the charge
    endpoint needs something to reference). When Safaricom confirms, that row
    must be CLAIMED — not joined by a second one, which would clear the tab
    twice on one guest's single payment.
    """
    from app.models.tab import Tab
    from app.models.user import User
    from decimal import Decimal
    user = db.session.query(User).first()
    tab = Tab(status="OPEN", opened_by_id=user.id)
    db.session.add(tab)
    db.session.flush()

    # What the till writes before it calls /finance/mpesa/charge
    till_row = Payment(
        tab_id=tab.id, amount=Decimal("750.00"), method="MPESA",
        received_by_id=user.id, idempotency_key="till-uuid-1",
    )
    db.session.add(till_row)
    db.session.flush()

    mpesa_daraja._register_pending_stk("ws_CO_CLAIM", tab.id, till_row.id)

    ok, payment_id = mpesa_daraja.handle_stk_callback(
        _stk_success_payload(checkout_id="ws_CO_CLAIM", receipt="CLAIM123XY", amount=750)
    )

    assert ok is True
    assert payment_id == till_row.id          # the same row, not a new one
    assert db.session.query(Payment).filter_by(tab_id=tab.id).count() == 1
    assert db.session.get(Payment, till_row.id).mpesa_code == "CLAIM123XY"

    recon = db.session.query(PaymentReconciliation).filter_by(payment_id=till_row.id).first()
    assert recon.status == PaymentReconciliationStatus.MATCHED.value

    # A retried callback must not add a second row either
    ok2, payment_id2 = mpesa_daraja.handle_stk_callback(
        _stk_success_payload(checkout_id="ws_CO_CLAIM", receipt="CLAIM123XY", amount=750)
    )
    assert ok2 is True and payment_id2 == till_row.id
    assert db.session.query(Payment).filter_by(tab_id=tab.id).count() == 1


def test_stk_callback_confirmed_amount_wins_over_the_expectation(app):
    """
    If Safaricom confirms a different amount than the till expected, the money
    that actually moved is what the tab records — and the correction is audited,
    not silent.
    """
    from app.models.tab import Tab
    from app.models.user import User
    from decimal import Decimal
    user = db.session.query(User).first()
    tab = Tab(status="OPEN", opened_by_id=user.id)
    db.session.add(tab)
    db.session.flush()

    till_row = Payment(
        tab_id=tab.id, amount=Decimal("750.00"), method="MPESA",
        received_by_id=user.id, idempotency_key="till-uuid-2",
    )
    db.session.add(till_row)
    db.session.flush()
    mpesa_daraja._register_pending_stk("ws_CO_DIFF", tab.id, till_row.id)

    ok, payment_id = mpesa_daraja.handle_stk_callback(
        _stk_success_payload(checkout_id="ws_CO_DIFF", receipt="DIFF456ZZ", amount=500)
    )

    assert ok is True
    assert Decimal(str(db.session.get(Payment, payment_id).amount)) == Decimal("500")
    assert db.session.query(AuditLog).filter_by(
        action="payment.stk_amount_corrected").count() == 1


def test_initiate_stk_push_records_the_payment_it_was_asked_about(app, monkeypatch):
    """
    The wiring, not just the callback: initiate_stk_push() must persist the
    payment_id it was handed. Without it the callback has nothing to claim and
    silently creates a second payment — the double-pay this pair guards.
    """
    for k, v in {
        "MPESA_CONSUMER_KEY": "k", "MPESA_CONSUMER_SECRET": "s",
        "MPESA_SHORTCODE": "174379", "MPESA_PASSKEY": "p",
        "MPESA_CALLBACK_URL": "https://example.com/cb", "MPESA_ENV": "sandbox",
    }.items():
        monkeypatch.setenv(k, v)

    monkeypatch.setattr(mpesa_daraja, "_get_oauth_token", lambda: ("tok", None))

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {
            "ResponseCode": "0", "CheckoutRequestID": "ws_CO_WIRE",
            "MerchantRequestID": "m1", "CustomerMessage": "Check your phone",
        }
    monkeypatch.setattr(mpesa_daraja.httpx, "post", lambda *a, **kw: _Resp())

    ok, result = mpesa_daraja.initiate_stk_push(
        amount=750, phone_number="0712345678", tab_id="tab-1", payment_id="pay-1",
    )

    assert ok is True
    row = db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_WIRE").first()
    assert row.payment_id == "pay-1"


def test_charge_leaves_no_payment_behind_when_the_prompt_fails(client, app, waiter_token, monkeypatch):
    """
    The hole this endpoint was reshaped to close: a prompt that fails to send
    must leave NO payment row. The till used to write the row itself, so a
    failed prompt left a bill reading SETTLED against money nobody asked for.
    """
    for k, v in {
        "MPESA_CONSUMER_KEY": "k", "MPESA_CONSUMER_SECRET": "s",
        "MPESA_SHORTCODE": "174379", "MPESA_PASSKEY": "p",
        "MPESA_CALLBACK_URL": "https://example.com/cb", "MPESA_ENV": "sandbox",
    }.items():
        monkeypatch.setenv(k, v)

    # Daraja refuses — the shape of a dead socket, a bad number, a timeout
    monkeypatch.setattr(mpesa_daraja, "_get_oauth_token", lambda: (None, "Daraja OAuth failed"))

    hdr = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = client.post("/tabs", json={}, headers=hdr).get_json()["id"]

    before = db.session.query(Payment).count()

    rv = client.post("/finance/mpesa/charge",
                     json={"tab_id": tab_id, "amount": 1500, "phone_number": "0712345678",
                           "idempotency_key": "till-fail-1"},
                     headers=hdr)

    assert rv.status_code == 400, rv.get_json()
    assert db.session.query(Payment).count() == before
    assert db.session.query(Payment).filter_by(idempotency_key="till-fail-1").first() is None


def test_charge_creates_exactly_one_payment_when_the_prompt_goes_out(client, app, waiter_token, monkeypatch):
    """The success path: one payment row, linked to the tab, and the pending
    row carries its id so the callback claims it instead of doubling it."""
    for k, v in {
        "MPESA_CONSUMER_KEY": "k", "MPESA_CONSUMER_SECRET": "s",
        "MPESA_SHORTCODE": "174379", "MPESA_PASSKEY": "p",
        "MPESA_CALLBACK_URL": "https://example.com/cb", "MPESA_ENV": "sandbox",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(mpesa_daraja, "_get_oauth_token", lambda: ("tok", None))

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {
            "ResponseCode": "0", "CheckoutRequestID": "ws_CO_ROUTE",
            "MerchantRequestID": "m1", "CustomerMessage": "Check your phone",
        }
    monkeypatch.setattr(mpesa_daraja.httpx, "post", lambda *a, **kw: _Resp())

    hdr = {"Authorization": f"Bearer {waiter_token}"}
    tab_id = client.post("/tabs", json={}, headers=hdr).get_json()["id"]

    rv = client.post("/finance/mpesa/charge",
                     json={"tab_id": tab_id, "amount": 1500, "phone_number": "0712345678",
                           "idempotency_key": "till-ok-1"},
                     headers=hdr)
    assert rv.status_code == 200, rv.get_json()
    pid = rv.get_json()["payment_id"]

    rows = db.session.query(Payment).filter_by(tab_id=tab_id).all()
    assert len(rows) == 1 and rows[0].id == pid

    pending = db.session.query(PendingSTKPush).filter_by(
        checkout_request_id="ws_CO_ROUTE").first()
    assert pending.payment_id == pid

    # A retried tap reaches the same row, not a second one
    rv2 = client.post("/finance/mpesa/charge",
                      json={"tab_id": tab_id, "amount": 1500, "phone_number": "0712345678",
                            "idempotency_key": "till-ok-1"},
                      headers=hdr)
    assert rv2.status_code == 200
    assert db.session.query(Payment).filter_by(tab_id=tab_id).count() == 1


def test_charge_refuses_a_tab_that_does_not_exist(client, waiter_token, monkeypatch):
    """A stale screen pointing at a deleted tab must not open a payment."""
    for k, v in {
        "MPESA_CONSUMER_KEY": "k", "MPESA_CONSUMER_SECRET": "s",
        "MPESA_SHORTCODE": "174379", "MPESA_PASSKEY": "p",
        "MPESA_CALLBACK_URL": "https://example.com/cb", "MPESA_ENV": "sandbox",
    }.items():
        monkeypatch.setenv(k, v)
    rv = client.post("/finance/mpesa/charge",
                     json={"tab_id": "no-such-tab", "amount": 100, "phone_number": "0712345678"},
                     headers={"Authorization": f"Bearer {waiter_token}"})
    assert rv.status_code == 404
