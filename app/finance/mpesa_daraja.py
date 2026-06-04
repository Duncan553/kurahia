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
from datetime import datetime
import httpx
from typing import Tuple, Optional

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
            return True, {
                "checkout_request_id": data.get("CheckoutRequestID"),
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

def handle_c2b_callback(payload):
    """Process incoming C2B notification from Safaricom."""
    if not is_configured():
        return False, "M-Pesa Daraja integration not configured."
    raise NotImplementedError("Step 1.4 will implement this.")

def handle_stk_callback(payload):
    """Process STK Push completion callback."""
    if not is_configured():
        return False, "M-Pesa Daraja integration not configured."
    raise NotImplementedError("Step 1.4 will implement this.")
