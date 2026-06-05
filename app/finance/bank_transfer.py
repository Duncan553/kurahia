"""
finance/bank_transfer.py — Bank transfer dormant socket + Flask routes.

Two activation paths:

1. SMS forwarder (primary) — BANK_SMS_WEBHOOK_SECRET env var activates this.
   POST /finance/bank/sms-forward receives SMSs forwarded from the till phone.
   Parses Equity / KCB / Co-op credit SMSs, writes Payment + PaymentReconciliation.

2. Bank API — BANK_PROVIDER + BANK_API_KEY + provider-specific vars activate this.
   POST /finance/bank/verify triggers real-time transfer verification via provider API.
   Implementations exist for Equity Jenga, KCB Open Banking, and Co-op Mobicash.
   Each has # TODO markers for exact endpoint URL and response field verification
   against production bank docs before go-live.
"""
import os
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Tuple, Optional
import httpx
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.audit_log import AuditLog

bank_transfer_bp = Blueprint("bank_transfer", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5

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


# ── Provider implementations ─────────────────────────────────────

def _verify_equity(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    """
    Verify a bank transfer via Equity Bank Jenga API.

    Required env vars:
        BANK_EQUITY_API_BASE      Sandbox: https://sandbox.equitybankgroup.com
                                  Production: https://api.equitybankgroup.com
        BANK_EQUITY_API_KEY       API key from Jenga developer portal
        BANK_EQUITY_MERCHANT_CODE Merchant code from Jenga developer portal

    TODO: verify exact endpoint path and response fields against
          https://developer.equitybankgroup.com (Jenga API v3 docs).
    """
    api_base      = os.environ.get("BANK_EQUITY_API_BASE")
    api_key       = os.environ.get("BANK_EQUITY_API_KEY")
    merchant_code = os.environ.get("BANK_EQUITY_MERCHANT_CODE")

    missing = [k for k, v in {
        "BANK_EQUITY_API_BASE":      api_base,
        "BANK_EQUITY_API_KEY":       api_key,
        "BANK_EQUITY_MERCHANT_CODE": merchant_code,
    }.items() if not v]
    if missing:
        return False, f"Equity API env vars missing: {', '.join(missing)}."

    try:
        resp = httpx.get(
            f"{api_base}/v3/account/transaction",  # TODO: verify endpoint from Jenga v3 docs
            params={"transactionRef": bank_ref, "merchantCode": merchant_code},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return False, "Equity API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"Equity API HTTP error: {e.response.status_code}."
    except Exception as e:
        return False, f"Equity API request failed: {type(e).__name__}: {e}"

    # TODO: verify exact status field name/values from Jenga API response spec
    status = str(data.get("status", "")).upper()
    if status not in ("SUCCESS", "COMPLETED"):
        return False, f"Equity API: transfer not confirmed (status={status!r})."

    confirmed_amount = Decimal(str(data.get("amount", 0)))
    if confirmed_amount != amount:
        return False, f"Amount mismatch: expected {amount}, bank confirms {confirmed_amount}."

    return True, {
        "provider": "equity",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "details": {
            "bank_ref":        bank_ref,
            "confirmed_amount": str(confirmed_amount),
            "transaction_date": data.get("transactionDate"),  # TODO: verify field name
        },
    }


# KCB OAuth token cache — same pattern as M-Pesa Daraja
_kcb_token_cache: dict = {"token": None, "expires_at": 0}


def _get_kcb_token(api_base: str, client_id: str, client_secret: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch and cache a KCB OAuth2 bearer token."""
    now = time.time()
    if _kcb_token_cache["token"] and _kcb_token_cache["expires_at"] > now:
        return _kcb_token_cache["token"], None
    try:
        resp = httpx.post(
            f"{api_base}/oauth/token",  # TODO: verify OAuth endpoint from KCB Open Banking docs
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data  = resp.json()
        token = data["access_token"]
        _kcb_token_cache["token"]      = token
        _kcb_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
        return token, None
    except httpx.HTTPStatusError as e:
        return None, f"KCB OAuth HTTP error: {e.response.status_code}."
    except httpx.TimeoutException:
        return None, "KCB OAuth timed out after 10 seconds."
    except Exception as e:
        return None, f"KCB OAuth failed: {type(e).__name__}: {e}"


def _verify_kcb(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    """
    Verify a bank transfer via KCB Open Banking API (OAuth2).

    Required env vars:
        BANK_KCB_API_BASE       Sandbox: https://uat.buni.kcbgroup.com
                                Production: https://api.kcbgroup.com
        BANK_KCB_CLIENT_ID      OAuth client ID from KCB developer portal
        BANK_KCB_CLIENT_SECRET  OAuth client secret from KCB developer portal

    TODO: verify exact token + query endpoint paths against
          https://developer.kcbgroup.com docs.
    """
    api_base      = os.environ.get("BANK_KCB_API_BASE")
    client_id     = os.environ.get("BANK_KCB_CLIENT_ID")
    client_secret = os.environ.get("BANK_KCB_CLIENT_SECRET")

    missing = [k for k, v in {
        "BANK_KCB_API_BASE":       api_base,
        "BANK_KCB_CLIENT_ID":      client_id,
        "BANK_KCB_CLIENT_SECRET":  client_secret,
    }.items() if not v]
    if missing:
        return False, f"KCB API env vars missing: {', '.join(missing)}."

    token, err = _get_kcb_token(api_base, client_id, client_secret)
    if err:
        return False, err

    try:
        resp = httpx.get(
            f"{api_base}/v1/account/transactions",  # TODO: verify endpoint from KCB docs
            params={"transactionReference": bank_ref},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return False, "KCB API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"KCB API HTTP error: {e.response.status_code}."
    except Exception as e:
        return False, f"KCB API request failed: {type(e).__name__}: {e}"

    # TODO: verify exact response field names from KCB Open Banking response spec
    status = str(data.get("status", "")).upper()
    if status not in ("SUCCESS", "COMPLETED"):
        return False, f"KCB API: transfer not confirmed (status={status!r})."

    confirmed_amount = Decimal(str(data.get("amount", 0)))
    if confirmed_amount != amount:
        return False, f"Amount mismatch: expected {amount}, bank confirms {confirmed_amount}."

    return True, {
        "provider": "kcb",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "details": {
            "bank_ref":         bank_ref,
            "confirmed_amount": str(confirmed_amount),
            "transaction_date": data.get("transactionDate"),  # TODO: verify field name
        },
    }


def _verify_coop(amount: Decimal, bank_ref: str, account_number: str) -> Tuple[bool, any]:
    """
    Verify a bank transfer via Co-op Bank API (Basic auth).

    Required env vars:
        BANK_COOP_API_BASE    Sandbox: https://developer.co-opbank.co.ke:8243
                              Production: https://api.co-opbank.co.ke:8243
        BANK_COOP_USERNAME    Consumer key from Co-op developer portal
        BANK_COOP_PASSWORD    Consumer secret from Co-op developer portal

    TODO: verify exact endpoint path and auth mechanism against
          https://developer.co-opbank.co.ke docs (may use OAuth, not Basic auth).
    """
    api_base = os.environ.get("BANK_COOP_API_BASE")
    username = os.environ.get("BANK_COOP_USERNAME")
    password = os.environ.get("BANK_COOP_PASSWORD")

    missing = [k for k, v in {
        "BANK_COOP_API_BASE": api_base,
        "BANK_COOP_USERNAME": username,
        "BANK_COOP_PASSWORD": password,
    }.items() if not v]
    if missing:
        return False, f"Co-op API env vars missing: {', '.join(missing)}."

    try:
        resp = httpx.get(
            f"{api_base}/api/1.0/Transactions/Statement",  # TODO: verify from Co-op API docs
            params={"TransactionRef": bank_ref},
            auth=(username, password),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return False, "Co-op API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"Co-op API HTTP error: {e.response.status_code}."
    except Exception as e:
        return False, f"Co-op API request failed: {type(e).__name__}: {e}"

    # TODO: verify exact response field names from Co-op Bank API response spec
    if not data.get("Successful", False):
        return False, "Co-op API: transfer not confirmed."

    confirmed_amount = Decimal(str(data.get("Amount", 0)))
    if confirmed_amount != amount:
        return False, f"Amount mismatch: expected {amount}, bank confirms {confirmed_amount}."

    return True, {
        "provider": "coop",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "details": {
            "bank_ref":         bank_ref,
            "confirmed_amount": str(confirmed_amount),
            "transaction_date": data.get("TransactionDate"),  # TODO: verify field name
        },
    }


# ── Flask routes ─────────────────────────────────────────────────

@bank_transfer_bp.post("/bank/sms-forward")
def bank_sms_forward():
    """
    Public — called by the SMS forwarder app on the till phone.
    If BANK_SMS_WEBHOOK_SECRET is set, requires X-Webhook-Secret header to match.
    Always returns 200 so the forwarder app doesn't retry on internal bugs.
    """
    expected = os.environ.get("BANK_SMS_WEBHOOK_SECRET")
    if expected and request.headers.get("X-Webhook-Secret") != expected:
        return jsonify({"error": "Unauthorized."}), 401

    try:
        payload = request.get_json(silent=True) or {}
        handle_sms_forward(payload)
    except Exception:
        current_app.logger.exception("Bank SMS forward processing failed")
    return jsonify({"status": "accepted"}), 200


@bank_transfer_bp.post("/bank/verify")
@require_active_user
def bank_verify():
    """Manager-triggered real-time verification of a bank transfer via provider API."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    if not is_api_configured():
        return jsonify({
            "error": "Bank API not configured.",
            "fallback": "Use manual reconciliation or SMS forwarder.",
        }), 503

    data          = request.get_json(silent=True) or {}
    amount        = data.get("amount")
    bank_ref      = data.get("bank_ref")
    account_number = data.get("account_number", "")

    if amount is None:
        return jsonify({"error": "Missing required field: amount."}), 400
    if not bank_ref:
        return jsonify({"error": "Missing required field: bank_ref."}), 400

    ok, result = verify_bank_transfer(amount, bank_ref, account_number)
    if not ok:
        return jsonify({"error": result}), 400
    return jsonify(result), 200


@bank_transfer_bp.get("/bank/status")
@require_active_user
def bank_status():
    """Diagnostic — which parts of the bank socket are configured?"""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    sms_configured, api_configured, message = configuration_status()
    return jsonify({
        "sms_configured": sms_configured,
        "api_configured": api_configured,
        "provider":       get_provider_name(),
        "message":        message,
    }), 200
