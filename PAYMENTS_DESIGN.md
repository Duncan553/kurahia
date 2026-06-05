# PAYMENTS_DESIGN.md
# Kurahia Resort — Payment Architecture

> **Status:** Design document. All three sockets (M-Pesa Daraja, bank API, card gateway)
> are dormant stubs. This document is the build brief for when credentials arrive.
> Tonight: design only. Tomorrow: build.

---

## 1. The Pattern (Manual + Dormant Socket)

### Why every method has two layers

Every payment method at Kurahia works on day one WITHOUT any external API.
The manual layer is the production path right now. The socket is the upgrade path later.

```
Day-one operation (MANUAL):
  Staff records payment by hand
        │
        ▼
  POST /tabs/:id/payments
  { method: "MPESA", amount: 500, mpesa_code: "QJN4X3P1ZB" }
        │
        ▼
  Payment row written (append-only)
        │
        ▼
  Cashier/manager reconciles at end of shift:
  GET  /finance/mpesa/pending
  POST /finance/mpesa/reconcile  { action: "MATCH", statement_ref: "QJN4X3P1ZB" }
        │
        ▼
  PaymentReconciliation row: status=MATCHED

Future operation (SOCKET ACTIVE):
  Customer pays till on their phone
        │
        ▼
  Safaricom C2B callback hits /finance/mpesa/callback
        │
        ▼
  SAME Payment row written automatically
        │
        ▼
  SAME PaymentReconciliation row written automatically (status=MATCHED)
        │
        ▼
  Waiter tablet notified — payment appears on "Pending Payments" screen
        │
        ▼
  Waiter taps the payment, assigns it to a tab → Tab balance updated
```

**The key design insight:** `PaymentReconciliation` was built socket-first.
Its own docstring says: *"Daraja API auto-match writes the same row automatically.
Socket ready — the flow doesn't change when automation arrives."*
Activation replaces a human step with an API call. The data model is identical.

### How activation works (one-function swap)

Each socket lives in a single file with a single function body to replace:

| Socket | File | Function(s) to implement |
|--------|------|--------------------------|
| M-Pesa Daraja | `app/finance/mpesa.py` | `initiate_stk_push()`, handle C2B callback |
| Bank API | `app/finance/bank.py` (to create) | `verify_bank_transfer()`, handle webhook |
| Card gateway | `app/finance/card.py` (to create) | `initiate_card_payment()`, handle callback |

No other code changes. The pipelines (Payment model, reconciliation model,
tab balance derivation, audit log, judge alerts) are already wired.

### The invariants that never change

These apply to ALL payment methods, manual or automatic:

1. **Money is `Decimal`, never `float`.** `Payment.amount` is `NUMERIC(14,2)`.
2. **Payments are append-only.** No DELETE or PATCH endpoint exists on the Payment table.
   `Payment.amount > 0` is enforced by a DB-level CHECK constraint.
3. **Tab balance is derived, not stored.**
   `balance = SUM(charges) - SUM(payments)`. The Payment row IS the source of truth.
4. **Every payment carries an `idempotency_key`.**
   Duplicate callbacks from Safaricom or the card gateway are silently ignored.
5. **Every write carries an audit log entry.**
   `AuditLog.log(actor, action, target, details)` fires on every payment event.

---

## 2. The Unified Waiter Tablet UI

### The "Pending Payments" screen

This screen doesn't exist in the codebase yet — it's the next frontend chunk.
This section is the product spec for when it's built.

**What it shows:**

```
┌─────────────────────────────────────────────────────────┐
│  PENDING PAYMENTS                         [Refresh]      │
├─────────────────────────────────────────────────────────┤
│  ⏳  M-Pesa  KSh 1,500    QJN4X3P1ZB    14:32  [Assign] │
│  ⏳  M-Pesa  KSh   300    RKP7Y2Q4WC    14:28  [Assign] │
│  ✓   M-Pesa  KSh 2,000    LMN8Z5A3VB    14:15  Tab #12  │
│  ⏳  Card    KSh 4,200    REF-000412     13:55  [Assign] │
└─────────────────────────────────────────────────────────┘
```

**What "Assign" does:**

Waiter taps [Assign] → drawer opens → waiter selects a tab → payment links to tab →
tab balance recalculates → `✓` appears on the row → payment is no longer pending.

**Backend endpoint needed:**

```
POST /payments/:payment_id/assign-to-tab
Body: { "tab_id": "uuid" }

Effect:
  - Sets Payment.tab_id
  - Recalculates tab.balance (derived — no stored field to update)
  - Returns the updated tab balance
```

This endpoint does not exist yet. It will be Chunk C-2 work.

**Why payments can arrive without a tab:**

With Daraja active, a customer pays the till BEFORE they've been assigned a tab
(they just walked in and paid at the gate kiosk). The payment lands in the system
immediately. The waiter's job is to link it to the right tab once the customer
sits down or checks in. This is a natural hospitality workflow.

**For manual entry (current day-one flow):**

The waiter records the payment directly against the tab:
`POST /tabs/:tab_id/payments`
No pending-payments screen needed. The tab_id is known at time of entry.

The pending-payments screen becomes important when the socket is active and payments
arrive without a tab assignment.

### Tab balance after payment

