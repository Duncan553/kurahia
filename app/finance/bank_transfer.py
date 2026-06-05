"""
finance/bank_transfer.py — Bank transfer dormant socket.

Two activation paths:

1. SMS forwarder (primary) — BANK_SMS_WEBHOOK_SECRET env var activates this.
   An Android SMS forwarding app (e.g. SMSSync) sends bank credit SMSs to
   POST /finance/bank/sms-forward. This module parses the SMS body,
   extracts amount + bank_ref, and writes Payment + PaymentReconciliation.

2. Bank API (stub) — BANK_PROVIDER + BANK_API_KEY activate this.
   Not yet implemented. verify_bank_transfer() returns a plain error until
   Step 2.4 fills in provider-specific code.

Routes are NOT registered here. Step 2.5 adds Flask routes.
"""
import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Tuple, Optional
from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.audit_log import AuditLog

# ── Env var contracts ────────────────────────────────────────────

REQUIRED_ENV_VARS_SMS = ("BANK_SMS_WEBHOOK_SECRET",)
REQUIRED_ENV_VARS_API = ("BANK_PROVIDER", "BANK_API_KEY")

SUPPORTED_PROVIDERS = ("equity", "kcb", "coop")


def is_sms_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED_ENV_VARS_SMS)


def get_provider_name() -> Optional[str]:
    """Return the configured BANK_PROVIDER if it's valid, else None."""
    provider = (os.environ.get("BANK_PROVIDER") or "").strip().lower()
    return provider if provider in SUPPORTED_PROVIDERS else None


def is_api_configured() -> bool:
    """True only when BANK_API_KEY is set AND BANK_PROVIDER is a supported provider."""
    return bool(os.environ.get("BANK_API_KEY")) and get_provider_name() is not None


def configuration_status() -> Tuple[bool, bool, str]:
    """
    Return (sms_ready, api_ready, message) for the diagnostic endpoint.

    API message distinguishes three states:
      - Configured:    BANK_PROVIDER is valid + BANK_API_KEY set   → names the provider
      - Dormant:       BANK_PROVIDER not set                        → says so plainly
      - Misconfigured: BANK_PROVIDER set but not in SUPPORTED_PROVIDERS → names the bad value
    """
    sms      = is_sms_configured()
    api      = is_api_configured()
    provider = get_provider_name()
    raw_prov = (os.environ.get("BANK_PROVIDER") or "").strip()

    # Build the API-side status message
    if api:
        api_msg = f"Bank API configured for provider: {provider}."
    elif raw_prov and provider is None:
        # BANK_PROVIDER is set but isn't in SUPPORTED_PROVIDERS — misconfigured, treated as dormant
        api_msg = f"Bank API misconfigured — provider '{raw_prov}' not supported. Supported: {', '.join(SUPPORTED_PROVIDERS)}."
    elif not raw_prov:
        api_msg = "Bank API dormant — BANK_PROVIDER not set."
    else:
        # BANK_PROVIDER valid but BANK_API_KEY missing
        api_msg = f"Bank API dormant — BANK_API_KEY not set (provider '{raw_prov}' recognised)."

    if sms and api:
        msg = f"Bank socket fully active: SMS forwarder active. {api_msg}"
    elif sms:
        msg = f"Bank SMS forwarder active. {api_msg}"
    elif api:
        msg = f"Bank SMS forwarder not active (BANK_SMS_WEBHOOK_SECRET missing). {api_msg}"
    else:
        missing_sms = [k for k in REQUIRED_ENV_VARS_SMS if not os.environ.get(k)]
        msg = f"Bank socket dormant. SMS path missing: {', '.join(missing_sms)}. {api_msg}"

    return sms, api, msg


# ── Per-bank SMS regex patterns ───────────────────────────────────
#
# Named capture groups: amount (digits + optional decimal), ref (alphanumeric ref).
# Each pattern is tested in order; first match wins.
#
# To add a new bank: append a (bank_name, compiled_regex) tuple.
# Test with real SMSs — amounts may use comma separators in some formats.

def _clean_amount(raw: str) -> Optional[Decimal]:
    """Strip commas and parse; return None if unparseable."""
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None

