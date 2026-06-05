# M-Pesa Daraja Sandbox Testing Runbook

> Use this before any production credentials arrive. Sandbox lets you run the full
> STK Push and callback flow with fake money. Nothing real moves. Prove it works here first.

---

## Section A — Getting Sandbox Credentials

1. Go to **https://developer.safaricom.co.ke** and create a free account.
2. Click **My Apps → Add a New App**. Give it any name (e.g. "Kurahia Test").
   Select both **Lipa Na M-Pesa Sandbox** and **M-Pesa Sandbox** APIs.
3. Once the app is created, open it. You'll see:
   - **Consumer Key** — copy this.
   - **Consumer Secret** — copy this.
4. On the left sidebar, click **Test Credentials**. Safaricom shows you:
   - **Lipa Na M-Pesa Online Shortcode**: `174379` (this is Safaricom's sandbox shortcode — it's the same for everyone in sandbox)
   - **Lipa Na M-Pesa Online Passkey**: a long string — copy this (needed for STK Push password generation)
5. **Test phone number**: Use `254708374149` for sandbox STK Push tests. This number
   always receives the sandbox PIN prompt and auto-approves. It's not a real phone —
   it's Safaricom's sandbox simulator.

That's everything you need. No approval process for sandbox. Access is instant.

---

## Section B — Setting Env Vars for Sandbox