The balance formula is the same regardless of payment method:

```python
# From app/services/finance.py (conceptual — not yet written for tab balance)
balance = (
    db.session.query(func.sum(Charge.amount))
    .filter_by(tab_id=tab_id).scalar() or 0
) - (
    db.session.query(func.sum(Payment.amount))
    .filter_by(tab_id=tab_id).scalar() or 0
)
```

A tab with KSh 3,000 in charges and KSh 1,500 in payments has a balance of KSh 1,500 owing.
A wristband tab starts at -3,000 (the entry payment is applied at issuance).

---

## 3. M-Pesa Daraja Socket

### 3.1 C2B listener (auto-receive when customer pays till)

**What C2B means:**
Customer-to-Business. The customer opens their Safaricom app, selects the resort's
Till Number (Buy Goods) or Pay Bill, and pays. Safaricom sends an HTTP POST to a
registered callback URL. The system receives it automatically.

**Flow:**

```
Customer phone
     │
     │  M-Pesa app: "Pay 1,500 to Till 123456"
     ▼
Safaricom servers
     │
     │  POST https://relay.kurahia.com/finance/mpesa/callback
     │  {
     │    "TransactionType": "Pay Bill",
     │    "TransID": "QJN4X3P1ZB",
     │    "TransAmount": "1500.00",
     │    "BusinessShortCode": "123456",
     │    "BillRefNumber": "TAB-0042",   ← waiter gives customer this reference
     │    "MSISDN": "2547XXXXXXXX",
     │    "FirstName": "WACHIRA"
     │  }
     ▼
/finance/mpesa/callback  ← new endpoint to build
     │
     │  1. Verify HMAC signature (Daraja header)
     │  2. Check idempotency (TransID = idempotency_key)
     │  3. Create Payment row (method=MPESA, amount=1500, mpesa_code="QJN4X3P1ZB")
     │  4. Create PaymentReconciliation row (status=MATCHED, statement_ref="QJN4X3P1ZB")
     │  5. If BillRefNumber matches a tab → set Payment.tab_id automatically
     │  6. Return { "ResultCode": 0, "ResultDesc": "Accepted" } to Safaricom
     ▼
Payment is in the system, auto-matched, tab assigned (if ref was provided)
```

**BillRefNumber convention (to brief staff):**

The waiter gives the customer a reference number to type when paying.
Convention: `TAB-<band_number>` or `TABLE-<table_number>`.
Example: Customer at band #42 → waiter says "pay to 123456, reference TAB-42".
System uses BillRefNumber to auto-assign the payment to the right tab.
If no reference or unrecognised reference → payment lands in "Pending Payments" screen.

**Safaricom's response requirement:**

Safaricom expects a JSON response within 5 seconds:
```json
{ "ResultCode": 0, "ResultDesc": "Accepted" }
```
If the response times out or returns non-zero ResultCode, Safaricom retries.
This is why idempotency on `TransID` is critical — you will get duplicate callbacks.

### 3.2 STK Push (cashier-initiated charge to customer phone)

**What STK Push means:**
Cashier-to-Customer. The cashier enters the customer's phone number and amount.
Safaricom sends a PIN prompt to the customer's phone. Customer enters their M-Pesa PIN.
Money moves. Safaricom sends a callback confirming success or failure.

**Flow:**

```
Cashier tablet
     │
     │  POST /finance/mpesa/stk-push
     │  { "phone": "0712345678", "amount": 1500, "tab_id": "uuid", "account_ref": "TAB-42" }
     ▼
/finance/mpesa/stk-push  ← new endpoint to build
     │
     │  1. Format phone: 0712345678 → 254712345678
     │  2. Generate password: Base64(ShortCode + Passkey + Timestamp)
     │  3. POST to Daraja STK Push API
     │     https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest
     │  4. Record CheckoutRequestID (for idempotency + status polling)
     │  5. Return 202 Accepted to cashier ("prompt sent to customer")
     ▼
Customer phone receives PIN prompt
     │
     │  Customer enters PIN
     ▼
Safaricom sends callback to /finance/mpesa/stk-callback
     │
     │  Success: { "ResultCode": 0, "CallbackMetadata": { "Amount": 1500, "MpesaReceiptNumber": "QJN..." } }
     │  Failure: { "ResultCode": 1032, "ResultDesc": "Request cancelled by user" }
     ▼
/finance/mpesa/stk-callback  ← new endpoint to build
     │
     │  Success path:
     │    - Create Payment row (method=MPESA, amount=1500, mpesa_code="QJN...")
     │    - Create PaymentReconciliation (status=MATCHED)
     │    - Assign to tab if tab_id was stored with the CheckoutRequestID
     │
     │  Failure path:
     │    - Write to audit log (customer cancelled / insufficient funds)
     │    - No Payment row created
     │    - Return plain-English error to cashier tablet
     ▼
```

**STK Push vs C2B — which to use:**

| Scenario | Use |
|----------|-----|
| Customer pays self-service at kiosk | C2B (they initiate) |
| Cashier collects payment at POS | STK Push (cashier initiates) |
| Customer settles bill at table | Either — STK Push is smoother UX |
| Advance deposit for villa booking | STK Push (cashier initiates from booking screen) |

### 3.3 Env vars and activation