_BANK_SMS_PATTERNS = [
    # Equity Bank: "Equity Bank: KES 2,400.00 received from JOHN DOE. Ref: ABC123DEF on 04/06/2026"
    (
        "Equity",
        re.compile(
            r"Equity Bank.*?KES\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r".*?Ref:\s*(?P<ref>[A-Z0-9]{6,20})",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    # KCB: "KCB Bank: Ksh2,500.00 received from 254712345678 on 04/06/2026. Ref EGH987654."
    (
        "KCB",
        re.compile(
            r"KCB\b.*?Ksh\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r".*?Ref\s*(?P<ref>[A-Z0-9]{6,20})",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    # Co-op Bank: "Co-op Bank Acc:1234567890 Cr KES3,000.00 Ref:TXN20260604001 04Jun2026 12:00"
    (
        "Co-op",
        re.compile(
            r"Co-?op\b.*?Cr\s*KES\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r".*?Ref:?\s*(?P<ref>[A-Z0-9]{6,25})",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]


def _parse_sms_body(body: str) -> Tuple[Optional[str], Optional[Decimal], Optional[str]]:
    """
    Try each bank pattern against the SMS body.
    Returns (bank_name, amount, ref) on match, or (None, None, None) on no match.
    """
    for bank_name, pattern in _BANK_SMS_PATTERNS:
        m = pattern.search(body)
        if m:
            amount = _clean_amount(m.group("amount"))
            ref    = m.group("ref").strip()
            if amount and ref:
                return bank_name, amount, ref
    return None, None, None


# ── SMS forwarder handler ────────────────────────────────────────

def handle_sms_forward(payload: dict, webhook_secret: str) -> Tuple[bool, any]:
    """
    Process an SMS forwarded from the till phone.

    Payload shape (SMSSync / Android SMS Gateway compatible):
        {
            "secret":  "<BANK_SMS_WEBHOOK_SECRET>",
            "from":    "+254711111111",
            "body":    "Equity Bank: KES 2,400.00 received ... Ref: ABC123DEF ...",
        }

    Shared-secret auth: caller must send BANK_SMS_WEBHOOK_SECRET in payload.secret.
    Rejected with (False, "Unauthorized") if missing or wrong.

    Returns (True, payment_id) on success or idempotent duplicate.
    Returns (False, error_message) on failure.
    """
    if not is_sms_configured():
        return False, "Bank SMS forwarder not configured."

    # Shared-secret check — forwarder app sends the secret in the payload body
    expected_secret = os.environ.get("BANK_SMS_WEBHOOK_SECRET", "")
    if payload.get("secret") != expected_secret:
        return False, "Unauthorized: invalid webhook secret."

    body = (payload.get("body") or "").strip()
    if not body:
        return False, "SMS body is empty."

    bank_name, amount, bank_ref = _parse_sms_body(body)

    if bank_name is None:
        # Log for pattern-tuning — sender + first 80 chars of body
        AuditLog.log(
            actor="bank_sms",
            action="payment.bank_sms_unrecognized",
            target=payload.get("from", "unknown"),
            details=f"body_preview={body[:80]!r}",
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, "SMS format not recognized. Logged for pattern review."

    # Idempotency — Safaricom-style retry-safe; prefix avoids collision with mpesa keys
    idem_key = f"banksms-{bank_ref}"
    existing = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing:
        return True, existing.id

    try:
        payment = Payment(
            method=PaymentMethod.BANK_TRANSFER.value,
            amount=amount,
            bank_ref=bank_ref,
            received_by_id=None,       # automated — no human actor
            idempotency_key=idem_key,
            description=f"Auto-received via {bank_name} SMS forwarder",
        )
        db.session.add(payment)
        db.session.flush()

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.BANK_TRANSFER.value,
            matched=True,
            statement_ref=bank_ref,
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="bank_sms",
            action="payment.bank_sms_received",
            target=bank_ref,
            details=f"bank={bank_name} amount={amount} from={payload.get('from', 'unknown')}",
        )

        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"Bank SMS write failed: {type(e).__name__}: {e}"


# ── Bank API dispatch layer ──────────────────────────────────────

def verify_bank_transfer(amount, bank_ref: str, account_number: str = "") -> Tuple[bool, any]:
    """
    Verify a bank transfer via the configured bank API.
    Dispatches to the appropriate provider implementation.

    Input validation runs before provider dispatch — applies equally to all providers.

    Returns:
        (True,  {"provider": ..., "verified_at": ..., "details": ...}) on confirmed transfer
        (False, "plain English error message") on failure or dormancy
    """
    if not is_api_configured():
        return False, "Bank API integration not configured."

    # Input validation — before touching any provider
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        return False, "Amount must be a positive number."
    if amount <= 0:
        return False, "Amount must be a positive number."
    if not bank_ref or not str(bank_ref).strip():
        return False, "bank_ref is required."

    provider = get_provider_name()
    if provider == "equity":
        return _verify_equity(amount, bank_ref, account_number)
    elif provider == "kcb":
        return _verify_kcb(amount, bank_ref, account_number)
    elif provider == "coop":
        return _verify_coop(amount, bank_ref, account_number)
    else:
        # Defensive — should not reach here since is_api_configured() validates provider
        return False, f"Unknown bank provider: {provider}."


# ── Provider stubs (Step 2.3 implements these) ────────────────────

def _verify_equity(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    raise NotImplementedError("Step 2.3 will implement Equity Jenga API integration.")


def _verify_kcb(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    raise NotImplementedError("Step 2.3 will implement KCB Open Banking integration.")


def _verify_coop(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    raise NotImplementedError("Step 2.3 will implement Co-op Mobicash integration.")
