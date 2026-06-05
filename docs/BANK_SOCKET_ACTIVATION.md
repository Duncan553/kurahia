# Bank Transfer Socket — Activation Runbook

> The bank socket has three layers. Layer 1 (manual entry) is active from day one.
> Layer 2 (SMS forwarder) takes one hour to activate. Layer 3 (bank API) takes 2-4 weeks.
> Activate in order. Each layer reduces manual work. The system works fine at Layer 1 forever.

---

## Layer 1 — Manual Entry (Active From Day One)

No setup needed. This is how bank transfers work right now.

### How a cashier records a bank transfer

A customer calls ahead and says "I've paid KES 50,000 via bank transfer, ref FT231204A1B2."
The cashier records it:

```bash
# Via the existing deposits endpoint (for villa booking deposits)
POST /bookings/:booking_id/deposits
{
  "method": "BANK_TRANSFER",
  "amount": "50000",
  "bank_ref": "FT231204A1B2",
  "idempotency_key": "<uuid>"
}
```

Or if it's a tab payment (rare — bank transfers usually go to deposits, not POS tabs):

```bash
POST /tabs/:tab_id/payments
{
  "method": "BANK_TRANSFER",
  "amount": "50000",
  "bank_ref": "FT231204A1B2",
  "idempotency_key": "<uuid>"
}
```

The `bank_ref` field stores the transaction reference exactly as the customer gave it.
Always use the reference from the actual bank SMS or statement — not what the customer
says from memory (customers misremember references constantly).

### How a manager reconciles at end of day

```bash
# See all unreconciled BANK_TRANSFER payments for today
GET /finance/bank/pending?date=2026-06-05

# Mark each as MATCHED (confirmed on bank statement) or FLAGGED (can't verify)
POST /finance/bank/reconcile
{
  "entries": [
    {
      "payment_id": "<uuid>",
      "action": "MATCH",
      "statement_ref": "FT231204A1B2",
      "notes": "Confirmed on KCB statement 2026-06-05"
    }
  ]
}
```

**MATCH** = you saw the matching entry on the actual bank statement.
**FLAG** = the payment was recorded but you can't find the matching bank entry. This fires
a `BANK_FLAGGED` JudgeAlert that the owner sees. Manager follows up the next day.

Flagged entries need to be resolved manually — either MATCH them once confirmed, or
reverse the tab charge if the transfer never happened.

---

## Layer 2 — SMS Forwarder Activation

When this is active: credit SMS notifications on the bank's SIM card get forwarded to
the system in real time. The system parses the SMS, creates a Payment row, and marks
it MATCHED automatically. No manager reconciliation step needed.

**Setup time: ~1 hour.**

### Step 1: Get the right Android app

Install one of these on the Android phone that has the bank's SIM:

- **SMS Forwarder for Webhooks** (search Google Play: "SMS Forwarder Webhook") —
  straightforward, sends raw SMS body to your URL via HTTP POST
- **SMSGate** — open-source, more configurable, supports custom headers

Both apps send a POST to your URL every time an SMS arrives. You filter by content.

Avoid Zapier/IFTTT-based approaches — they add latency and have rate limits.

### Step 2: Generate a webhook secret

This secret proves the SMS came from your forwarder app, not a random internet request.

```bash
# Generate a random 32-character secret
python3 -c "import secrets; print(secrets.token_hex(16))"
# Example output: a3f8d2c1b4e7f09a2d5c8b1e4f7a0d3c
```

Add to your `.env.production`:
```bash
BANK_SMS_WEBHOOK_SECRET=a3f8d2c1b4e7f09a2d5c8b1e4f7a0d3c
```

Restart the server so it picks up the new env var.

### Step 3: Configure the forwarder app

In the SMS forwarder app:
- **Webhook URL**: `https://relay.kurahia.com/finance/bank/sms-forward`
  (same relay server as M-Pesa — the Cloudflare Tunnel or VPS relay from MPESA_SANDBOX_TESTING.md §C)
- **Custom header**: `X-Webhook-Secret: a3f8d2c1b4e7f09a2d5c8b1e4f7a0d3c`
  (must match what you put in `BANK_SMS_WEBHOOK_SECRET`)
- **Filter**: Forward all SMSs, or filter to only forward from your bank's sender number.
  Filtering is optional — the system ignores SMSs it can't parse and logs them for review.

