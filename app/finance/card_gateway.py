"""
finance/card_gateway.py — Card gateway dormant socket + Flask routes.

Activation: set CARD_PROVIDER (pesapal | dpo | cellulant) + shared env vars.
Three supported gateways, all provider-dispatched from a single public API.

Routes:
  POST /finance/card/initiate  — manager auth, triggers payment URL
  POST /finance/card/callback  — public IPN receiver (gateway calls us)
  GET  /finance/card/status    — manager auth, diagnostic
"""
import os
import time
import uuid
import xml.etree.ElementTree as ET
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

card_gateway_bp = Blueprint("card_gateway", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5

# ── Env var contracts ────────────────────────────────────────────

# Shared vars — all providers need these
REQUIRED_ENV_VARS = ("CARD_PROVIDER", "CARD_API_KEY", "CARD_MERCHANT_ID", "CARD_IPN_URL")

SUPPORTED_PROVIDERS = ("pesapal", "dpo", "cellulant")


# ── Configuration helpers ────────────────────────────────────────

def get_provider_name() -> Optional[str]:
    """Return the configured CARD_PROVIDER if valid, else None."""
    provider = (os.environ.get("CARD_PROVIDER") or "").strip().lower()
    return provider if provider in SUPPORTED_PROVIDERS else None


def is_configured() -> bool:
    """True only when all shared env vars are set AND provider is supported."""
    return (
        all(os.environ.get(k) for k in REQUIRED_ENV_VARS)
        and get_provider_name() is not None
    )


def configuration_status() -> Tuple[bool, str]:
    """Return (configured, message) for the diagnostic endpoint."""
    provider = get_provider_name()
    raw_prov = (os.environ.get("CARD_PROVIDER") or "").strip()

    if is_configured():
        return True, f"Card gateway configured for provider: {provider}."
    if raw_prov and provider is None:
        return False, (
            f"Card gateway misconfigured — provider '{raw_prov}' not supported. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}."
        )
    if not raw_prov:
        return False, "Card gateway dormant — CARD_PROVIDER not set."
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    return False, f"Card gateway dormant — missing env vars: {', '.join(missing)}."


# ── Provider initiation dispatch ─────────────────────────────────

def initiate_card_payment(
    amount,
    tab_id: str,
    payment_id: str,
    customer_email: str = None,
    customer_phone: str = None,
) -> Tuple[bool, any]:
    """
    Initiate a card payment via the configured gateway.
    Cashier calls this; customer is directed to the returned payment_url.

    Returns:
        (True,  {"payment_url": ..., "transaction_ref": ..., "provider": ...}) on success
        (False, "plain English error") on failure or dormancy
    """
    if not is_configured():
        return False, "Card gateway not configured."

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        return False, "Amount must be a positive number."
    if amount <= 0:
        return False, "Amount must be a positive number."

    if not customer_email and not customer_phone:
        return False, "At least one of customer_email or customer_phone is required."

    provider = get_provider_name()
    if provider == "pesapal":
        return _initiate_pesapal(amount, tab_id, payment_id, customer_email, customer_phone)
    elif provider == "dpo":
        return _initiate_dpo(amount, tab_id, payment_id, customer_email, customer_phone)
    elif provider == "cellulant":
        return _initiate_cellulant(amount, tab_id, payment_id, customer_email, customer_phone)
    else:
        return False, f"Unknown card provider: {provider}."


# ── Pesapal v3 ───────────────────────────────────────────────────

_pesapal_token_cache: dict = {"token": None, "expires_at": 0}


def _get_pesapal_token(api_base: str, consumer_key: str, consumer_secret: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch and cache a Pesapal v3 OAuth token (~5 min TTL, cached for 4 min)."""
    now = time.time()
    if _pesapal_token_cache["token"] and _pesapal_token_cache["expires_at"] > now:
        return _pesapal_token_cache["token"], None
    try:
        resp = httpx.post(
            f"{api_base}/api/Auth/RequestToken",
            json={"consumer_key": consumer_key, "consumer_secret": consumer_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["token"]
        _pesapal_token_cache["token"] = token
        _pesapal_token_cache["expires_at"] = now + 240  # 4 min — tokens expire in ~5
        return token, None
    except httpx.HTTPStatusError as e:
        return None, f"Pesapal auth HTTP error: {e.response.status_code}."
    except httpx.TimeoutException:
        return None, "Pesapal auth timed out after 10 seconds."
    except Exception as e:
        return None, f"Pesapal auth failed: {type(e).__name__}: {e}"


def _initiate_pesapal(amount: Decimal, tab_id: str, payment_id: str,
                      customer_email: str, customer_phone: str) -> Tuple[bool, any]:
    """
    Initiate a Pesapal v3 STK / card payment.

    Required env vars:
        CARD_API_KEY          Consumer key from Pesapal developer portal
        CARD_MERCHANT_ID      IPN ID registered on Pesapal (the notification_id)
        CARD_IPN_URL          Your public callback URL
        CARD_PESAPAL_API_BASE Sandbox: https://cybqa.pesapal.com/pesapalv3
                              Production: https://pay.pesapal.com/v3

    TODO: verify consumer_secret handling — Pesapal v3 uses key+secret for OAuth;
          currently reads CARD_API_KEY as consumer_key and needs a separate
          CARD_API_SECRET or CARD_PESAPAL_CONSUMER_SECRET env var.
    """
    api_base      = os.environ.get("CARD_PESAPAL_API_BASE")
    consumer_key  = os.environ.get("CARD_API_KEY")
    # TODO: add CARD_API_SECRET to REQUIRED_ENV_VARS before production go-live
    consumer_secret = os.environ.get("CARD_API_SECRET", consumer_key)
    merchant_id   = os.environ.get("CARD_MERCHANT_ID")
    ipn_url       = os.environ.get("CARD_IPN_URL")

    missing = [k for k, v in {
        "CARD_PESAPAL_API_BASE": api_base,
        "CARD_API_KEY":          consumer_key,
        "CARD_MERCHANT_ID":      merchant_id,
        "CARD_IPN_URL":          ipn_url,
    }.items() if not v]
    if missing:
        return False, f"Pesapal env vars missing: {', '.join(missing)}."

    token, err = _get_pesapal_token(api_base, consumer_key, consumer_secret)
    if err:
        return False, err

    order_ref = str(payment_id)[:25]
    payload = {
        "id":                str(uuid.uuid4()),
        "currency":          "KES",
        "amount":            float(amount),
        "description":       f"Tab payment {str(tab_id)[:20]}",
        "callback_url":      ipn_url,
        "notification_id":   merchant_id,   # IPN ID from Pesapal portal
        "merchant_reference": order_ref,
        "billing_address": {
            "email_address": customer_email or "",
            "phone_number":  customer_phone or "",
        },
    }
    try:
        resp = httpx.post(
            f"{api_base}/api/Transactions/SubmitOrderRequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return False, "Pesapal API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"Pesapal API HTTP error: {e.response.status_code}."
    except Exception as e:
        return False, f"Pesapal API request failed: {type(e).__name__}: {e}"

    err_info = data.get("error")
    if err_info and err_info.get("code"):
        return False, f"Pesapal rejected order: {err_info.get('message', 'unknown')}."

    redirect_url = data.get("redirect_url")
    tracking_id  = data.get("order_tracking_id")
    if not redirect_url:
        return False, "Pesapal did not return a redirect URL."

    return True, {
        "payment_url":     redirect_url,
        "transaction_ref": tracking_id or order_ref,
        "provider":        "pesapal",
    }


# ── DPO Group ────────────────────────────────────────────────────

def _initiate_dpo(amount: Decimal, tab_id: str, payment_id: str,
                  customer_email: str, customer_phone: str) -> Tuple[bool, any]:
    """
    Initiate a DPO Group card payment (XML-based API).

    Required env vars:
        CARD_DPO_COMPANY_TOKEN  Company token from DPO portal
        CARD_DPO_API_BASE       Sandbox: https://secure.3gdirectpay.com
                                Production: https://secure.3gdirectpay.com (same — test/live differ by CompanyToken)
        CARD_IPN_URL            Your public callback URL

    TODO: verify ServiceType code (3854 used here — confirm against your DPO account's
          service codes), and API version path (/API/v6/) from DPO docs.
    """
    company_token = os.environ.get("CARD_DPO_COMPANY_TOKEN")
    api_base      = os.environ.get("CARD_DPO_API_BASE", "https://secure.3gdirectpay.com")
    ipn_url       = os.environ.get("CARD_IPN_URL")

    missing = [k for k, v in {
        "CARD_DPO_COMPANY_TOKEN": company_token,
        "CARD_IPN_URL":           ipn_url,
    }.items() if not v]
    if missing:
        return False, f"DPO env vars missing: {', '.join(missing)}."

    now_str = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")
    xml_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<API3G>"
        f"<CompanyToken>{company_token}</CompanyToken>"
        "<Request>createToken</Request>"
        "<Transaction>"
        f"<PaymentAmount>{amount:.2f}</PaymentAmount>"
        "<PaymentCurrency>KES</PaymentCurrency>"
        f"<CompanyRef>{str(payment_id)[:30]}</CompanyRef>"
        f"<RedirectURL>{ipn_url}</RedirectURL>"
        f"<BackURL>{ipn_url}</BackURL>"
        "<CompanyRefUnique>1</CompanyRefUnique>"
        "<PTL>30</PTL>"
        "</Transaction>"
        "<Services>"
        "<Service>"
        "<ServiceType>3854</ServiceType>"  # TODO: verify service type code from DPO portal
        "<ServiceDescription>Tab Payment</ServiceDescription>"
        f"<ServiceDate>{now_str}</ServiceDate>"
        "</Service>"
        "</Services>"
        "</API3G>"
    )
    try:
        resp = httpx.post(
            f"{api_base}/API/v6/",  # TODO: verify DPO API version path from DPO docs
            content=xml_body.encode(),
            headers={"Content-Type": "application/xml"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except httpx.TimeoutException:
        return False, "DPO API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"DPO API HTTP error: {e.response.status_code}."
    except ET.ParseError as e:
        return False, f"DPO returned invalid XML: {e}."
    except Exception as e:
        return False, f"DPO API request failed: {type(e).__name__}: {e}"

    result_code = root.findtext("Result")
    if result_code != "000":
        explanation = root.findtext("ResultExplanation", "unknown error")
        return False, f"DPO rejected transaction: {explanation}."

    trans_token = root.findtext("TransToken")
    if not trans_token:
        return False, "DPO did not return a transaction token."

    return True, {
        "payment_url":     f"{api_base}/payv2.php?ID={trans_token}",
        "transaction_ref": trans_token,
        "provider":        "dpo",
    }


# ── Cellulant Tingg ──────────────────────────────────────────────

def _initiate_cellulant(amount: Decimal, tab_id: str, payment_id: str,
                        customer_email: str, customer_phone: str) -> Tuple[bool, any]:
    """
    Initiate a Cellulant Tingg checkout payment.

    Required env vars:
        CARD_CELLULANT_API_BASE    e.g. https://apis.cellulant.io
        CARD_CELLULANT_CLIENT_ID   Client ID from Cellulant developer portal
        CARD_API_KEY               API key / bearer token from Cellulant portal
        CARD_MERCHANT_ID           Service code from Cellulant portal
        CARD_IPN_URL               Your public callback URL

    TODO: verify exact endpoint path, auth header format, and response field names
          against https://developer.cellulant.io (Tingg checkout v3 docs).
    """
    api_base  = os.environ.get("CARD_CELLULANT_API_BASE")
    client_id = os.environ.get("CARD_CELLULANT_CLIENT_ID")
    api_key   = os.environ.get("CARD_API_KEY")
    service_code = os.environ.get("CARD_MERCHANT_ID")
    ipn_url   = os.environ.get("CARD_IPN_URL")

    missing = [k for k, v in {
        "CARD_CELLULANT_API_BASE":  api_base,
        "CARD_CELLULANT_CLIENT_ID": client_id,
        "CARD_API_KEY":             api_key,
        "CARD_MERCHANT_ID":         service_code,
        "CARD_IPN_URL":             ipn_url,
    }.items() if not v]
    if missing:
        return False, f"Cellulant env vars missing: {', '.join(missing)}."

    merchant_tx_id = str(payment_id)[:30]
    payload = {
        "msisdn":               customer_phone or "",
        "countryCode":          "KE",
        "currencyCode":         "KES",
        "accountNumber":        merchant_tx_id,
        "serviceCode":          service_code,
        "dueDate":              datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "requestAmount":        float(amount),
        "merchantTransactionID": merchant_tx_id,
        "callbackUrl":          ipn_url,
        "customerEmail":        customer_email or "",
        "description":          f"Tab payment {str(tab_id)[:20]}",
    }
    try:
        resp = httpx.post(
            f"{api_base}/v2/payments/request",  # TODO: verify from Cellulant Tingg v3 docs
            json=payload,
            headers={
                "clientId":     client_id,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return False, "Cellulant API timed out after 15 seconds."
    except httpx.HTTPStatusError as e:
        return False, f"Cellulant API HTTP error: {e.response.status_code}."
    except Exception as e:
        return False, f"Cellulant API request failed: {type(e).__name__}: {e}"

    # TODO: verify status code field name and success values from Cellulant response spec
    status = data.get("statusCode")
    if str(status) not in ("200", "201"):
        return False, f"Cellulant rejected payment: {data.get('statusDescription', 'unknown')}."

    # TODO: verify redirect/checkout URL field name from Cellulant response spec
    payment_url = data.get("checkoutUrl") or data.get("redirectUrl")
    if not payment_url:
        return False, "Cellulant did not return a payment URL."

    return True, {
        "payment_url":     payment_url,
        "transaction_ref": data.get("merchantTransactionID", merchant_tx_id),
        "provider":        "cellulant",
    }


# ── IPN handler ──────────────────────────────────────────────────

def handle_card_ipn(payload: dict) -> Tuple[bool, any]:
    """
    Process a card IPN from any configured gateway.
    Detects provider from payload shape then delegates.

    Pesapal:   has OrderTrackingId at top level
    DPO:       has TransactionApproval or transactionToken at top level
    Cellulant: has merchantTransactionID + serviceCode at top level

    Returns (True, payment_id) on success or idempotent duplicate.
    Returns (False, error_message) on bad payload or write failure.
    """
    if "OrderTrackingId" in payload:
        return _handle_pesapal_ipn(payload)
    elif "TransactionApproval" in payload or "transactionToken" in payload:
        return _handle_dpo_ipn(payload)
    elif "merchantTransactionID" in payload and "serviceCode" in payload:
        return _handle_cellulant_ipn(payload)
    else:
        AuditLog.log(
            actor="card_gateway",
            action="payment.card_ipn_unrecognized",
            target="unknown",
            details=f"payload_preview={str(payload)[:120]!r}",
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, "Unrecognized IPN format. Logged for pattern review."


def _handle_pesapal_ipn(payload: dict) -> Tuple[bool, any]:
    """
    Handle a Pesapal payment notification.

    Pesapal sends: OrderTrackingId, OrderMerchantReference, OrderNotificationType, Amount.

    TODO: In production, call GET /api/Transactions/GetTransactionStatus to confirm
          completion and get the authoritative amount rather than trusting the IPN payload.
          Requires a valid Bearer token — use _get_pesapal_token() here.
    """
    tracking_id = payload.get("OrderTrackingId")
    merchant_ref = payload.get("OrderMerchantReference", "")

    if not tracking_id:
        return False, "Pesapal IPN missing OrderTrackingId."

    # TODO: add status API call to confirm completion before writing Payment row
    raw_amount = payload.get("Amount", "0")
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    if amount <= 0:
        return False, "Pesapal IPN missing valid amount — call status API to retrieve."

    idem_key = f"cardipn-pesapal-{tracking_id}"
    existing = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing:
        return True, existing.id

    try:
        payment = Payment(
            method=PaymentMethod.CARD.value,
            amount=amount,
            card_ref=tracking_id[:50],
            received_by_id=None,
            idempotency_key=idem_key,
            description=f"Pesapal payment ref={merchant_ref[:40] if merchant_ref else tracking_id}",
        )
        db.session.add(payment)
        db.session.flush()

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.CARD.value,
            matched=True,
            statement_ref=tracking_id,
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="card_gateway",
            action="payment.card_ipn_pesapal",
            target=tracking_id,
            details=f"amount={amount} merchant_ref={merchant_ref}",
        )
        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"Pesapal IPN write failed: {type(e).__name__}: {e}"


def _handle_dpo_ipn(payload: dict) -> Tuple[bool, any]:
    """
    Handle a DPO Group payment notification.

    DPO sends (TODO: verify exact field names from DPO IPN docs):
        TransactionApproval, TransactionRef, CustomerName, CustomerCredit,
        TransactionAmount, TransactionFinalAmount, TransactionCurrency.
    """
    trans_token = payload.get("TransactionToken") or payload.get("transactionToken")
    trans_ref   = payload.get("TransactionRef", trans_token)
    approval    = payload.get("TransactionApproval", "")

    if not trans_token:
        return False, "DPO IPN missing TransactionToken."
    if str(approval).upper() != "YES":
        return False, f"DPO IPN: transaction not approved (approval={approval!r})."

    raw_amount = payload.get("TransactionFinalAmount") or payload.get("TransactionAmount", "0")
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    if amount <= 0:
        return False, "DPO IPN missing valid amount."

    idem_key = f"cardipn-dpo-{trans_token}"
    existing = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing:
        return True, existing.id

    try:
        payment = Payment(
            method=PaymentMethod.CARD.value,
            amount=amount,
            card_ref=str(trans_ref or trans_token)[:50],
            received_by_id=None,
            idempotency_key=idem_key,
            description=f"DPO payment token={str(trans_token)[:40]}",
        )
        db.session.add(payment)
        db.session.flush()

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.CARD.value,
            matched=True,
            statement_ref=str(trans_token),
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="card_gateway",
            action="payment.card_ipn_dpo",
            target=str(trans_token),
            details=f"amount={amount} trans_ref={trans_ref}",
        )
        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"DPO IPN write failed: {type(e).__name__}: {e}"


def _handle_cellulant_ipn(payload: dict) -> Tuple[bool, any]:
    """
    Handle a Cellulant Tingg payment notification.

    Cellulant sends (TODO: verify exact field names from Cellulant IPN docs):
        merchantTransactionID, serviceCode, requestAmount, payments[0].amount,
        paymentStatus (200 = success), checkoutRequestID.
    """
    tx_id      = payload.get("merchantTransactionID")
    status     = str(payload.get("paymentStatus", ""))

    if not tx_id:
        return False, "Cellulant IPN missing merchantTransactionID."
    if status != "200":
        return False, f"Cellulant IPN: payment not completed (status={status!r})."

    # Amount may be in requestAmount or nested payments[0].amount
    # TODO: verify correct amount field from Cellulant IPN spec
    raw_amount = payload.get("requestAmount", "0")
    if isinstance(payload.get("payments"), list) and payload["payments"]:
        raw_amount = payload["payments"][0].get("amount", raw_amount)
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    if amount <= 0:
        return False, "Cellulant IPN missing valid amount."

    idem_key = f"cardipn-cellulant-{tx_id}"
    existing = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing:
        return True, existing.id

    try:
        payment = Payment(
            method=PaymentMethod.CARD.value,
            amount=amount,
            card_ref=str(tx_id)[:50],
            received_by_id=None,
            idempotency_key=idem_key,
            description=f"Cellulant payment tx={str(tx_id)[:40]}",
        )
        db.session.add(payment)
        db.session.flush()

        recon = PaymentReconciliation(
            payment_id=payment.id,
            method=PaymentMethod.CARD.value,
            matched=True,
            statement_ref=str(tx_id),
            status=PaymentReconciliationStatus.MATCHED.value,
        )
        db.session.add(recon)

        AuditLog.log(
            actor="card_gateway",
            action="payment.card_ipn_cellulant",
            target=str(tx_id),
            details=f"amount={amount} service_code={payload.get('serviceCode')}",
        )
        db.session.commit()
        return True, payment.id
    except Exception as e:
        db.session.rollback()
        return False, f"Cellulant IPN write failed: {type(e).__name__}: {e}"


# ── Flask routes ─────────────────────────────────────────────────

@card_gateway_bp.post("/card/initiate")
@require_active_user
def card_initiate():
    """Cashier triggers a card payment — customer follows the returned URL."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    if not is_configured():
        return jsonify({
            "error": "Card gateway not configured.",
            "fallback": "Customer pays via terminal directly; record manually.",
        }), 503

    data = request.get_json(silent=True) or {}
    for field in ("amount", "tab_id", "payment_id"):
        if data.get(field) is None:
            return jsonify({"error": f"Missing required field: {field}."}), 400

    ok, result = initiate_card_payment(
        amount=data["amount"],
        tab_id=data["tab_id"],
        payment_id=data["payment_id"],
        customer_email=data.get("customer_email"),
        customer_phone=data.get("customer_phone"),
    )
    if not ok:
        return jsonify({"error": result}), 400
    return jsonify({
        "status":          "pending",
        "payment_url":     result["payment_url"],
        "transaction_ref": result["transaction_ref"],
        "provider":        result["provider"],
    }), 200


@card_gateway_bp.post("/card/callback")
def card_callback():
    """
    Public — card gateway calls this from the internet (no JWT).
    Always returns 200 so the gateway doesn't retry on our bugs.
    """
    from app.utils.webhook_validation import validate_webhook_payload
    ok, reason = validate_webhook_payload(request)
    if not ok:
        current_app.logger.warning(
            "card/callback rejected — ip=%s reason=%s", request.remote_addr, reason
        )
        return jsonify({"status": "accepted"}), 200

    try:
        payload = request.get_json(silent=True) or {}
        handle_card_ipn(payload)
    except Exception:
        current_app.logger.exception("Card IPN processing failed")
    return jsonify({"status": "accepted"}), 200


@card_gateway_bp.get("/card/status")
@require_active_user
def card_status():
    """Diagnostic — is the card gateway configured?"""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    configured, message = configuration_status()
    return jsonify({
        "configured": configured,
        "provider":   get_provider_name(),
        "message":    message,
    }), 200
