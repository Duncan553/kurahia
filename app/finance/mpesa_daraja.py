"""
finance/mpesa_daraja.py — Safaricom Daraja API socket.

Dormant until env vars are set. When activated, handles:
- STK Push (cashier-initiated charges)
- C2B callback (auto-receive when customer pays till directly)

Manual reconciliation flow in finance/mpesa.py is unaffected.
"""
import base64
import os
import time
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

# ── Public API (placeholders that fail gracefully when dormant) ──

def initiate_stk_push(amount, phone_number, tab_id, payment_id):
    """Cashier-initiated STK Push. Returns (success, message_or_data)."""
    if not is_configured():
        return False, "M-Pesa Daraja integration not configured."
    raise NotImplementedError("Step 1.3 will implement this.")

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
