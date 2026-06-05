# Card Gateway Socket — Activation Runbook

> The card socket has one dormant layer on top of a day-one manual flow.
> Manual entry works immediately. The gateway adds a customer-facing payment URL.
> Activate whichever provider you sign up with — only one can be active at a time.

---

## Manual Card Flow (Active From Day One)

No setup needed. This is how card payments work right now.

### How a cashier records a card payment

Customer taps their card on the physical POS terminal. Terminal prints a receipt:
```
AUTH: 123456   REF: 0042   AMOUNT: KSh 4,200
```

Cashier records the payment:
```bash
POST /tabs/:tab_id/payments
{
  "method": "CARD",
  "amount": "4200",
  "card_ref": "AUTH-123456-REF-0042",
  "idempotency_key": "<uuid>"
}
```

Use the reference exactly as printed on the terminal receipt. Don't use what the
customer says from memory.

### Daily reconciliation for card payments

Card payments show up in the daily totals:
```bash
# Daily card total — compares against physical terminal batch report
GET /finance/card/summary?date=2026-06-05
# Returns: {"card_total": "42000.00", "card_count": 10, ...}
```

To mark individual card payments as MATCHED against the bank statement:
```bash
# /finance/mpesa/reconcile handles both M-Pesa AND CARD — this is intentional
POST /finance/mpesa/reconcile
{
  "entries": [
    {
      "payment_id": "<uuid>",
      "action": "MATCH",
      "statement_ref": "AUTH-123456",
      "notes": "Confirmed on KCB merchant statement 2026-06-05"
    }
  ]
}
```

If the terminal batch total matches your bank statement, you can batch-MATCH all
card payments at once. Flag any that don't appear on the statement.

---

## Provider Activation

Pick one provider. Only one can be active at a time (`CARD_PROVIDER` env var).

### Pesapal (Recommended for Kenya)

Pesapal is the most widely used card gateway in Kenya. Accepts Visa, Mastercard, and
M-Pesa. No minimum transaction volume requirement to onboard.

**Signup and credentials:**

1. Go to **https://www.pesapal.com** → Business → Sign Up
2. Submit business documents (KRA PIN, business registration, bank details)
3. Approval takes 3-5 business days
4. Once approved, log into the **Pesapal Merchant Portal**
5. Go to Settings → API Keys → Generate new consumer key + secret
6. Note your **Merchant ID** (shown on the portal home screen)
7. For sandbox testing: use the Pesapal sandbox portal at **https://cybqa.pesapal.com**

**Register your IPN URL:**

In the Pesapal Merchant Portal → Settings → IPN → Add IPN URL:
```
https://relay.kurahia.com/finance/card/callback
```

Pesapal will send a POST to this URL when a payment completes. The URL must be
publicly reachable (same Cloudflare Tunnel or VPS relay as M-Pesa).

**Set env vars:**
```bash
CARD_PROVIDER=pesapal
CARD_API_KEY=<Consumer Key from Pesapal portal>
CARD_API_SECRET=<Consumer Secret from Pesapal portal>   # needed for OAuth token
CARD_MERCHANT_ID=<Merchant ID / IPN ID from portal>
CARD_IPN_URL=https://relay.kurahia.com/finance/card/callback
CARD_PESAPAL_API_BASE=https://cybqa.pesapal.com/pesapalv3   # sandbox
# Change to: https://pay.pesapal.com/v3  for production
```

**Test with sandbox:**
```bash
# Confirm socket is live
GET /finance/card/status
# Expected: {"configured": true, "provider": "pesapal", ...}

# Trigger a test payment (cashier flow)
POST /finance/card/initiate
Authorization: Bearer <manager-token>
{
  "amount": 1,
  "tab_id": "test-tab-001",
  "payment_id": "test-pay-001",
  "customer_email": "test@sandbox.com"
}
# Returns: {"status": "pending", "payment_url": "https://cybqa.pesapal.com/...", ...}

# Follow the payment_url in a browser → Pesapal sandbox checkout
# Use sandbox test card: 4000000000000002 / any future expiry / any CVV
# After payment, Pesapal POSTs to your IPN URL
```

---

### DPO Group

DPO is a pan-Africa gateway with strong Kenya presence. Accepts Visa, Mastercard,
and Airtel Money. More formal onboarding process than Pesapal.

**Signup:**

1. Go to **https://www.directpay.online** → Get Started
2. Complete merchant application (business documents, bank account)
3. DPO will issue a **Company Token** — this is your primary credential
4. Access sandbox at **https://secure.3gdirectpay.com** (same URL, different token)

**Set env vars:**
```bash
CARD_PROVIDER=dpo
CARD_API_KEY=<any placeholder — DPO uses Company Token, not API key>
CARD_MERCHANT_ID=<any placeholder — DPO uses Company Token>
CARD_IPN_URL=https://relay.kurahia.com/finance/card/callback
CARD_DPO_COMPANY_TOKEN=<Company Token from DPO portal>
CARD_DPO_API_BASE=https://secure.3gdirectpay.com   # same for sandbox + production
```

Note: DPO distinguishes sandbox/production via the Company Token itself, not via
base URL. Use your sandbox Company Token for testing, production token for live.

**Test with sandbox:**
```bash
POST /finance/card/initiate
Authorization: Bearer <manager-token>
{
  "amount": 1,
  "tab_id": "test-tab-001",
  "payment_id": "test-pay-dpo-001",
  "customer_email": "test@example.com"
}
# Returns: {"payment_url": "https://secure.3gdirectpay.com/payv2.php?ID=...", ...}

# Open the payment_url — DPO test card: 5436886269848367 / 08/2025 / 123
```

