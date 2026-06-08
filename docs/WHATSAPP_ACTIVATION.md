# WhatsApp Socket Activation Runbook

This document covers activating the WhatsApp dormant socket for Waterfront Kurahia.
The socket uses Twilio's WhatsApp Business API. It is dormant until all four env vars are set.

---

## How the socket works

The dispatcher (`app/services/notifications/dispatcher.py`) runs through three delivery paths:

1. **IN_APP** — user is clocked in and on-site → notification lands in their inbox immediately
2. **WhatsApp** — user is off-site → Twilio API call to their registered phone number
3. **SMS fallback** — if WhatsApp fails/dormant → falls back to SMS
4. **FAILED** — if all paths are down → status=FAILED, notes explain why

The WhatsApp socket is dormant when any of the four required env vars are missing. The dispatcher falls through gracefully to SMS/inbox in that state.

---

## Step 1 — Create a Twilio account

1. Go to [https://www.twilio.com/try-twilio](https://www.twilio.com/try-twilio)
2. Sign up for a free account (no credit card required for sandbox)
3. From the Twilio Console dashboard, copy:
   - **Account SID** (starts with `AC...`)
   - **Auth Token** (click to reveal)

---

## Step 2 — Get a WhatsApp sender number

### Sandbox (for testing — free)

1. In the Twilio Console: go to **Messaging → Try it out → Send a WhatsApp message**
2. Note the sandbox number: `+1 415 523 8886`
3. Each test device must "join" the sandbox first by sending a WhatsApp message:
   - Message `join <your-sandbox-code>` to `+1 415 523 8886`
   - The sandbox code is shown in the Twilio Console

### Production (requires Twilio WhatsApp Business approval)

1. Go to **Messaging → Senders → WhatsApp senders**
2. Apply for a WhatsApp Business Account via Twilio
3. Approval takes 2-5 business days (Meta reviews the application)
4. Once approved, you get a dedicated `+254...` or international number

---

## Step 3 — Set environment variables

Add to your `.env` file (never commit this file):

```bash
WHATSAPP_PROVIDER=twilio
WHATSAPP_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_AUTH_TOKEN=your_auth_token_here
WHATSAPP_FROM_NUMBER=+14155238886   # sandbox number, or your production sender
```

For production, use the actual env vars on your server (not `.env`).

---

## Step 4 — Verify the socket is live

```bash
# Check status (manager login required)
curl -H "Authorization: Bearer <token>" http://localhost:5000/notifications/whatsapp/status
# Expected: {"configured": true, "message": "WhatsApp socket configured for provider: twilio."}
```

Or use the Flask test command (add to CLI if not present):

```bash
flask notifications send-whatsapp-test +254712345678
```

---

## Step 5 — Test delivery end-to-end

1. Make sure your personal number has joined the Twilio sandbox (Step 2 above)
2. Create a test notification manually:
   ```bash
   flask events deliver-due
   ```
3. Check your WhatsApp — you should receive the message
4. Check audit log: `flask audit verify-chain` — confirm `notification.in_app` or WhatsApp delivery logged

---

## Phone number formats

The socket accepts any of these Kenyan formats and normalises to E.164:

| Input | Normalised |
|---|---|
| `0712345678` | `+254712345678` |
| `254712345678` | `+254712345678` |
| `+254712345678` | `+254712345678` |

Numbers that don't match return `INVALID_PHONE`. Staff phones must be saved in their HR profile in one of the above formats.

---

## Production hardening checklist

Before going live with the production WhatsApp sender:

- [ ] **Webhook signature verification** — Twilio signs inbound callbacks with `X-Twilio-Signature`. Add `validate_twilio_signature()` to any inbound WhatsApp route (if you add two-way messaging later)
- [ ] **IP allowlisting** — Twilio publishes its IP ranges. Restrict your server firewall to accept callbacks only from Twilio IPs
- [ ] **Message template approval** — WhatsApp Business requires pre-approved message templates for outbound messages to users who haven't messaged you in the last 24 hours. Submit templates via the Twilio Console before go-live
- [ ] **Monitoring** — Set up a Twilio webhook for delivery status updates to track DELIVERED vs UNDELIVERED at the carrier level
- [ ] **Opt-out handling** — Users who reply STOP must be immediately removed from WhatsApp sends. Twilio handles this automatically for approved Business accounts

---

## Troubleshooting

**"WhatsApp socket dormant — missing env vars"**
→ One or more of the four env vars is not set. Run `flask notifications whatsapp status` to see which ones.

**"provider 'X' not supported"**
→ `WHATSAPP_PROVIDER` is set but not `twilio`. Check spelling.

**Twilio error 21211 (Invalid 'To' Phone Number)**
→ The recipient's number is not in E.164 format, or hasn't joined the sandbox. See phone number formats above.

**Twilio error 63016 (Channel could not authenticate the request)**
→ `WHATSAPP_ACCOUNT_SID` or `WHATSAPP_AUTH_TOKEN` is wrong. Copy them fresh from the Twilio Console.
