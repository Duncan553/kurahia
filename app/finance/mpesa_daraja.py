"""
finance/mpesa_daraja.py — Safaricom Daraja API socket.

Dormant until env vars are set. When activated, handles:
- STK Push (cashier-initiated charges)
- C2B callback (auto-receive when customer pays till directly)

Manual reconciliation flow in finance/mpesa.py is unaffected.
"""
import os
from typing import Tuple, Optional

# ── Env var contract ────────────────────────────────────────────
REQUIRED_ENV_VARS = (
    "MPESA_CONSUMER_KEY",
    "MPESA_CONSUMER_SECRET",
    "MPESA_SHORTCODE",
    "MPESA_PASSKEY",
    "MPESA_CALLBACK_URL",
)

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
