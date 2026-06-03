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

## Step 3 — TLS / HTTPS on the LAN

**Why self-signed is the right call here:**
The system is LAN-only with no internet exposure. There is no man-in-the-middle threat from outside
the building. A malicious device _on_ the LAN is a much larger physical security problem that TLS
alone cannot solve. Self-signed certificates give encryption in transit at zero cost and zero
renewal overhead — the correct trade-off for a private hotel network.

### Generate the certificate

```bash
sudo mkdir -p /etc/ssl/kurahia
sudo openssl req -x509 -newkey rsa:4096 \
    -keyout /etc/ssl/kurahia/key.pem \
    -out    /etc/ssl/kurahia/cert.pem \
    -days 3650 -nodes \
    -subj "/CN=kurahia-server.local"
```

10-year expiry (`-days 3650`) is intentional — there is no certificate authority involved, so
there is no reason to renew yearly. Regenerate only if the server hostname changes or the key
is compromised.

### File permissions

```bash
sudo chmod 644 /etc/ssl/kurahia/cert.pem   # world-readable is fine
sudo chmod 600 /etc/ssl/kurahia/key.pem    # private key: nginx user only
sudo chown root:www-data /etc/ssl/kurahia/key.pem
```

### First-connect warning — brief all staff before go-live

On the first connection from any tablet or phone, the browser will show
**"Your connection is not private"** (Chrome) or **"Warning: Potential Security Risk"** (Firefox).
This is expected — the certificate is self-signed, not issued by a public authority.
Staff tap **Advanced → Proceed to kurahia-server.local**. The warning never appears again on
that device. Brief every staff member on day one so this doesn't cause panic.

### Nginx config (`/etc/nginx/sites-available/kurahia`)

```nginx
server {
    listen 443 ssl;
    server_name kurahia-server.local;

    ssl_certificate     /etc/ssl/kurahia/cert.pem;
    ssl_certificate_key /etc/ssl/kurahia/key.pem;

    # Allow receipt photos and profile images up to 10 MB
    client_max_body_size 10M;

    location / {
        proxy_pass         http://localhost:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name kurahia-server.local;
    return 301 https://$host$request_uri;
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/kurahia /etc/nginx/sites-enabled/
sudo nginx -t            # confirm config is valid before reloading
sudo systemctl reload nginx
```

### Tailscale + TLS

For owner remote access via Tailscale, TLS is not strictly required — Tailscale provides
end-to-end encryption over its own WireGuard tunnel. However, keeping HTTPS on means the owner
sees the same URL (`https://kurahia-server.local`) whether on the hotel LAN or connecting
remotely via Tailscale. Consistent URL, no special case for remote access.

## Step 4 — Run with Waitress (production WSGI)
```bash
pip install waitress
waitress-serve --host 127.0.0.1 --port 5000 "run:app"
# Or use gunicorn: gunicorn -w 4 "run:app"
```

## Step 5 — Scheduled jobs (cron)

All times in 24h **Africa/Nairobi**. Install path: `/opt/kurahia`.
Failures write to stderr → captured by system cron log (`/var/log/syslog`).
No silent failures: each command exits non-zero on error, which cron mails to the system user.

```cron
# Kurahia cron entries — install on hotel server
# All times in 24h Africa/Nairobi.

# 22:30 — EOD gate sweep: forfeit ACTIVE bands, run gate judge signals.
# Fail: bands stay ACTIVE overnight; gate revenue reconciliation will show mismatch next morning.
30 22 * * *   cd /opt/kurahia && /opt/kurahia/.venv/bin/flask gate close-day

# 23:00 — Mark past-check-in bookings as NO_SHOW.
# Fail: no-shows stay as HELD; owner won't see them in no-show report until next run.
0 23 * * *    cd /opt/kurahia && /opt/kurahia/.venv/bin/flask bookings flag-no-shows

# 00:00 — Dispatch all QUEUED notifications past their scheduled send time.
# Fail: staff notifications delayed until next run; idempotent so re-running is safe.
0 0 * * *     cd /opt/kurahia && /opt/kurahia/.venv/bin/flask events deliver-due

# 00:05 — Spoilage spike + watch-list check; writes JudgeAlerts to dashboard.
# Fail: no alerts generated for that day; silent theft detection has a gap.
5 0 * * *     cd /opt/kurahia && /opt/kurahia/.venv/bin/flask judge run-daily

# 00:10 — Flag IN_PROGRESS events that ran past their end time.
# Fail: stale events stay IN_PROGRESS; planner view shows them as active incorrectly.
10 0 * * *    cd /opt/kurahia && /opt/kurahia/.venv/bin/flask events flag-incomplete

# 03:00 — Backup: SQLite copy or pg_dump to /opt/kurahia/backups/.
# Fail: no backup written for that day; previous backup still intact.
0 3 * * *     cd /opt/kurahia && /opt/kurahia/.venv/bin/flask system backup
```

### How to install these cron entries

```bash
sudo -u kurahia crontab -e   # opens editor; paste the entries above
sudo -u kurahia crontab -l   # verify they're saved
sudo systemctl status cron   # confirm cron daemon is running
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

> **Note:** M-Pesa, WhatsApp, and SMS are stub implementations that return `UNCONFIGURED`. Activation requires writing real API code, not just adding credentials — see `app/finance/mpesa.py` and `app/services/notifications/`. Variable names are documented in `.env.production.example` as a planning reference only.
