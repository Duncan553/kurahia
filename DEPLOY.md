# Deployment Checklist — Kurahia Resort Backend

## Server requirements
- Ubuntu 22.04+ (or any Linux)
- Python 3.12+
- PostgreSQL 14+ (recommended for production; SQLite works for single-server)
- Nginx (reverse proxy + TLS termination)

## Step 1 — Environment
```bash
cp .env.example .env
# Edit: FLASK_ENV=production, strong SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL
```

## Step 2 — Database
```bash
flask db upgrade
flask seed
flask bookings seed-resources
flask events seed-types
flask conduct seed-rules
flask calendar seed-kenya-holidays
```

## Step 3 — TLS (required, even on LAN)
```bash
# Self-signed for LAN:
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
# Or use Let's Encrypt for internet-facing deployments (certbot)
```

Nginx config:
```nginx
server {
    listen 443 ssl;
    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

## Step 4 — Run with Waitress (production WSGI)
```bash
pip install waitress
waitress-serve --host 127.0.0.1 --port 5000 "run:app"
# Or use gunicorn: gunicorn -w 4 "run:app"
```

## Step 5 — Scheduled jobs (cron)
```cron
# Deliver due notifications — every 5 minutes
*/5 * * * * cd /app && flask events deliver-due

# Daily judge analysis — 2 AM
0 2 * * * cd /app && flask judge run-daily

# Weekly ratio analysis — Sunday 3 AM
0 3 * * 0 cd /app && flask judge run-weekly

# EOD gate close — 11 PM
0 23 * * * cd /app && flask gate close-day

# Flag incomplete events — midnight
0 0 * * * cd /app && flask events flag-incomplete

# Sweep actionable alerts — every hour
0 * * * * cd /app && flask system check-alerts

# Audit chain verification — daily 4 AM
0 4 * * * cd /app && flask audit verify-chain

# Backups — daily 3:30 AM
30 3 * * * cd /app && flask system backup --dest /backups/kurahia
```

## Step 6 — Security hardening
- [x] TLS enforced (Nginx)
- [x] Secrets in env, not code (`grep -r "SECRET\|PASSWORD\|KEY" app/ --include="*.py"` should return nothing sensitive)
- [x] JWT short-lived (30 min access / 30 day refresh)
- [x] Login rate limiting via `FAILED_ATTEMPTS_LOCKOUT` / `LOCKOUT_MINUTES` env vars
- [x] Audit log hash-chained — verify daily with `flask audit verify-chain`
- [x] No db.session.delete() on business entities
- [x] OWNER_PRIVATE rows structurally invisible to manager sessions

## Step 7 — Activate dormant sockets
When ready:
1. **M-Pesa**: edit `app/finance/mpesa.py` — implement `initiate_stk_push()` and `verify_payment()`
2. **WhatsApp**: edit `app/services/notifications/whatsapp.py` — implement `send_whatsapp()`
3. **SMS**: edit `app/services/notifications/sms.py` — implement `send_sms()`
4. Seed `NotificationChannelConfig` rows with `is_active=True` for each channel

No other code changes needed — the pipelines are already wired.