### Step 4: Test with a fake SMS via curl

Before real transfers, verify the endpoint is reachable and the secret works:

```bash
# Should return {"status": "accepted"} — 200
curl -s -X POST https://relay.kurahia.com/finance/bank/sms-forward \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: a3f8d2c1b4e7f09a2d5c8b1e4f7a0d3c" \
  -d '{
    "from": "+254719000000",
    "body": "Equity Bank: KES 2,400.00 received from JOHN DOE. Ref: EQTTEST001 on 05/06/2026 at 10:00."
  }'

# Verify the Payment row was created
flask shell
>>> from app.models.payment import Payment
>>> p = db.session.query(Payment).filter_by(bank_ref="EQTTEST001").first()
>>> print(p.amount, p.bank_ref, p.method)
# Expected: 2400.00 EQTTEST001 BANK_TRANSFER
```

### Supported SMS formats

The system recognises these formats. If your bank's format is different, add a regex
in `app/finance/bank_transfer.py` → `_BANK_SMS_PATTERNS`.

**Equity Bank:**
```
Equity Bank: KES 2,400.00 received from JOHN DOE. Ref: ABC123DEF on 05/06/2026 at 10:00.
```

**KCB:**
```
KCB Bank: Ksh2,500.00 received from 254712345678 on 05/06/2026. Ref EGH987654.
```

**Co-op Bank:**
```
Co-op Bank Acc:1234567890 Cr KES3,000.00 Ref:TXN20260604001 04Jun2026 12:00
```

Bank SMS formats change without warning. If the system stops auto-matching, check
the server logs for `payment.bank_sms_unrecognized` audit log entries — they include
the first 80 characters of the unrecognized body so you can update the regex.

### Check Layer 2 status

```bash
GET /finance/bank/status
# Expected with SMS active:
{
  "sms_configured": true,
  "api_configured": false,
  "provider": null,
  "message": "Bank SMS forwarder active. Bank API dormant — BANK_PROVIDER not set."
}
```

---

## Layer 3 — Bank API Activation

When this is active: instead of relying on SMS delivery, the system can query the bank
API directly to verify a specific transfer reference. Stronger than SMS — works even
if the SMS was delayed or delivered to the wrong phone.

**Setup time: 2-4 weeks (formal bank application process).**

This layer adds `POST /finance/bank/verify` for managers. It doesn't replace Layer 1
or Layer 2 — it adds on top. All three layers can be active simultaneously.

### Option A: Equity Bank Jenga API

1. Sign up at **https://developer.equitybankgroup.com** (free, instant sandbox access)
2. Create an app, copy **Consumer Key** and **Consumer Secret**
3. Note your **Merchant Code** from the portal

Set env vars:
```bash
BANK_PROVIDER=equity
BANK_API_KEY=<any value — placeholder for is_api_configured() check>
BANK_EQUITY_API_BASE=https://sandbox.equitybankgroup.com   # or prod URL
BANK_EQUITY_API_KEY=<Consumer Key from portal>
BANK_EQUITY_MERCHANT_CODE=<Merchant Code from portal>
```

⚠️ Before going to production with Equity, verify the exact API endpoint and response
field names against the live Jenga v3 docs — the code has `# TODO` markers at those
points in `app/finance/bank_transfer.py::_verify_equity`.

### Option B: KCB Open Banking

1. Apply at **https://developer.kcbgroup.com** (requires formal business application)
2. Wait for KCB approval (2-4 weeks)
3. Receive **Client ID** and **Client Secret** via email

Set env vars:
```bash
BANK_PROVIDER=kcb
BANK_API_KEY=<any value — placeholder>
BANK_KCB_API_BASE=https://uat.buni.kcbgroup.com   # sandbox; prod URL from KCB docs
BANK_KCB_CLIENT_ID=<Client ID from KCB>
BANK_KCB_CLIENT_SECRET=<Client Secret from KCB>
```

⚠️ KCB uses OAuth2 token auth. Verify the OAuth endpoint path and the transaction query
endpoint against KCB's production docs — `# TODO` markers in `_verify_kcb`.

### Option C: Co-op Bank Mobicash

1. Apply at **https://developer.co-opbank.co.ke**
2. Receive **Consumer Key** and **Consumer Secret**