Required environment variables (all set in `.env.production`):

```bash
MPESA_CONSUMER_KEY=<from Daraja portal>
MPESA_CONSUMER_SECRET=<from Daraja portal>
MPESA_SHORTCODE=<your Till Number or Pay Bill shortcode>
MPESA_PASSKEY=<from Daraja portal — used for STK Push password generation>
MPESA_CALLBACK_URL=https://relay.kurahia.com/finance/mpesa/callback
MPESA_ENV=sandbox     # change to 'production' after sandbox tests pass
```

**Daraja API base URLs:**

```python
DARAJA_URLS = {
    "sandbox":    "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}
# Usage: base = DARAJA_URLS[os.getenv("MPESA_ENV", "sandbox")]
```

**Token acquisition (OAuth, expires in 1 hour):**

```python
import base64, os, requests

def get_daraja_token() -> str:
    key    = os.environ["MPESA_CONSUMER_KEY"]
    secret = os.environ["MPESA_CONSUMER_SECRET"]
    creds  = base64.b64encode(f"{key}:{secret}".encode()).decode()
    base   = DARAJA_URLS[os.getenv("MPESA_ENV", "sandbox")]
    resp   = requests.get(
        f"{base}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {creds}"},
        timeout=10,
    )
    return resp.json()["access_token"]
```

Cache the token. Don't call this on every payment — it counts against rate limits.

### 3.4 Callback URL topology

**The problem:** Safaricom requires a public HTTPS URL for callbacks.
The hotel server is on a private LAN — not publicly reachable.

**Option A — VPS relay (recommended for production):**

```
Safaricom → VPS (DigitalOcean/Hetzner, KSh 800/month)
                │
                │  Reverse proxy or simple forwarder
                ▼
           Tailscale tunnel
                │
                ▼
           Hotel server (private LAN)
                │
                ▼
           /finance/mpesa/callback
```

The VPS runs a tiny nginx that forwards the Daraja POST to the hotel server
via its Tailscale IP. The hotel server never needs a public IP.

**Nginx relay config on VPS:**

```nginx
server {
    listen 443 ssl;
    server_name relay.kurahia.com;

    location /finance/mpesa/ {
        proxy_pass http://100.x.x.x:443;   # hotel server's Tailscale IP
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Option B — Cloudflare Tunnel (zero server cost):**

```
Safaricom → Cloudflare edge → cloudflared daemon on hotel server
                                     │
                                     ▼
                              /finance/mpesa/callback
```

Cloudflare Tunnel is free. `cloudflared` runs as a systemd service on the hotel server.
No VPS needed. Slightly more complex to set up.

```bash
# Install and authenticate
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
     -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared tunnel login
cloudflared tunnel create kurahia
cloudflared tunnel route dns kurahia relay.kurahia.com

# Config file /etc/cloudflared/config.yml:
# tunnel: kurahia
# ingress:
#   - hostname: relay.kurahia.com
#     service: https://localhost:443
#   - service: http_status:404
```

**Recommendation:** Start with Cloudflare Tunnel (free, less infrastructure).
Move to VPS relay if Cloudflare introduces latency issues or rate limits.

### 3.5 Idempotency and retries

Safaricom retries callbacks if it doesn't receive a 200 response within 5 seconds.
This means the same transaction can arrive 2-3 times.

**The idempotency contract:**

```python
# At the top of the C2B callback handler:
trans_id = data.get("TransID")  # e.g. "QJN4X3P1ZB"

existing = db.session.query(Payment).filter_by(
    idempotency_key=trans_id
).first()
if existing:
    # Already processed — acknowledge and return immediately
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

