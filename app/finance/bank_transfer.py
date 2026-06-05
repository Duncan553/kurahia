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


def is_sms_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED_ENV_VARS_SMS)


def is_api_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED_ENV_VARS_API)


def configuration_status() -> Tuple[bool, bool, str]:
    """Return (sms_ready, api_ready, message) for the diagnostic endpoint."""
    sms = is_sms_configured()
    api = is_api_configured()
    if sms and api:
        msg = "Bank socket fully active: SMS forwarder + API verification both configured."
    elif sms:
        msg = "Bank SMS forwarder active. Bank API not configured (manual reconciliation fallback)."
    elif api:
        msg = "Bank API configured. SMS forwarder not active (BANK_SMS_WEBHOOK_SECRET missing)."
    else:
        missing_sms = [k for k in REQUIRED_ENV_VARS_SMS if not os.environ.get(k)]
        missing_api = [k for k in REQUIRED_ENV_VARS_API if not os.environ.get(k)]
        msg = (
            f"Bank socket dormant. "
            f"SMS path missing: {', '.join(missing_sms)}. "
            f"API path missing: {', '.join(missing_api)}."
        )
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


# ── Bank API stub ────────────────────────────────────────────────

def verify_bank_transfer(amount: Decimal, bank_ref: str, account_number: str = "") -> Tuple[bool, str]:
    """
    Verify a bank transfer via provider API.
    Stubbed until Step 2.4 implements provider-specific handlers.

    Returns (True, confirmed_ref) on success or (False, error_message) on failure.
    """
    if not is_api_configured():
        return False, "Bank API integration not configured."
    raise NotImplementedError("Step 2.4 will implement provider-specific verification.")