Set env vars:
```bash
BANK_PROVIDER=coop
BANK_API_KEY=<any value — placeholder>
BANK_COOP_API_BASE=https://developer.co-opbank.co.ke:8243   # sandbox; prod URL from Co-op docs
BANK_COOP_USERNAME=<Consumer Key from Co-op portal>
BANK_COOP_PASSWORD=<Consumer Secret from Co-op portal>
```

⚠️ Co-op may use OAuth instead of Basic auth — verify auth mechanism and endpoint
against their production docs before go-live. `# TODO` markers in `_verify_coop`.

### Testing Layer 3

```bash
# Confirm the socket sees the provider
GET /finance/bank/status
# Expected:
{
  "sms_configured": true,   # if Layer 2 also active
  "api_configured": true,
  "provider": "equity",
  "message": "Bank socket fully active: SMS forwarder active. Bank API configured for provider: equity."
}

# Trigger a manual verification (manager auth required)
POST /finance/bank/verify
Authorization: Bearer <manager-token>
{
  "amount": 50000,
  "bank_ref": "EQTREF123456",
  "account_number": ""
}
# Success → {"provider": "equity", "verified_at": "...", "details": {...}}
# Failure → {"error": "Amount mismatch: expected 50000, bank confirms 45000."}
```

---

## Verification Sequence

Run these steps in order after activating each layer:

1. **Confirm Layer 1 is working:** Record a test bank transfer manually via the API.
   Hit `GET /finance/bank/pending` — it should appear. Reconcile it. Done.

2. **Confirm Layer 2 (SMS forwarder):** Send a test curl with a valid Equity SMS body
   (see Layer 2 → Step 4 above). Check that a Payment row with `method=BANK_TRANSFER`
   was created. Check `GET /finance/bank/status` shows `sms_configured: true`.

3. **Confirm Layer 3 (bank API):** Hit `GET /finance/bank/status` — `api_configured`
   should be `true` and `provider` should show your bank name. Send a test
   `POST /finance/bank/verify` with a real sandbox transfer reference. Confirm the
   response includes `verified_at` and `confirmed_amount`.

4. **Full end-to-end (Layer 2):** Make a real small bank transfer (KES 10) to the resort
   account. Wait for the bank SMS. Confirm it arrives at `POST /finance/bank/sms-forward`
   in the server logs. Confirm a Payment row was auto-created. Done.

---

## Common Issues

**Webhook secret mismatch (HTTP 401 on sms-forward)**

The `X-Webhook-Secret` header your forwarder app sends doesn't match `BANK_SMS_WEBHOOK_SECRET`.
Double-check both values are identical — no extra spaces, no trailing newline from copy-paste.
Test with the curl command in Layer 2 → Step 4.

**Unrecognized SMS format (logged, no Payment created)**

Check server logs for `payment.bank_sms_unrecognized` entries. The log includes the
first 80 characters of the unrecognized body. Compare against the patterns in
`_BANK_SMS_PATTERNS` in `bank_transfer.py`. Banks occasionally update their SMS format
after core banking upgrades — add a new regex entry when this happens.

**Bank API timeout (HTTP 400 with "timed out" message)**

The bank's API is slow or down. The system times out at 15 seconds per provider.
Fall back to Layer 2 (SMS) or Layer 1 (manual reconciliation). Check the bank's
status page or developer portal for outages. Don't retry in a loop — wait.

**Provider env vars missing (HTTP 503 on /finance/bank/verify)**

`BANK_PROVIDER` and `BANK_API_KEY` are set (so `is_api_configured()` returns True),
but the provider-specific vars (`BANK_EQUITY_API_KEY`, etc.) are missing.
Check `GET /finance/bank/status` — the message will say which env vars are absent.

**SMS forwarder stopped sending**

The Android app may have been killed by the phone's battery optimizer. In Android
Settings → Battery → the forwarder app → disable battery optimization. Some phones
(Xiaomi, Samsung) aggressively kill background apps; check the app's docs for
the specific workaround for your phone model.

**Transfer landed in "pending" instead of auto-matching**

This happens when Layer 2 was active but the SMS arrived while the server was restarting,
or when the bank SMS format changed. The payment is in the system — just unreconciled.
Hit `GET /finance/bank/pending` and manually reconcile it via `POST /finance/bank/reconcile`.
Then investigate why the auto-match didn't happen (check logs).