# ... process the new payment ...
```

**The STK Push idempotency contract:**

Store the `CheckoutRequestID` when you initiate the push.
When the callback arrives, match on `CheckoutRequestID` to identify the tab.
If the callback arrives twice, the second one finds the Payment row already exists
(via `idempotency_key=MpesaReceiptNumber`) and returns 200 without creating a duplicate.

**Payment.idempotency_key for M-Pesa:**

| Scenario | Value |
|----------|-------|
| C2B payment | `TransID` (e.g. "QJN4X3P1ZB") |
| STK Push success | `MpesaReceiptNumber` from callback |
| Manual entry | UUID generated at time of entry |

### 3.6 Failure modes

| Failure | System behavior | Owner visibility |
|---------|-----------------|------------------|
| Daraja callback times out (hotel server down) | Safaricom retries 3x. Payment missed if server offline >5 min. | Cashier notices customer paid but no receipt. Manual fallback: cashier enters payment manually. |
| Wrong BillRefNumber typed by customer | Payment lands in "Pending Payments" — no auto-assign to tab. | Waiter assigns manually from the screen. |
| STK Push: customer cancels | `ResultCode: 1032`. No Payment created. Audit log entry written. | Cashier sees "Customer cancelled" message. Retry or request cash. |
| STK Push: insufficient funds | `ResultCode: 1`. No Payment created. Audit log entry. | Cashier sees "Insufficient funds" message. |
| Token refresh fails | STK Push endpoint returns 503 with plain-English error. | Cashier directed to manual M-Pesa entry. C2B callbacks unaffected. |
| Duplicate callback | Idempotency check returns 200 immediately. No duplicate Payment. | Invisible to owner — correct behavior. |
| `MPESA_ENV=sandbox` in production | Daraja sandbox accepts transactions but no real money moves. | **Critical**: owner must flip to `production` before go-live. |

### 3.6.1 Production Hardening TODOs

These are deliberately excluded from the current build. Nothing here blocks sandbox
testing. All of these must be done before real money flows through the socket.

**IP allowlisting on `/finance/mpesa/callback`**

Safaricom publishes the IP ranges their callback servers use. Restrict the callback
endpoint to those IPs only — reject anything else with a 403. This stops anyone from
POSTing fake callbacks to your public URL.
Important: Safaricom's callback IPs can change. Re-verify the allowlist against their
developer portal before each production deploy, not just at initial setup.

**Monitoring**

Add structured logging for:
- Callback latency (time from STK Push initiation to callback receipt)
- Callback failure rate (how often `handle_stk_callback` or `handle_c2b_callback` returns `False`)
- OAuth token refresh frequency (excessive refreshes indicate token cache is being bypassed or expiring early)

A spike in callback failure rate with no corresponding spike in latency means a payload
format change from Safaricom — check their changelog.

**Alerting: orphaned STK Push entries**

If no Daraja callback arrives within 60 seconds of a successful STK Push, there may
be an orphaned entry in `_pending_stk` — the customer was prompted but the callback
was lost. Fire a `JudgeAlert` so the cashier can follow up manually.
Implementation: a background job (Flask-APScheduler or a cron hitting a CLI command)
checks `_pending_stk` for entries older than 60 seconds and fires the alert.

**Optional: `datetime.utcnow()` → `datetime.now(timezone.utc)`**

`datetime.utcnow()` is deprecated in Python 3.12. It still works but emits a
deprecation warning in newer Python versions. Replace with
`datetime.now(timezone.utc)` across `mpesa_daraja.py` when convenient.
This is a cosmetic fix — it does not affect any stored data or behavior.

**Optional: persist `_pending_stk` to the database**

Currently `_pending_stk` is an in-memory dict. If the server restarts between an
STK Push and its callback, the callback arrives but can't link to the originating tab
(the dict is empty). The payment still lands in the system via idempotency, but without
a tab assignment — it goes to "Pending Payments" for manual assignment.
This is the documented and acceptable fallback at hotel scale (low STK Push volume,
short server restart windows). If STK Push volume grows or the server restarts
frequently, move `_pending_stk` to a DB table with a TTL column.

---

## 4. Bank API Socket

### 4.1 Provider-agnostic abstraction

Kenya has three main banks with developer APIs:

| Bank | API name | Notes |
|------|----------|-------|
| Equity Bank | Equity Jenga API | Most documented, fastest sandbox |
| KCB | KCB Open Banking | Requires formal business relationship |
| Co-operative Bank | Co-op Bank API | Good SME support |

The design uses a provider-agnostic function signature so swapping banks
doesn't require a data model change:

```python
# app/finance/bank.py (to create)

def verify_bank_transfer(
    reference: str,          # the reference the customer typed when paying
    expected_amount: Decimal,
    account_number: str,
) -> tuple[bool, str, Decimal]:
    """
    Returns (matched, bank_reference, confirmed_amount).
    Provider-specific code goes here. The caller doesn't know which bank.
    """
    provider = os.getenv("BANK_PROVIDER", "")  # "equity" | "kcb" | "coop"
    if provider == "equity":
        return _verify_equity(reference, expected_amount, account_number)
    elif provider == "kcb":
        return _verify_kcb(reference, expected_amount, account_number)
    # ...
    return (False, "", Decimal("0"))   # UNCONFIGURED
```

### 4.2 Manual flow at launch (current)

Bank transfers are currently handled manually — the same way M-Pesa was before
Daraja was an option. The existing `PaymentMethod.CARD` value covers bank transfers
at launch (a card payment and a bank transfer both produce a reference number that
gets reconciled against a statement).

**Forthcoming schema change needed:**

`PaymentMethod` currently has: `CASH`, `CARD`, `MPESA`.
Bank transfers should get their own method for cleaner reporting:

```python
class PaymentMethod(str, enum.Enum):
    CASH          = "CASH"
    CARD          = "CARD"
    MPESA         = "MPESA"
    BANK_TRANSFER = "BANK_TRANSFER"   # ← add this when building the socket
```

This requires a migration (`flask db migrate`). No other code changes — the
reconciliation flow, tab balance formula, and audit log all work on any method.

**Current day-one manual flow for bank transfers:**

```
Customer makes bank transfer: KSh 50,000 for villa deposit
      │
      │  Transaction reference: "FT231204A1B2"
      ▼
Cashier records in system:
POST /bookings/:id/deposits
{
  "method": "CARD",   ← using CARD as a stand-in for now
  "amount": "50000",
  "card_ref": "FT231204A1B2",
  "idempotency_key": "uuid"
}
      │
      ▼
Payment row created (method=CARD, card_ref="FT231204A1B2")
      │
      ▼