Create or update your `.env` file (not `.env.production` — that's for real keys):

```bash
# M-Pesa Daraja — SANDBOX ONLY
MPESA_CONSUMER_KEY=<paste your Consumer Key from the portal>
MPESA_CONSUMER_SECRET=<paste your Consumer Secret from the portal>
MPESA_SHORTCODE=174379
MPESA_PASSKEY=<paste your Lipa Na M-Pesa Online Passkey from Test Credentials>
MPESA_CALLBACK_URL=https://<your-tunnel-subdomain>.trycloudflare.com/finance/mpesa/callback
MPESA_ENV=sandbox
```

**Which values are constants vs from the portal:**

| Variable | Where it comes from |
|---|---|
| `MPESA_CONSUMER_KEY` | Daraja portal — your app's credentials |
| `MPESA_CONSUMER_SECRET` | Daraja portal — your app's credentials |
| `MPESA_SHORTCODE` | Always `174379` in sandbox |
| `MPESA_PASSKEY` | Daraja portal → Test Credentials |
| `MPESA_CALLBACK_URL` | Your tunnel URL (see Section C) + `/finance/mpesa/callback` |
| `MPESA_ENV` | Always `sandbox` here — change to `production` only after all tests pass |

**Critical:** `MPESA_ENV=sandbox` routes all API calls to `https://sandbox.safaricom.co.ke`.
No real money. Never set this to `production` until you're ready to go live.

---

## Section C — Exposing the Callback URL

Safaricom's servers call your `/finance/mpesa/callback` endpoint from the internet.
Your dev machine is on a private network. You need a public HTTPS URL that tunnels
to your local server.

### Option 1: Cloudflare Tunnel (Recommended — free, no account needed for quick test)

```bash
# One-time: download cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
     -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Start a temporary public tunnel to your Flask dev server
cloudflared tunnel --url http://localhost:5000
```

Cloudflare prints a URL like `https://random-words-here.trycloudflare.com`.
That's your public URL. Set `MPESA_CALLBACK_URL` to that URL + `/finance/mpesa/callback`.

**Note:** This URL changes every time you restart the tunnel. Update `MPESA_CALLBACK_URL`
in your `.env` each time. That's fine for testing — just restart Flask after updating.

For a **permanent URL** (needed for production), create a Cloudflare account and use
a named tunnel with a fixed domain:

```bash
cloudflared tunnel login
cloudflared tunnel create kurahia-dev
cloudflared tunnel route dns kurahia-dev mpesa-dev.yourdomain.com
# Then run: cloudflared tunnel run kurahia-dev
```

### Option 2: VPS Relay (more setup, more stable)

Rent a $5/month VPS (DigitalOcean, Hetzner, or Contabo Kenya).
SSH reverse tunnel from your laptop to the VPS:

```bash
# On your laptop — forwards VPS port 8080 to your local Flask server
ssh -R 8080:localhost:5000 user@your-vps-ip -N
```

On the VPS, run nginx to forward port 443 to 8080:

```nginx
location /finance/mpesa/ {
    proxy_pass http://localhost:8080;
}
```

Set `MPESA_CALLBACK_URL=https://your-vps-domain.com/finance/mpesa/callback`.

**Why not ngrok:** ngrok used to be the standard recommendation but its free tier
now rate-limits and changes URLs aggressively. Cloudflare Tunnel is more reliable
for free use and is what you should reach for first.

---

## Section D — The Verification Sequence

Do these steps in order. Each one proves the next layer works.

### Step 1: Confirm the socket is live

```bash
# Start Flask
flask run

# In another terminal — should return {"configured": true}
curl -s -X GET http://localhost:5000/finance/mpesa/status \
  -H "Authorization: Bearer <your-manager-token>" | python3 -m json.tool
```

If `configured` is `false`, the env vars aren't loading. Check that Flask is reading
your `.env` file (python-dotenv must be installed, or export the vars manually).

### Step 2: Start the tunnel

```bash
cloudflared tunnel --url http://localhost:5000
```

Copy the `https://xxxxx.trycloudflare.com` URL. Update `MPESA_CALLBACK_URL` in `.env`.
Restart Flask so it picks up the new URL.

### Step 3: Initiate an STK Push

```bash
curl -s -X POST http://localhost:5000/finance/mpesa/charge \
  -H "Authorization: Bearer <your-manager-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1,
    "phone_number": "254708374149",
    "tab_id": "test-tab-001",
    "payment_id": "test-pay-001"
  }' | python3 -m json.tool
```

Expected response:

```json
{
  "status": "pending",
  "checkout_request_id": "ws_CO_...",
  "customer_message": "Success. Request accepted for processing."
}
```

If you get `{"error": "..."}` instead, the most common causes are:
- Wrong passkey (copied from wrong field on the portal)
- `MPESA_ENV` still not set (defaults to `sandbox` which is correct — but verify)
- OAuth token request failed (check your Consumer Key/Secret)

### Step 4: Watch for the callback

The sandbox simulates the customer "approving" within a few seconds. Watch your Flask
logs. You should see an incoming POST to `/finance/mpesa/callback`.

```
127.0.0.1 - - [04/Jun/2026 22:00:00] "POST /finance/mpesa/callback HTTP/1.1" 200 -
```

If the callback never arrives, the callback URL isn't reachable. Test the URL
directly from your browser (it should be reachable from outside your machine).

### Step 5: Verify the Payment row was created

```bash
flask shell
```

```python
from app.extensions import db
from app.models.payment import Payment
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus

# Get the most recent payment
p = db.session.query(Payment).order_by(Payment.created_at_utc.desc()).first()
print(p.method, p.amount, p.mpesa_code)

# Verify reconciliation was written
recon = db.session.query(PaymentReconciliation).filter_by(payment_id=p.id).first()
print(recon.status, recon.matched, recon.statement_ref)
```

Expected:
- `p.method` → `MPESA`
- `p.mpesa_code` → the sandbox receipt number (e.g. `LGR56ZKPQM`)
- `recon.status` → `MATCHED`
- `recon.matched` → `True`

### Step 6: Verify the audit log entry

```python
from app.models.audit_log import AuditLog

log = db.session.query(AuditLog).filter_by(action="payment.stk_confirmed").order_by(
    AuditLog.created_at_utc.desc()
).first()
print(log.actor, log.action, log.target, log.details)
```

Expected: `actor="daraja"`, receipt number as target, amount in details.

All six steps passing means the socket works end-to-end. You're ready to swap in
production credentials when they arrive.

---

## Section E — Common Sandbox Issues

**Callback URL not reachable**

Safaricom cannot reach your local machine directly. This is the most common issue.
Confirm the tunnel is running and the URL works from a phone or another machine
(not your laptop). Test: `curl https://xxxxx.trycloudflare.com/health` — should
return `{"status": "ok"}`.

**Wrong shortcode or passkey**

In sandbox, the shortcode is always `174379` and the passkey comes from the portal's
**Test Credentials** tab specifically (not the production passkey). Using a production
passkey against the sandbox shortcode will always produce an `Invalid Passkey` error.

**Sandbox phone format**

Always use `254708374149` (or the exact number Safaricom shows in Test Credentials).
Ordinary Kenyan numbers like `0712345678` won't receive sandbox STK prompts —
the sandbox only delivers prompts to its own test phone number.

**STK Push accepted but no callback**

The sandbox callback is not always instant. Wait up to 30 seconds. If still nothing,
the callback URL may have changed (Cloudflare temporary URLs change on tunnel restart).
Update `MPESA_CALLBACK_URL`, restart Flask, and try again.

**`ResultCode: 1` or `ResultCode: 1032` in callback**

These are simulated failures — the sandbox sometimes sends these to test your
error handling. They're expected. Your server should handle them gracefully (no
Payment row created, audit log entry written, 200 returned to Safaricom).
Run the test suite to confirm: `pytest tests/test_mpesa_daraja_callbacks.py -v`.

**"Insecure key length" warning in logs**

This is a JWT warning from the test `SECRET_KEY` being short. It does not affect
M-Pesa functionality. It only appears in development/testing config. Production
secrets are longer and won't trigger it.
