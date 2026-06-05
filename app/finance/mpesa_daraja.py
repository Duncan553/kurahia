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
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import httpx
from typing import Tuple, Optional
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.audit_log import AuditLog
from app.models.pending_stk_push import PendingSTKPush

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
            _register_pending_stk(checkout_id, tab_id)
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

    # Idempotency — duplicate callback on same receipt number
    existing = db.session.query(Payment).filter_by(idempotency_key=receipt).first()
    if existing:
        return True, existing.id

    # Look up the originating tab from the persistent pending table
    pending_row = db.session.query(PendingSTKPush).filter_by(
        checkout_request_id=checkout_request_id
    ).first()
    tab_id = pending_row.tab_id if pending_row else None

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
def mpesa_charge():
    """Cashier-initiated STK Push to customer's phone."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    if not is_configured():
        return jsonify({
            "error": "M-Pesa Daraja integration not configured.",
            "fallback": "Use manual M-Pesa entry.",
        }), 503

    data = request.get_json(silent=True) or {}
    for field in ("amount", "phone_number", "tab_id", "payment_id"):
        if data.get(field) is None:
            return jsonify({"error": f"Missing required field: {field}."}), 400

    ok, result = initiate_stk_push(
        amount=data["amount"],
        phone_number=data["phone_number"],
        tab_id=data["tab_id"],
        payment_id=data["payment_id"],
    )
    if not ok:
        return jsonify({"error": result}), 400
    return jsonify({
        "status": "pending",
        "checkout_request_id": result["checkout_request_id"],
        "customer_message": result["customer_message"],
    }), 200


@mpesa_daraja_bp.post("/mpesa/callback")
def mpesa_callback():
    """
    Public — Safaricom calls this from the internet (no JWT).
    Always return 200 so Safaricom doesn't retry endlessly on our bugs.
    """
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
    """Diagnostic — is the Daraja socket live?"""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
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