Manager reconciles at end of day:
POST /finance/mpesa/reconcile
{ "entries": [{ "payment_id": "uuid", "action": "MATCH", "statement_ref": "FT231204A1B2" }] }
```

### 4.3 SMS forwarder option (no bank API needed)

An alternative to the bank API that requires zero integration work:
banks SMS the account holder when a transfer arrives. A forwarding app on the
owner's phone can send those SMSs to the system.

```
Bank SMS → owner phone
     │
     │  SMS forwarder app (SMSSync / Android SMS Gateway)
     ▼
POST https://relay.kurahia.com/finance/bank/sms-forward
{
  "from": "+254711111111",
  "body": "KCB: You have received KES 50,000.00 from JOHN DOE Ref: FT231204A1B2"
}
     │
     │  System parses the SMS body (bank-specific regex)
     │  Extracts: amount, reference, sender name
     ▼
Auto-creates Payment + PaymentReconciliation (status=MATCHED)
```

**Tradeoffs:**

| | Bank API | SMS forwarder |
|-|----------|---------------|
| Setup effort | High (formal application, 2-4 weeks) | Low (install app, 1 hour) |
| Reliability | High (direct API) | Medium (depends on SMS delivery) |
| Cost | Per-API-call fees | Free |
| Works offline | No | Yes (SMS buffer) |

**Recommendation:** Launch with SMS forwarder. Replace with bank API when
volume justifies the formal application process.

### 4.4 Env vars and activation

```bash
# Bank API path
BANK_PROVIDER=equity              # equity | kcb | coop
BANK_API_KEY=<from bank portal>
BANK_API_SECRET=<from bank portal>
BANK_ACCOUNT_NUMBER=<resort account>
BANK_CALLBACK_URL=https://relay.kurahia.com/finance/bank/callback

# SMS forwarder path (alternative — no API needed)
BANK_SMS_FORWARDER_TOKEN=<a random secret — validates incoming SMS forwards>
```

### 4.5 Failure modes

| Failure | System behavior | Owner visibility |
|---------|-----------------|------------------|
| Bank API down | `verify_bank_transfer()` returns `(False, "", 0)`. Payment stays UNMATCHED. | Manager reconciles manually at end of day. |
| SMS forwarder drops an SMS | Transfer not auto-matched. | Manager sees UNMATCHED payment in reconciliation report. Manual match. |
| Wrong reference typed by customer | Auto-match fails. Payment lands unmatched. | Manager sees it in reconciliation screen. One-click manual match. |
| Bank changes their SMS format | SMS parser stops matching. | All transfers land unmatched. SMS parser needs a regex update. |

### 4.6 Production Hardening TODOs

These are deliberately excluded from the current build. Nothing here blocks activation.
All of the API-path items must be resolved before real money flows through Layer 3.

**Verify real API endpoints and response fields (required before Layer 3 go-live)**

Three `# TODO` markers remain in `app/finance/bank_transfer.py` — one per provider.
Each marks an endpoint URL and response field name that was inferred from public docs
and must be confirmed against the actual production API before go-live:

- `_verify_equity`: endpoint `/v3/account/transaction` and fields `status`, `amount`, `transactionDate`
  → verify at https://developer.equitybankgroup.com (Jenga v3 docs)
- `_verify_kcb`: OAuth token endpoint `/oauth/token`, query endpoint `/v1/account/transactions`,
  fields `status`, `amount`, `transactionDate`
  → verify at https://developer.kcbgroup.com
- `_verify_coop`: auth mechanism (Basic auth assumed — may be OAuth), endpoint
  `/api/1.0/Transactions/Statement`, fields `Successful`, `Amount`, `TransactionDate`
  → verify at https://developer.co-opbank.co.ke

**IP allowlisting on `/finance/bank/sms-forward`**

If your SMS forwarder app routes through a fixed IP (e.g. a dedicated VPS relay),
restrict the endpoint to that IP range. Blocks anyone who guesses your webhook URL from
POSTing fake bank credit notifications. Low priority while the webhook secret is in place —
both checks together is the right long-term posture.

**Monitoring**

Add structured logging for:
- SMS forward latency (time between SMS receipt on phone and Payment row written)
- Parse failure rate (`payment.bank_sms_unrecognized` events per hour) — a spike means
  a bank changed their SMS format
- Bank API verification success rate per provider and per day — a drop means the bank
  API endpoint changed or their sandbox is down

**Alerting: SMS format drift**

If more than 5 consecutive SMS payloads hit `payment.bank_sms_unrecognized` within
an hour, fire a `JudgeAlert`. This is the fastest signal that a bank changed their
credit notification SMS format after a core banking upgrade. Without the alert, the
first sign of the problem is the manager noticing the pending list is full.
Implementation: count `AuditLog` entries with `action="payment.bank_sms_unrecognized"`
in a rolling window; fire if threshold exceeded.

**Optional: persist SMS format patterns to the database**

Currently `_BANK_SMS_PATTERNS` is a list of compiled regexes in Python code.
When a bank changes their SMS format, a code deploy is needed to update the regex.
A future improvement: move patterns to a DB table (`bank_sms_patterns`) with columns
`bank_name`, `regex_pattern`, `is_active`. Owner can update patterns via a CLI command
without a redeploy. Only worth doing if SMS format changes become frequent (more than
once per year per bank).

---

## 5. Card Gateway Socket

### 5.1 Provider-agnostic abstraction

