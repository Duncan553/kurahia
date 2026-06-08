"""
app/services/notifications/whatsapp.py — WhatsApp dormant socket.

Activation: set all four env vars below. Socket is dormant until then.
The dispatcher imports send_whatsapp() and calls it; UNCONFIGURED is a
first-class outcome that triggers SMS/inbox fallback automatically.

Required env vars (all four must be set):
  WHATSAPP_PROVIDER   = twilio
  WHATSAPP_ACCOUNT_SID = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  WHATSAPP_AUTH_TOKEN  = <auth token from Twilio console>
  WHATSAPP_FROM_NUMBER = +14155238886  (Twilio sandbox or production sender)

Runbook: docs/WHATSAPP_ACTIVATION.md
"""
import os
import re
from typing import Optional

SUPPORTED_PROVIDERS = ("twilio",)

REQUIRED_ENV_VARS = (
    "WHATSAPP_PROVIDER",
    "WHATSAPP_ACCOUNT_SID",
    "WHATSAPP_AUTH_TOKEN",
    "WHATSAPP_FROM_NUMBER",
)


# ── Configuration helpers ────────────────────────────────────────────────────

def get_provider_name() -> Optional[str]:
    provider = (os.environ.get("WHATSAPP_PROVIDER") or "").strip().lower()
    return provider if provider in SUPPORTED_PROVIDERS else None


def is_configured() -> bool:
    return (
        all(os.environ.get(k) for k in REQUIRED_ENV_VARS)
        and get_provider_name() is not None
    )


def configuration_status() -> tuple[bool, str]:
    """Return (configured, plain-English message) for the status endpoint."""
    provider = get_provider_name()
    raw_prov  = (os.environ.get("WHATSAPP_PROVIDER") or "").strip()

    if is_configured():
        return True, f"WhatsApp socket configured for provider: {provider}."

    if raw_prov and provider is None:
        return False, (
            f"WhatsApp socket misconfigured — provider '{raw_prov}' not supported. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    return False, f"WhatsApp socket dormant — missing env vars: {', '.join(missing)}."


# ── Phone number normalisation ────────────────────────────────────────────────

_KENYAN_LOCAL    = re.compile(r"^0([17]\d{8})$")      # 0712345678, 0112345678
_KENYAN_INTL_254 = re.compile(r"^254([17]\d{8})$")    # 254712345678
_KENYAN_INTL_PLUS= re.compile(r"^\+254([17]\d{8})$")  # +254712345678


def normalise_phone(raw: str) -> Optional[str]:
    """
    Convert a Kenyan phone number to E.164 (+254XXXXXXXXX).
    Returns None if the number doesn't match any recognised format.
    Twilio requires E.164 for WhatsApp sends.
    """
    raw = (raw or "").strip().replace(" ", "").replace("-", "")

    for pattern in (_KENYAN_LOCAL, _KENYAN_INTL_254, _KENYAN_INTL_PLUS):
        m = pattern.match(raw)
        if m:
            return f"+254{m.group(1)}"

    return None  # unrecognised format


# ── Provider dispatch ─────────────────────────────────────────────────────────

def send_whatsapp(phone: str, body: str) -> tuple[str, str]:
    """
    Main entry point. Called by the dispatcher.

    Returns (status_code, message):
      "SENT"          — message delivered to Twilio successfully
      "UNCONFIGURED"  — socket not set up; dispatcher falls back to SMS/inbox
      "INVALID_PHONE" — phone number format not recognised
      "ERROR"         — Twilio returned an error (details in message)
    """
    if not is_configured():
        return ("UNCONFIGURED", "WhatsApp socket not configured.")

    e164 = normalise_phone(phone)
    if e164 is None:
        return ("INVALID_PHONE", f"Phone number '{phone}' is not a recognised Kenyan format.")

    provider = get_provider_name()
    if provider == "twilio":
        return _send_via_twilio(e164, body)

    # Should never reach here if SUPPORTED_PROVIDERS is in sync with is_configured()
    return ("UNCONFIGURED", f"Provider '{provider}' not implemented.")


def _send_via_twilio(to_e164: str, body: str) -> tuple[str, str]:
    """
    POST to the Twilio Messages API.
    Twilio WhatsApp numbers use the whatsapp: URI scheme.
    """
    try:
        import httpx
    except ImportError:
        return ("ERROR", "httpx not installed — run: pip install httpx")

    account_sid = os.environ["WHATSAPP_ACCOUNT_SID"]
    auth_token  = os.environ["WHATSAPP_AUTH_TOKEN"]
    from_number = os.environ["WHATSAPP_FROM_NUMBER"].strip()

    # Twilio WhatsApp requires the "whatsapp:" prefix
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    to_whatsapp = f"whatsapp:{to_e164}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    try:
        response = httpx.post(
            url,
            auth=(account_sid, auth_token),
            data={"From": from_number, "To": to_whatsapp, "Body": body},
            timeout=10.0,
        )
        if response.status_code in (200, 201):
            return ("SENT", f"Message queued: SID={response.json().get('sid', 'unknown')}")
        return ("ERROR", f"Twilio error {response.status_code}: {response.text[:200]}")
    except httpx.RequestError as exc:
        return ("ERROR", f"Network error contacting Twilio: {exc}")