⚠️ Verify the ServiceType code in `_initiate_dpo()` — the current code uses `3854`.
Check your DPO account's registered service type codes in the portal. Wrong code
causes a "service not found" error on token creation.

---

### Cellulant Tingg

Cellulant's Tingg platform aggregates M-Pesa, Visa, Mastercard, and multiple African
mobile money providers into one checkout. Useful if you want one integration covering
all payment methods for future-proofing.

**Signup:**

1. Go to **https://cellulant.io** → Products → Tingg → Contact Sales
2. Cellulant requires a business relationship before API access (not self-service)
3. Once onboarded, receive Client ID + API Key from the Cellulant developer portal

**Set env vars:**
```bash
CARD_PROVIDER=cellulant
CARD_API_KEY=<API Key from Cellulant portal>
CARD_MERCHANT_ID=<Service Code from Cellulant portal>
CARD_IPN_URL=https://relay.kurahia.com/finance/card/callback
CARD_CELLULANT_API_BASE=https://apis.cellulant.io   # verify from Cellulant docs
CARD_CELLULANT_CLIENT_ID=<Client ID from Cellulant portal>
```

⚠️ Cellulant's Tingg API v3 endpoint paths and auth header format are marked as TODO
in the code — verify against their actual production docs before go-live. The current
implementation uses reasonable placeholders based on publicly available documentation.

---

## Verification Sequence

Run these steps after activating any provider:

### Step 1: Confirm socket sees the provider

```bash
GET /finance/card/status
Authorization: Bearer <manager-token>

# Expected:
{
  "configured": true,
  "provider": "pesapal",
  "message": "Card gateway configured for provider: pesapal."
}
```

If `configured` is `false`, check that all required env vars are set. The message
field names which vars are missing.

### Step 2: Trigger a test payment

```bash
POST /finance/card/initiate
Authorization: Bearer <manager-token>
Content-Type: application/json
{
  "amount": 1,
  "tab_id": "test-tab-001",
  "payment_id": "test-pay-001",
  "customer_email": "test@sandbox.com"
}
```

Expected: HTTP 200 with `payment_url`. If you get 503, the gateway isn't configured.
If you get 400, check the error message — usually a provider-specific env var is missing.

### Step 3: Complete the test payment

Open `payment_url` in a browser. Use the sandbox test card from your provider's docs.
Complete the payment.

### Step 4: Verify the IPN landed

Check server logs for an incoming POST to `/finance/card/callback`. The response
should be HTTP 200 with `{"status": "accepted"}`.

If the IPN doesn't arrive within 30 seconds:
- The callback URL isn't reachable from the internet — check your tunnel is running
- The IPN URL registered in the provider portal doesn't match `CARD_IPN_URL`

### Step 5: Verify the Payment row was created

```bash
flask shell
```
```python
from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus

p = db.session.query(Payment).filter_by(
    method=PaymentMethod.CARD.value
).order_by(Payment.created_at_utc.desc()).first()
print(p.amount, p.card_ref, p.idempotency_key)
# Expected: 1.00 <tracking_id> cardipn-pesapal-<tracking_id>

recon = db.session.query(PaymentReconciliation).filter_by(payment_id=p.id).first()
print(recon.status, recon.matched)
# Expected: MATCHED True
```

All five steps passing = gateway is working end-to-end. Switch `CARD_PESAPAL_API_BASE`
to production URL (or your DPO/Cellulant production credentials) and do one KES 1
live transaction to confirm production routing works.

---

## Common Issues

**IPN not received (payment completed on provider side but no Payment row created)**

Your `CARD_IPN_URL` isn't reachable from the internet. Check:
1. The tunnel is still running: `curl https://relay.kurahia.com/health` → `{"status": "ok"}`
2. The IPN URL you registered in the provider portal exactly matches `CARD_IPN_URL`
3. The provider sent the IPN: check the provider portal's IPN delivery log (Pesapal
   and DPO both have this in their dashboards)

If the IPN was sent but not received, the tunnel may have restarted and changed URL
(for Cloudflare temporary tunnels). Update `CARD_IPN_URL` in `.env`, restart the server,
and update the IPN URL in the provider portal.

**Wrong provider env vars (HTTP 400 on /finance/card/initiate)**

The message will tell you: `"Pesapal env vars missing: CARD_PESAPAL_API_BASE"` etc.
Check `GET /finance/card/status` for a plain-English breakdown of what's missing.

**Auth mismatch / credentials rejected by provider (HTTP 400 or 401 from provider)**

- Pesapal: Consumer Key/Secret mismatch → re-copy from the portal, no extra spaces
- DPO: Company Token wrong → check you're using sandbox token with sandbox base URL
- Cellulant: Client ID or API Key wrong → regenerate from portal

**payment_url not loading in browser (ERR_CONNECTION_REFUSED or 403)**

- Pesapal: You may be using sandbox URL with a production token, or vice versa
- DPO: Transaction token expired (valid for 30 minutes — `PTL=30` in code)
- Cellulant: Service code not enabled for your account — contact Cellulant support

**Sandbox → production switch checklist**

Before going live:
- [ ] `CARD_PESAPAL_API_BASE` changed to `https://pay.pesapal.com/v3`
- [ ] DPO Company Token replaced with production token
- [ ] IPN URL in provider portal updated to production `CARD_IPN_URL`
- [ ] `CARD_IPN_URL` in `.env.production` is the real relay URL, not a dev tunnel
- [ ] Verify endpoint + field names against production API docs (TODO markers in code)
- [ ] Run one KES 1 live transaction per provider before enabling for staff