Kenya's top card/digital payment gateways:

| Provider | Products | Notes |
|----------|----------|-------|
| Pesapal | Visa/Mastercard + M-Pesa | Widely used, good KE support |
| DPO Group | Visa/Mastercard + Airtel Money | Pan-Africa, formal onboarding |
| Cellulant | Tingg — unified Africa payments | M-Pesa + cards + bank in one |

Same provider-agnostic pattern as bank API:

```python
# app/finance/card.py (to create)

def initiate_card_payment(
    amount: Decimal,
    tab_id: str,
    reference: str,
    callback_url: str,
) -> tuple[str, str]:
    """
    Returns (payment_url, transaction_ref).
    Cashier directs customer to payment_url or shows QR code.
    """
    provider = os.getenv("CARD_PROVIDER", "")
    if provider == "pesapal":
        return _pesapal_initiate(amount, reference, callback_url)
    elif provider == "dpo":
        return _dpo_initiate(amount, reference, callback_url)
    # ...
    return ("", "UNCONFIGURED")
```

### 5.2 Manual flow at launch (current)

Card payments currently use `PaymentMethod.CARD` with a `card_ref` field.
The card_ref is the receipt number from the physical POS terminal.

```
Customer taps card at physical POS terminal
     │
     │  Terminal prints receipt: "AUTH: 123456  REF: 0042"
     ▼
Cashier records in system:
POST /tabs/:tab_id/payments
{
  "method": "CARD",
  "amount": "4200",
  "card_ref": "AUTH-123456-REF-0042",
  "idempotency_key": "uuid"
}
     │
     ▼
Manager reconciles via /finance/mpesa/pending (CARD payments visible here too)
POST /finance/mpesa/reconcile
{ "entries": [{ "payment_id": "uuid", "action": "MATCH", "statement_ref": "AUTH-123456" }] }
```

**Note:** `/finance/mpesa/reconcile` handles both M-Pesa and card reconciliation —
the `_pending_by_method()` function in `mpesa.py` accepts any PaymentMethod value,
and the endpoint validates that the payment is either MPESA or CARD. The naming
is a legacy artifact; the function is payment-method-agnostic.

### 5.3 Env vars and activation

```bash
CARD_PROVIDER=pesapal              # pesapal | dpo | cellulant
CARD_API_KEY=<from gateway portal>
CARD_API_SECRET=<from gateway portal>
CARD_IPN_URL=https://relay.kurahia.com/finance/card/callback
CARD_MERCHANT_ID=<from gateway portal>
```

### 5.4 Failure modes

| Failure | System behavior | Owner visibility |
|---------|-----------------|------------------|
| Gateway API down | `initiate_card_payment()` returns `("", "UNCONFIGURED")`. Plain-English error to cashier. | Cashier accepts physical card terminal + manual entry as fallback. |
| Customer abandons payment URL | No callback received. Payment row never created. | Tab balance unchanged — cashier knows. Retry or switch method. |
| Duplicate IPN callback | Idempotency check on `transaction_ref`. Second callback ignored. | Invisible — correct behavior. |
| Card declined | Gateway sends failure callback. Audit log entry. | Cashier sees "Card declined" message. Customer pays another way. |
| `CARD_PROVIDER` not set | Function returns `("", "UNCONFIGURED")`. Cashier routed to manual flow. | Error shown: "Card gateway not configured. Use manual card entry." |

### 5.5 Production Hardening TODOs

These are deliberately excluded from the current build. None block testing. Resolve
all API-specific items before any real card transaction flows through the system.

**Verify real provider API endpoints + auth flows (required before go-live)**

The code contains `# TODO` markers for all three providers:
- Pesapal: `CARD_API_SECRET` handling in OAuth (currently uses `CARD_API_KEY` as both
  key and secret as a placeholder); status API call in IPN handler to confirm completion
  before writing Payment row
