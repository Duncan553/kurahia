"""
finance/mpesa_daraja.py — Safaricom Daraja API socket.

Dormant until env vars are set. When activated, handles:
- STK Push (cashier-initiated charges)
- C2B callback (auto-receive when customer pays till directly)

Manual reconciliation flow in finance/mpesa.py is unaffected.
"""
import base64
import os
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import httpx
from typing import Tuple, Optional
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user, require_clocked_in
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.audit_log import AuditLog
from app.models.pending_stk_push import PendingSTKPush
from app.models.tab import Tab

mpesa_daraja_bp = Blueprint("mpesa_daraja", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5

# ── Env var contract ────────────────────────────────────────────
REQUIRED_ENV_VARS = (
    "MPESA_CONSUMER_KEY",
    "MPESA_CONSUMER_SECRET",
    "MPESA_SHORTCODE",
    "MPESA_PASSKEY",
    "MPESA_CALLBACK_URL",
)

_token_cache = {"token": None, "expires_at": 0}

def _get_oauth_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Get a Daraja access token, cached for ~55 minutes.
    Returns (token, None) on success or (None, error_message) on failure.
    """
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"], None

    env = os.environ.get("MPESA_ENV", "sandbox")
    base_url = (
        "https://sandbox.safaricom.co.ke" if env == "sandbox"
        else "https://api.safaricom.co.ke"
    )

    consumer_key = os.environ.get("MPESA_CONSUMER_KEY")
    consumer_secret = os.environ.get("MPESA_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        return None, "M-Pesa Daraja credentials not configured."

    creds = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode()
    ).decode()

    try:
        resp = httpx.get(
            f"{base_url}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {creds}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        # Refresh 5 min before actual expiry to avoid mid-call expiration
        _token_cache["expires_at"] = now + 3300
        return data["access_token"], None
    except httpx.HTTPStatusError as e:
        return None, f"Daraja OAuth HTTP error: {e.response.status_code}"
    except httpx.TimeoutException:
        return None, "Daraja OAuth timed out after 10 seconds."
    except Exception as e:
        return None, f"Daraja OAuth failed: {type(e).__name__}: {e}"

def _clear_token_cache():
    """Test helper — reset cache between tests."""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0

# ── Pending STK Push persistence ────────────────────────────────
# checkout_request_id → tab_id mapping persisted in PendingSTKPush table.
# Survives server restarts. Rows expire after 1 hour; cleaned by CLI command.

def _register_pending_stk(checkout_request_id: str, tab_id, payment_id=None) -> None:
    """
    Persist a PendingSTKPush row so the callback can link to the originating tab
    even after a server restart.
    """
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    row = PendingSTKPush(
        checkout_request_id=checkout_request_id,
        tab_id=str(tab_id) if tab_id else None,
        payment_id=str(payment_id) if payment_id else None,
        expires_at_utc=expires,
    )
    try:
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass   # no app context (e.g. direct function call in tests) — non-fatal

def _clear_pending_stk() -> None:
    """Test helper — delete all PendingSTKPush rows."""
    db.session.query(PendingSTKPush).delete()
    db.session.commit()

def is_configured() -> bool:
    """Return True if all required env vars are set."""
    return all(os.environ.get(k) for k in REQUIRED_ENV_VARS)

def configuration_status() -> Tuple[bool, str]:
    """Return (ready, message). For diagnostic endpoints."""
    if is_configured():
        return True, "Daraja socket configured and active."
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    return False, f"Daraja socket dormant — missing env vars: {', '.join(missing)}"

# ── Phone helpers ────────────────────────────────────────────────

_PHONE_RE = re.compile(r'^(?:0|\+?254)(7\d{8}|1\d{8})$')

def _normalize_phone(phone: str) -> Optional[str]:
    """Return 254... format or None if invalid."""
    if not phone:
        return None
    cleaned = phone.strip().replace(" ", "")
    match = _PHONE_RE.match(cleaned)
    if not match:
        return None
    return "254" + match.group(1)

def _build_stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    """Daraja password format: base64(shortcode + passkey + timestamp)."""
    return base64.b64encode(
        f"{shortcode}{passkey}{timestamp}".encode()
    ).decode()

# ── Public API ───────────────────────────────────────────────────

def initiate_stk_push(amount, phone_number, tab_id, payment_id):
    """
    Cashier-initiated STK Push to customer's M-Pesa account.

    Returns:
        (True, {"checkout_request_id": ..., "merchant_request_id": ..., "customer_message": ...})
        on success.
        (False, "plain English error message") on failure.
    """
    if not is_configured():
        return False, "M-Pesa Daraja integration not configured."

    # Validate amount
    if not isinstance(amount, int) or amount <= 0:
        return False, "Amount must be a positive integer."

    # Validate phone
    normalized_phone = _normalize_phone(phone_number)
    if not normalized_phone:
        return False, "Invalid Kenyan phone number."

    # Get OAuth token
    token, err = _get_oauth_token()
    if err:
        return False, err

    # Build the STK Push payload
    env = os.environ.get("MPESA_ENV", "sandbox")
    base_url = (
        "https://sandbox.safaricom.co.ke" if env == "sandbox"
        else "https://api.safaricom.co.ke"
    )
    shortcode = os.environ["MPESA_SHORTCODE"]
    passkey = os.environ["MPESA_PASSKEY"]
    callback_url = os.environ["MPESA_CALLBACK_URL"]

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    password = _build_stk_password(shortcode, passkey, timestamp)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": normalized_phone,
        "PartyB": shortcode,
        "PhoneNumber": normalized_phone,
        "CallBackURL": callback_url,
        "AccountReference": str(tab_id)[:12],
        "TransactionDesc": f"Payment {str(payment_id)[:8]}",
    }

    try:
        resp = httpx.post(
            f"{base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("ResponseCode") == "0":
            checkout_id = data.get("CheckoutRequestID")
            _register_pending_stk(checkout_id, tab_id, payment_id)
            return True, {
                "checkout_request_id": checkout_id,
                "merchant_request_id": data.get("MerchantRequestID"),
                "customer_message": data.get("CustomerMessage"),
            }
        else:
            return False, f"STK Push rejected by Daraja: {data.get('ResponseDescription', 'unknown')}"
    except httpx.HTTPStatusError as e:
        return False, f"Daraja STK Push HTTP error: {e.response.status_code}"
    except httpx.TimeoutException:
        return False, "Daraja STK Push timed out after 15 seconds."
    except Exception as e:
        return False, f"Daraja STK Push failed: {type(e).__name__}: {e}"

def handle_c2b_callback(payload: dict) -> Tuple[bool, any]:
    """
    Process C2B callback from Safaricom (customer paid till directly).

    Returns (True, payment_id) on success or idempotent duplicate.
    Returns (False, error_message) on bad payload or write failure.
    """
    trans_id     = payload.get("TransID")
    trans_amount = payload.get("TransAmount")
    msisdn       = payload.get("MSISDN")

    if not trans_id or not trans_amount or not msisdn:
        return False, "Invalid C2B callback payload: missing TransID, TransAmount, or MSISDN."

    try:
        amount = Decimal(str(trans_amount))
    except Exception:
        return False, f"Invalid transaction amount in C2B callback: {trans_amount}"

    # Idempotency — Safaricom retries; second call returns existing payment silently
    existing = db.session.query(Payment).filter_by(idempotency_key=trans_id).first()
    if existing:
        return True, existing.id

    try:
        payment = Payment(
            method=PaymentMethod.MPESA.value,
            amount=amount,
            mpesa_code=trans_id,
            received_by_id=None,   # automated — no human actor
            idempotency_key=trans_id,
        )
        db.session.add(payment)
        db.session.flush()   # populate payment.id before building recon

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.MPESA.value,
            matched=True,
            statement_ref=trans_id,
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="daraja",
            action="payment.mpesa_c2b",
            target=trans_id,
            details=f"amount={amount} msisdn={msisdn}",
        )

        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"C2B callback write failed: {type(e).__name__}: {e}"


def handle_stk_callback(payload: dict) -> Tuple[bool, any]:
    """
    Process STK Push completion callback from Safaricom.

    Success path: creates Payment + PaymentReconciliation, links to originating tab.
    Failure path (cancelled/insufficient funds): writes audit log only, no Payment row.

    Returns (True, payment_id) on success.
    Returns (False, error_message) on failure or bad payload.
    """
    try:
        callback            = payload["Body"]["stkCallback"]
        result_code         = callback["ResultCode"]
        checkout_request_id = callback["CheckoutRequestID"]
    except (KeyError, TypeError):
        return False, "Invalid STK callback payload: missing Body.stkCallback fields."

    # Failure path — customer cancelled, insufficient funds, timeout, etc.
    if result_code != 0:
        result_desc = callback.get("ResultDesc", "STK Push failed.")
        try:
            AuditLog.log(
                actor="daraja",
                action="payment.stk_failed",
                target=checkout_request_id,
                details=f"result_code={result_code} desc={result_desc}",
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, f"STK Push failed: {result_desc}"

    # Success path — extract CallbackMetadata items into a name→value dict
    try:
        items   = {i["Name"]: i.get("Value") for i in callback["CallbackMetadata"]["Item"]}
        receipt = str(items.get("MpesaReceiptNumber", ""))
        amount  = Decimal(str(items.get("Amount", 0)))
    except (KeyError, TypeError) as e:
        return False, f"Could not parse STK callback metadata: {e}"

    if not receipt:
        return False, "STK callback missing MpesaReceiptNumber."

    # Idempotency — duplicate callback on the same receipt. Checked two ways
    # because the row this callback lands on may be one the till created
    # (idempotency_key = the till's uuid) rather than one born here
    # (idempotency_key = the receipt). Only mpesa_code is the same in both.
    existing = db.session.query(Payment).filter(
        db.or_(Payment.idempotency_key == receipt, Payment.mpesa_code == receipt)
    ).first()
    if existing:
        return True, existing.id

    # Look up the originating tab from the persistent pending table
    pending_row = db.session.query(PendingSTKPush).filter_by(
        checkout_request_id=checkout_request_id
    ).first()
    tab_id = pending_row.tab_id if pending_row else None

    # The till creates the Payment row BEFORE asking for the prompt, because
    # /mpesa/charge needs something to reference. If we then created a second
    # row here, the guest's one payment would clear the tab twice — a bill of
    # 750 settled by 1500 that never existed. Claim the row we already made.
    prior = (db.session.get(Payment, pending_row.payment_id)
             if pending_row and pending_row.payment_id else None)
    if prior is not None and prior.mpesa_code is None:
        try:
            # Safaricom is the authority on how much actually moved. Our row
            # held an expectation; this is the fact, so it wins — and if the
            # two differ the audit line says so rather than hiding it.
            if Decimal(str(prior.amount)) != amount:
                AuditLog.log(
                    actor="daraja", action="payment.stk_amount_corrected",
                    target=receipt,
                    details=f"expected={prior.amount} confirmed={amount} payment={prior.id}",
                )
                prior.amount = amount
            prior.mpesa_code = receipt

            db.session.add(PaymentReconciliation(
                payment_id=prior.id,
                method=PaymentMethod.MPESA.value,
                matched=True,
                statement_ref=receipt,
                status=PaymentReconciliationStatus.MATCHED.value,
            ))
            AuditLog.log(
                actor="daraja", action="payment.stk_confirmed", target=receipt,
                details=f"amount={amount} checkout_id={checkout_request_id} "
                        f"tab_id={prior.tab_id} claimed_payment={prior.id}",
            )
            db.session.delete(pending_row)
            db.session.commit()
            return True, prior.id
        except Exception as e:
            db.session.rollback()
            return False, f"STK callback claim failed: {type(e).__name__}: {e}"

    try:
        payment = Payment(
            tab_id=tab_id,
            method=PaymentMethod.MPESA.value,
            amount=amount,
            mpesa_code=receipt,
            received_by_id=None,   # automated — no human actor
            idempotency_key=receipt,
        )
        db.session.add(payment)
        db.session.flush()

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.MPESA.value,
            matched=True,
            statement_ref=receipt,
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="daraja",
            action="payment.stk_confirmed",
            target=receipt,
            details=f"amount={amount} checkout_id={checkout_request_id} tab_id={tab_id}",
        )

        if pending_row:
            db.session.delete(pending_row)
        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"STK callback write failed: {type(e).__name__}: {e}"


# ── Flask routes ─────────────────────────────────────────────────

@mpesa_daraja_bp.post("/mpesa/charge")
@require_active_user
@require_clocked_in
def mpesa_charge():
    """Send the M-Pesa prompt to the guest's phone.

    Gated at MANAGER_LEVEL, which put it out of reach of the only person who
    is ever standing at the table. A waiter is level 1; a manager is not
    holding the bill when the guest says "I'll pay by M-Pesa".

    It now matches POST /tabs/<id>/payments — active and clocked in — because
    prompting is the SAFER of the two acts. Recording a payment by hand lets a
    staff member assert that money arrived when none did; a prompt cannot move
    anything without the guest entering their own PIN, and Safaricom confirms
    it back to us. Holding the safer path to a higher bar pushed everyone onto
    the weaker one.
    """
    actor = db.session.get(User, get_jwt_identity())

    if not is_configured():
        return jsonify({
            "error": "M-Pesa Daraja integration not configured.",
            "fallback": "Use manual M-Pesa entry.",
        }), 503

    data = request.get_json(silent=True) or {}
    for field in ("amount", "phone_number", "tab_id"):
        if data.get(field) is None:
            return jsonify({"error": f"Missing required field: {field}."}), 400

    tab = db.session.get(Tab, str(data["tab_id"]))
    if tab is None:
        return jsonify({"error": "That tab no longer exists."}), 404

    # The payment row this prompt is for.
    #
    # It used to be the till's job to create it first and pass the id in. That
    # put the two halves in different transactions: if the prompt then failed
    # to send — dormant socket, Daraja down, a phone number Safaricom rejects —
    # the payment row survived on its own, and the bill read SETTLED against
    # money that was never asked for, let alone paid. The till had no way to
    # take it back; Payments are append-only.
    #
    # So the row is born HERE, and only survives if the prompt actually went
    # out. A caller may still pass its own payment_id (the gate does: its entry
    # fee is written by issue_band before this is ever called), and that path
    # is unchanged.
    payment_id  = data.get("payment_id")
    created_here = False
    if payment_id is None:
        idem = str(data.get("idempotency_key") or uuid.uuid4())
        # A retried tap must reach the same row, not a second one.
        prior = db.session.query(Payment).filter_by(idempotency_key=idem).first()
        if prior is not None:
            payment_id = prior.id
        else:
            try:
                amount_dec = Decimal(str(data["amount"]))
            except Exception:
                return jsonify({"error": "Amount is not a number."}), 400
            if amount_dec <= 0:
                return jsonify({"error": "Amount must be more than zero."}), 400
            payment = Payment(
                tab_id=tab.id,
                amount=amount_dec,
                method=PaymentMethod.MPESA.value,
                received_by_id=actor.id,
                idempotency_key=idem,
            )
            db.session.add(payment)
            db.session.flush()        # id, but NOT committed yet
            payment_id  = payment.id
            created_here = True

    ok, result = initiate_stk_push(
        amount=data["amount"],
        phone_number=data["phone_number"],
        tab_id=tab.id,
        payment_id=payment_id,
    )
    if not ok:
        # Nothing was sent, so nothing is owed. The row goes back with it.
        if created_here:
            db.session.rollback()
        return jsonify({"error": result}), 400

    AuditLog.log(actor=actor.username, action="payment.stk_requested",
                 target=str(payment_id),
                 details=f"tab={tab.id} amount={data['amount']} "
                         f"checkout={result['checkout_request_id']}")
    db.session.commit()
    return jsonify({
        "status": "pending",
        "payment_id": payment_id,
        "checkout_request_id": result["checkout_request_id"],
        "customer_message": result["customer_message"],
    }), 200


@mpesa_daraja_bp.post("/mpesa/callback")
def mpesa_callback():
    """
    Public — Safaricom calls this from the internet (no JWT).
    Always return 200 so Safaricom doesn't retry endlessly on our bugs.
    """
    from app.utils.webhook_validation import validate_webhook_payload
    ok, reason = validate_webhook_payload(request)
    if not ok:
        current_app.logger.warning(
            "mpesa/callback rejected — ip=%s reason=%s", request.remote_addr, reason
        )
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

    try:
        payload = request.get_json(silent=True) or {}
        if "Body" in payload and "stkCallback" in payload.get("Body", {}):
            handle_stk_callback(payload)
        else:
            handle_c2b_callback(payload)
    except Exception:
        current_app.logger.exception("Daraja callback processing failed")
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


@mpesa_daraja_bp.get("/mpesa/status")
@require_active_user
def mpesa_status():
    """Is the Daraja socket live?

    Manager-only made this a diagnostic. It is also the answer to a question
    the WAITER has to ask before showing a guest anything: can I send the
    prompt, or do I ask them to pay the paybill and read the code back?

    Without it the till offered "Send prompt" unconditionally — and with the
    socket dormant that recorded a payment and then failed to send anything,
    so the bill read SETTLED with no money behind it. Whether a payment route
    is switched on is not privileged information; it is a property of the till
    the person is standing at.
    """
    actor = db.session.get(User, get_jwt_identity())
    configured, message = configuration_status()
    return jsonify({"configured": configured, "message": message}), 200


# ── Cleanup helper (called by CLI) ───────────────────────────────

def cleanup_expired_pending_stk() -> int:
    """
    Delete PendingSTKPush rows past their expires_at_utc.
    Returns the number of rows deleted.
    Called by `flask mpesa cleanup-expired-stk`.
    """
    cutoff = datetime.now(timezone.utc)
    deleted = db.session.query(PendingSTKPush).filter(
        PendingSTKPush.expires_at_utc < cutoff
    ).delete()
    db.session.commit()
    return deleted