- DPO: ServiceType code (`3854` used — must match account's registered service codes);
  exact API version path (`/API/v6/`) — verify from DPO portal docs
- Cellulant: endpoint path (`/v2/payments/request`), auth header format (`clientId`
  header + Bearer token), response field names (`checkoutUrl` vs `redirectUrl`),
  IPN amount field location — verify from Cellulant Tingg v3 docs

**IPN-not-received fallback (polling job)**

If a customer completes payment on the provider side but the IPN never arrives (tunnel
was down, provider had a delivery failure), the tab balance stays wrong. Add a background
job that: queries initiate_card_payment log entries older than 5 minutes with no matching
Payment row; fires a `JudgeAlert` so a manager can check the provider dashboard and
manually reconcile if needed. No automatic retry — let a human confirm first.

**Webhook signature verification**

Currently the `/finance/card/callback` endpoint trusts any POST. Providers offer
signature verification to prove the IPN came from them:
- Pesapal: HMAC-SHA256 of the IPN payload using your consumer secret
- DPO: XML signature in the IPN POST body
- Cellulant: JWT-signed payload using a shared secret

Add signature verification before processing each IPN. Reject unsigned IPNs with a 401
(but still log the payload for debugging). This blocks anyone who discovers your
callback URL from injecting fake payment notifications.

**Monitoring**

Add structured logging for:
- IPN delivery latency (time from cashier triggering initiate to IPN received)
- IPN parse failure rate per provider (unrecognized payload shape)
- Initiation-to-completion latency per provider (useful for UX comparison between providers)
- OAuth token refresh frequency (Pesapal — excessive refreshes indicate cache is bypassed)

**Alerting: IPN failure rate threshold**

If more than 5% of IPNs from a provider result in `handle_card_ipn()` returning `False`
within any 1-hour window, fire a `JudgeAlert`. This signals a payload format change
(provider updated their IPN schema without notice) or a systematic integration issue.
Implementation: count `payment.card_ipn_unrecognized` audit log events against total
IPN volume in a rolling window.

**IP allowlisting on `/finance/card/callback`**

If any provider publishes fixed IP ranges for their IPN servers, add those to an
allowlist. Pesapal and DPO have IPN delivery from specific IP blocks — check each
provider's developer documentation. IP allowlisting + signature verification together
make the callback endpoint substantially harder to abuse.

**Currency handling**

All current implementations assume KES. The Payment model and gateway payloads hardcode
`"currency": "KES"` and `"PaymentCurrency": "KES"`. If Kurahia ever takes payments
from foreign guests in USD or EUR, the currency handling needs a full design pass before
that flows through here. Until then: KES only, no exceptions.

**Card refund flow (not implemented)**

There is no refund endpoint. If a customer is overcharged or a booking is cancelled
after card payment, the current process is: contact the provider gateway's merchant
portal and issue the refund there manually. The Payment row stays in the system
(append-only). Add a `refund` note to the tab or booking for audit purposes. A
programmatic refund API endpoint would be a separate design effort (each provider
has a different refund API shape).

---

## 6. Shared Components

### 6.1 PaymentReconciliation model usage

The `PaymentReconciliation` table is the single truth-table for whether a payment
has been verified against an external source (bank statement, Safaricom STK response,
card gateway IPN).

```
Payment (append-only)              PaymentReconciliation (one-to-one)
─────────────────────              ─────────────────────────────────────
id                           ←──  payment_id (UNIQUE FK)
method: MPESA/CARD/CASH/           method: mirrors Payment.method
        BANK_TRANSFER              matched: True/False
amount: 1500.00                    matched_by_id: user who confirmed
mpesa_code: "QJN4X3P1ZB"          statement_ref: real ref from bank/Safaricom
card_ref: nullable String(50)      status: MATCHED | UNMATCHED | FLAGGED
bank_ref: nullable String(64)      notes: "Confirmed against statement 2026-06-03"
tab_id: "uuid"
idempotency_key: "QJN4X3P1ZB"
```

**Manual reconciliation** — human writes this row via API.
**Socket-active reconciliation** — callback handler writes this row automatically.
Same table. Same columns. Same queries. Zero migration when switching.

### 6.2 AuditLog integration

Every payment event writes an audit log entry:

| Event | action | actor | target | details |
|-------|--------|-------|--------|---------|
| Payment recorded (manual) | `payment.record` | waiter username | tab_id | `method=MPESA amount=1500` |
| C2B callback received | `payment.mpesa_c2b` | `"daraja"` | mpesa_code | `amount=1500 ref=QJN...` |
| STK Push initiated | `payment.stk_push` | cashier username | phone | `amount=1500 tab=uuid` |
| STK Push confirmed | `payment.stk_confirmed` | `"daraja"` | mpesa_receipt | `amount=1500` |
| Reconciliation: matched | `finance.mpesa.reconcile` | manager username | payment_id | `matched=1 flagged=0` |
| Reconciliation: flagged | `finance.mpesa.reconcile` | manager username | payment_id | `matched=0 flagged=1` |

The `actor="daraja"` convention means automated events are distinguishable from
human events in the audit trail. No user ID needed — the callback is not a human.

### 6.3 Plain-English error contract

Every error response from a payment endpoint carries a `message` field
the frontend can display directly to the user. No raw exceptions. No stack traces.

Examples:

```json
{ "error": "STK Push failed: customer cancelled the M-Pesa prompt." }
{ "error": "Card gateway not configured. Record the card reference manually." }
{ "error": "Payment QJN4X3P1ZB already processed — duplicate ignored." }
{ "error": "Amount must be greater than zero." }
{ "error": "Invalid M-Pesa code format. Expected 10 characters (e.g. QJN4X3P1ZB)." }
```

### 6.4 Test plan structure

Each socket needs the same test categories:

```
tests/test_finance_mpesa.py      ← M-Pesa Daraja tests
tests/test_finance_bank.py       ← Bank API tests
tests/test_finance_card.py       ← Card gateway tests
```

Per-socket tests:

| Test | What it verifies |
|------|-----------------|
| `test_manual_payment_recorded` | Manual flow works end-to-end |
| `test_idempotency_duplicate_ignored` | Same idempotency_key → 200, no new row |
| `test_callback_creates_payment` | Mock callback → Payment + Reconciliation created |
| `test_duplicate_callback_ignored` | Callback arrives twice → 1 Payment, not 2 |
| `test_tab_balance_updates` | Tab balance recalculates after payment assigned |
| `test_audit_log_written` | Every payment event writes to AuditLog |
| `test_unconfigured_socket_returns_plain_error` | No env vars → clean error, no 500 |
| `test_failure_callback_no_payment_created` | Decline/cancel → 0 Payment rows |

**Testing sockets without real credentials:**
Use `unittest.mock.patch` to mock the HTTP calls to Daraja/bank/gateway.
The socket function is a single function body — easy to mock at the boundary.
No test hits a real external API.

---

## 7. Activation Runbooks

### M-Pesa Daraja — when keys arrive

**What you need from Safaricom:**
1. Daraja portal account: https://developer.safaricom.co.ke
2. Consumer Key + Consumer Secret (from your app on the portal)
3. Till Number (Buy Goods) or Shortcode (Pay Bill)
4. Passkey (from the portal — needed for STK Push only)
5. Business shortcode whitelisted for C2B

**Time estimate:** 2-4 weeks for Safaricom approval. Start early.

**Steps:**
1. Set `MPESA_ENV=sandbox` and all MPESA vars in `.env.production`
2. Implement `initiate_stk_push()` in `app/finance/mpesa.py`
3. Add the C2B callback endpoint `/finance/mpesa/callback`
4. Set up callback URL relay (Cloudflare Tunnel or VPS — see §3.4)
5. Run sandbox tests: initiate a push from Daraja test portal → confirm Payment created
6. Run the test suite: `pytest tests/test_finance_mpesa.py -v`
7. Switch `MPESA_ENV=production`
8. Run one live transaction of KSh 1 to verify end-to-end
9. Remove sandbox credentials from `.env.production`

**Don't go live without:**
- [ ] Idempotency test passing (duplicate callback → no duplicate Payment)
- [ ] `MPESA_ENV=production` confirmed (not `sandbox`)
- [ ] Callback URL is HTTPS with a valid cert (Safaricom rejects HTTP)
- [ ] Response to Safaricom within 5 seconds (timeout testing done)

---

### Bank API (Equity Jenga / KCB / Co-op) — when keys arrive

**Faster alternative: SMS forwarder (no formal application needed)**

1. Install SMSSync on the owner's Android phone
2. Set up webhook: `https://relay.kurahia.com/finance/bank/sms-forward`
3. Set `BANK_SMS_FORWARDER_TOKEN=<random 32-char secret>` in `.env.production`
4. Implement `app/finance/bank.py` with SMS parser for your bank's SMS format
5. Test with a real bank transfer of KSh 10

**Full bank API path:**

1. Apply to your bank's developer portal (formal process, 2-6 weeks)
2. Set `BANK_PROVIDER`, `BANK_API_KEY`, `BANK_API_SECRET`, `BANK_ACCOUNT_NUMBER`
3. Create `app/finance/bank.py` with provider-specific verify function
4. Add `/finance/bank/callback` endpoint
5. Test in sandbox
6. Add `BANK_TRANSFER` to `PaymentMethod` enum + migration
7. Run `flask db migrate -m "add BANK_TRANSFER payment method"` + `flask db upgrade`
8. Run `pytest tests/test_finance_bank.py -v`
9. One live KSh 10 transfer to verify end-to-end

**Don't go live without:**
- [ ] `PaymentMethod.BANK_TRANSFER` migration applied to production DB
- [ ] Idempotency test passing
- [ ] Plain-English error when bank API is down (cashier falls back to manual)

---

### Card Gateway (Pesapal / DPO / Cellulant) — when keys arrive

**Recommended starting point: Pesapal**
Most established in Kenya. Good documentation. No minimum volume requirement.
Sign up: https://www.pesapal.com

**Steps:**
1. Create Pesapal merchant account (5 business days)
2. Set `CARD_PROVIDER=pesapal`, `CARD_API_KEY`, `CARD_API_SECRET`, `CARD_MERCHANT_ID`
3. Set `CARD_IPN_URL=https://relay.kurahia.com/finance/card/callback`
4. Create `app/finance/card.py` with Pesapal-specific initiate + callback handler
5. Test in Pesapal sandbox (test cards provided in their docs)
6. Run `pytest tests/test_finance_card.py -v`
7. One live KSh 1 transaction end-to-end before enabling for staff

**Don't go live without:**
- [ ] IPN (Instant Payment Notification) callback tested with duplicate delivery
- [ ] Customer-cancel flow tested (no Payment row created on cancel)
- [ ] Cashier fallback tested (physical terminal + manual entry) when gateway is down

---

## Appendix: Current State vs Target State

```
                        TODAY                    SOCKET ACTIVE
                   ─────────────           ─────────────────────────
M-Pesa             Manual entry            C2B auto-receive
                   Code typed by cashier   STK Push to customer phone
                   End-of-shift recon      Auto-reconciled in real time

Bank transfer      Manual entry            Bank webhook or SMS forwarder
                   Ref typed by cashier    Auto-reconciled on callback

Card               Physical POS terminal   Digital card page / QR
                   Ref typed by cashier    Auto-reconciled via IPN

Cash               Manual entry            Manual entry (stays manual)
                   End-of-shift recon      End-of-shift recon (no change)
```

Cash stays manual forever — there is no API for cash.
Everything else upgrades transparently through the same models and endpoints.

---

*Document status: design only. No code changed.*
*Next: implement M-Pesa Daraja socket (C2B + STK Push) as Chunk C-2.*
