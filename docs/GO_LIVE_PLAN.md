# Go-Live Plan — Everything You Need Before the Hotel Runs on This System

> This is not a code file. This is the real-world checklist.
> Work through it in order. Each section explains what it is, why it matters,
> and exactly what to do.

---

## Where You Stand Right Now

**Code:** Done. 696 tests passing. Both PWAs build clean.
**Reality:** Nothing is on the hotel server yet. No real data. No staff trained.

The gap between "code done" and "hotel running on it" is infrastructure + people.
That's what this document covers.

---

## Step 1 — Get the Hotel Server

### What is a "server"?

A server is just a computer that stays on 24/7 and runs the backend.
It doesn't need to be powerful. It needs to be reliable and always on.

### Your options

**Option A: A mini-PC at the hotel (recommended)**
Buy a small computer — NUC, Beelink, or similar — and plug it into the hotel's
router. Ubuntu 22 LTS as the OS. This is the cheapest long-term option and keeps
all data physically at the hotel.

Cost: ~KSh 15,000–25,000 once.
Risk: If it dies, you need a replacement.

**Option B: A VPS (Virtual Private Server)**
Rent a small cloud server from DigitalOcean, Hetzner, or Linode.
~$6–12/month. Always on, automatic backups, someone else manages the hardware.
Downside: data lives off-site, and you need internet to reach it.

Cost: ~KSh 800–1,500/month.
Risk: If hotel internet dies, owner can't connect remotely (but staff on LAN still can
if you cache the PWA properly via service workers).

**Which to pick:**
For a resort on a LAN with mostly local staff use → Option A.
For an owner who travels and wants remote access without Tailscale complexity → Option B.

### OS Setup (Option A — mini-PC)

```bash
# Download Ubuntu Server 22.04 LTS, flash to USB, install on the mini-PC
# During install: set username to kurahia, pick a strong password
# After install, SSH in from your laptop:
ssh kurahia@<hotel-server-ip>

# Update everything first
sudo apt update && sudo apt upgrade -y

# Install tools you'll need
sudo apt install -y git python3-pip python3-venv curl
```

---

## Step 2 — Set Up Postgres

### What is Postgres and why not SQLite?

SQLite = a database in a single file. One writer at a time. Fine for your laptop.
Postgres = a real database server. Handles 100 simultaneous staff connections.
Survives power loss properly. Has user auth. Built for production.

Your Flask code doesn't change. Only the `DATABASE_URL` in `.env` changes.

### Install and configure

```bash
# Install Postgres
sudo apt install -y postgresql postgresql-contrib

# Start it and set it to auto-start on reboot
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create the database user and database
sudo -u postgres psql << 'EOF'
CREATE USER kurahia WITH PASSWORD 'pick_a_strong_password_here';
CREATE DATABASE kurahia OWNER kurahia;
\q
EOF

# Test the connection works
psql -U kurahia -d kurahia -h localhost -c "SELECT version();"
# Should print the Postgres version. If it connects, you're done.
```

### Why the password matters

The Postgres password protects your entire database.
If it's weak (like "password123"), anyone on the network who finds port 5432
can dump every guest record, every financial transaction, every staff detail.

Pick something like: `Kur@h1a_DB_2026!`
Write it down somewhere physical. You'll need it in the `.env` file.

---

## Step 3 — Deploy the Code

```bash
# On the hotel server:
git clone <your-repo-url> /home/kurahia/app
cd /home/kurahia/app

# Create the Python virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Create the production .env (copy the template, then edit it)
cp .env.production .env
nano .env
```

### What to change in .env

Open the file and change exactly these three things:

```bash
# Change this line — put the Postgres password you chose in Step 2
DATABASE_URL=postgresql://kurahia:pick_a_strong_password_here@localhost:5432/kurahia

# The SECRET_KEY and JWT_SECRET_KEY are already generated in the template.
# Leave them as-is UNLESS you want to generate fresh ones:
# python3 -c "import secrets; print(secrets.token_hex(32))"
```

Everything else in `.env.production` is already correct for production.

### Run migrations and seed

```bash
# This creates all the tables in Postgres from your migration files
.venv/bin/flask db upgrade

# This loads the base data: roles, departments, conduct rules, Kenya holidays
.venv/bin/flask seed run
.venv/bin/flask conduct seed-rules
.venv/bin/flask calendar seed-kenya-holidays
.venv/bin/flask events seed-types

# Confirm it worked — should show tables
psql -U kurahia -d kurahia -h localhost -c "\dt"
```

---

## Step 4 — Set Up HTTPS (SSL)

### Why HTTPS is not optional for PWAs

PWAs (Progressive Web Apps) have three features that require HTTPS:
1. **Service workers** — the file that makes the app work offline. Browsers refuse
   to register a service worker on HTTP. No HTTPS = no offline mode.
2. **Push notifications** — the Web Push API is HTTPS-only.
3. **"Add to Home Screen"** — Chrome and Safari only offer this on HTTPS sites.

Without HTTPS, your apps are just websites. With HTTPS, they install like real apps.

### Option A: Self-signed certificate (hotel LAN only)

Use this if the server has no public domain name — just a local IP like 192.168.1.100.

```bash
# Generate a self-signed certificate (free, lasts 10 years)
sudo mkdir -p /etc/ssl/kurahia
sudo openssl req -x509 -newkey rsa:4096 \
    -keyout /etc/ssl/kurahia/key.pem \
    -out    /etc/ssl/kurahia/cert.pem \
    -days   3650 -nodes \
    -subj "/CN=kurahia-server.local"

# Lock down the private key
sudo chmod 600 /etc/ssl/kurahia/key.pem
```

Downside: browsers will show "Not Secure" warning on first visit.
Staff click "Advanced → Proceed" once, then it's fine forever on that device.

### Option B: Real certificate with Let's Encrypt (if you have a domain name)

If you buy a domain (e.g., `kurahia.co.ke`), you can get a free trusted cert:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d kurahia.co.ke
# Auto-renews every 90 days
```
No browser warnings. Cleaner. Requires a domain + public internet.

### Install and configure Nginx

Nginx is a web server that sits in front of Flask. It handles HTTPS and forwards
requests to Waitress (the Flask production server). Think of it as a receptionist.

```bash
sudo apt install -y nginx

# Create the Nginx config file
sudo nano /etc/nginx/sites-available/kurahia
```

Paste this:
```nginx
server {
    listen 443 ssl;
    server_name kurahia-server.local;   # or your domain

    ssl_certificate     /etc/ssl/kurahia/cert.pem;
    ssl_certificate_key /etc/ssl/kurahia/key.pem;

    # Serve the Employee PWA static files
    location /emp/ {
        alias /home/kurahia/app/employee_pwa/dist/;
        try_files $uri $uri/ /emp/index.html;
    }

    # Serve the Owner PWA static files
    location /own/ {
        alias /home/kurahia/app/owner_pwa/dist/;
        try_files $uri $uri/ /own/index.html;
    }

    # Forward all API calls to Flask/Waitress
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

```bash
# Enable the site and reload Nginx
sudo ln -s /etc/nginx/sites-available/kurahia /etc/nginx/sites-enabled/
sudo nginx -t        # test the config — must say "syntax is ok"
sudo systemctl reload nginx
```

---

## Step 5 — Set Up the Systemd Service

### What is systemd and why do you need it?

Systemd is the process manager built into Linux. It starts services when the
server boots and restarts them if they crash.

Right now, if you run `waitress-serve ...` and close the terminal, the server dies.
If there's a power cut and the server reboots, the backend stays dead until
someone SSHes in and starts it manually.

A systemd service fixes this — Flask starts automatically on boot, always.

### Create the service file

```bash
sudo nano /etc/systemd/system/kurahia.service
```

Paste this:
```ini
[Unit]
Description=Kurahia Resort Backend
After=network.target postgresql.service

[Service]
User=kurahia
WorkingDirectory=/home/kurahia/app
EnvironmentFile=/home/kurahia/app/.env
ExecStart=/home/kurahia/app/.venv/bin/waitress-serve \
    --host=127.0.0.1 \
    --port=5000 \
    "app:create_app()"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Tell systemd about the new service
sudo systemctl daemon-reload

# Start it now
sudo systemctl start kurahia

# Set it to start automatically on every boot
sudo systemctl enable kurahia

# Check it's running
sudo systemctl status kurahia
# Should say: Active: active (running)

# See the live logs
sudo journalctl -u kurahia -f
```

Now the backend survives reboots and crashes automatically.

---

## Step 6 — Copy the VAPID Private Key

### What is VAPID and why is this step easy to forget?

VAPID is how push notifications are authenticated. Your server signs each
notification with a private key so browsers know it came from you.

The private key lives in `instance/private_key.pem`. This file is in `.gitignore`
(correctly — it's a secret). When you cloned the repo in Step 3, this file
**did not come with it**. If you skip this step, push notifications silently fail.

### Copy the key to the server

```bash
# From YOUR LAPTOP (not the server):
scp /home/wachira/kurahia/instance/private_key.pem \
    kurahia@<hotel-server-ip>:/home/kurahia/app/instance/private_key.pem

# Confirm it's there on the server:
ssh kurahia@<hotel-server-ip> "ls -la /home/kurahia/app/instance/"
```

That's it. Push notifications will work.

---

## Step 7 — Set Up Tailscale (Owner Remote Access)

### What is Tailscale?

Tailscale is a private VPN that connects devices as if they're on the same network,
even when they're physically apart. The hotel server and the owner's phone join
a private Tailscale network that only they can see.

Without Tailscale: owner can only use the owner PWA when physically at the hotel.
With Tailscale: owner can check dashboards, approve disputes, view financials from
anywhere in the world.

### Install on the hotel server

```bash
# On the hotel server:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# It prints a URL — open it on any browser and log in with your Google/GitHub account
# The server is now on your Tailscale network
```

### Install on the owner's phone

Download the Tailscale app (iOS/Android). Log in with the same account.
Both devices now appear in your Tailscale dashboard at tailscale.com.

The hotel server gets a stable private IP like `100.x.x.x`. The owner PWA
should be built pointing at that IP — it'll work from anywhere.

---

## Step 8 — Build the PWAs Pointing at the Real Server

Right now the PWAs point at `localhost:5000` (your laptop).
Before deploying, rebuild them pointing at the hotel server.

```bash
# In employee_pwa/.env.production — create this file:
VITE_API_BASE_URL=https://kurahia-server.local

# In owner_pwa/.env.production — create this file:
VITE_API_BASE_URL=https://100.x.x.x   # the Tailscale IP for owner remote access

# Build both PWAs
cd /home/wachira/kurahia/employee_pwa && npm run build
cd /home/wachira/kurahia/owner_pwa && npm run build

# Copy the built files to the server
scp -r employee_pwa/dist kurahia@<hotel-server-ip>:/home/kurahia/app/employee_pwa/
scp -r owner_pwa/dist kurahia@<hotel-server-ip>:/home/kurahia/app/owner_pwa/
```

---

## Step 9 — Load the Real Hotel Data

The seed commands in Step 3 loaded generic test data.
Now replace it with the real hotel's actual data.

### What needs to be real before go-live

**Menu items** — every food and drink item, real KSh prices, real categories.
Use the manager panel in the owner PWA to add them, OR write a one-time seed
script. Categories must match exactly how the kitchen/bar thinks about them.

**Resources** — jet ski, kayak, boat, spa treatment room, etc.
```bash
flask bookings seed-resources   # loads the defaults — then edit in owner PWA
```

**Staff accounts** — every member of staff who will use the system.
Owner creates accounts in the owner PWA:
- Real names as usernames (or employee numbers)
- Correct department and role
- Temporary password → staff sets their own PIN on first login

**Rooms/Villas** — actual villa names and numbers for check-in/check-out.

**Conduct rules** — already seeded, but review them. Do they match your actual
HR policy? Edit in owner PWA if needed.

---

## Step 10 — Test the Backup and Restore

### Why this step is non-negotiable

A backup you have never restored from is not a backup. It's a file you hope works.
You find out it doesn't work the day you actually need it — which is already a disaster.

Test before go-live. Test takes 10 minutes.

```bash
# On the hotel server — create a backup
flask system backup
# Prints something like: Backup saved to instance/backups/kurahia_2026-06-25.dump

# Simulate a disaster: create a test database and restore into it
sudo -u postgres psql -c "CREATE DATABASE kurahia_restore_test OWNER kurahia;"
pg_restore -U kurahia -d kurahia_restore_test instance/backups/kurahia_2026-06-25.dump

# Verify the restore has data
psql -U kurahia -d kurahia_restore_test -c "SELECT COUNT(*) FROM users;"
# Should match the count in the real DB

# Clean up the test database
sudo -u postgres psql -c "DROP DATABASE kurahia_restore_test;"
```

If that worked: you know your backup works. Sleep well.
If it failed: fix it now, not during an actual crisis.

### Automate backups

```bash
# Run backups every day at 2 AM automatically
crontab -e
# Add this line:
0 2 * * * cd /home/kurahia/app && .venv/bin/flask system backup
```

---

## Step 11 — Train the Staff (30 Minutes, Not a Document)

The most common reason a system fails at launch is not bugs. It's people.

Don't send staff a PDF. Sit with them. Show them once. Let them try it.

### Session per role (30 min each)

**Waiters** (biggest group — train first)
- How to log in with PIN on the tablet
- How to open a tab
- How to place an order
- How to charge to a band tab vs. direct payment
- How to log an incident

**Kitchen**
- The kitchen queue screen
- How to mark a ticket done
- What the different colours mean (pending, in-progress, done)

**Front desk**
- Check-in and check-out flow
- How to look up a guest
- How to handle a booking

**Gate**
- Issuing a wristband
- Band lookup
- What the credit ceiling means and what to say to a guest who hits it

**Manager**
- How to create staff accounts
- How to reset a PIN
- How to view disputes and incidents
- How to read the dashboard

---

## Step 12 — Shadow Week

### What is a shadow week?

You run the new system **in parallel** with whatever the hotel uses now (paper,
spreadsheets, the old POS, whatever) for one full week.

Staff use the new system. But the old system is the fallback if anything breaks.

### Why it matters

You will find bugs during shadow week that no test can catch:
- The kitchen tablet loses Wi-Fi during lunch rush
- A waiter accidentally opens two tabs for the same guest
- A shift handoff edge case nobody thought of
- The wristband printer jams at the gate

These are real-world failures. You want to find them during shadow week, not on
a fully live Saturday with 200 guests.

### How to run it

Pick a regular week — not a holiday, not an event. Tell staff: "Use the new
system for everything. If something goes wrong, we have the old system as backup.
Tell us every problem you hit, no matter how small."

Collect every complaint. Fix what you can overnight. By day 5 you'll know
if the system is ready.

---

## Step 13 — M-Pesa (When Ready)

The M-Pesa socket is already built. It's dormant — does nothing until you
fill in the env vars. When you're ready:

1. Register a Safaricom Business account
2. Apply for Daraja API access at developer.safaricom.co.ke
3. Get sandbox credentials → test with `docs/MPESA_SANDBOX_TESTING.md`
4. Go live: fill in the real credentials in `.env` and restart the service

```bash
# After adding M-Pesa credentials to .env:
sudo systemctl restart kurahia

# Verify the socket is active:
curl https://kurahia-server.local/finance/mpesa/status
# Should return: {"configured": true, "message": "..."}
```

---

## The Full Order

```
PHASE 1 — Infrastructure (1–2 days)
  □ Get hotel server (mini-PC or VPS)
  □ Install Ubuntu 22 LTS
  □ Install and configure Postgres
  □ Clone repo, set up .env, run migrations
  □ Install Nginx + HTTPS
  □ Set up systemd service (auto-start on boot)
  □ Copy VAPID private key from laptop to server
  □ Install Tailscale on server + owner phone
  □ Build PWAs pointing at hotel server
  □ Test: open employee PWA on a phone → should install as an app

PHASE 2 — Real Data (half day)
  □ Add all real menu items + prices
  □ Add all resources (jet ski, spa, etc.)
  □ Add all rooms/villas
  □ Create all staff accounts with correct roles/departments

PHASE 3 — Reliability Check (1 hour)
  □ Run backup + restore test (Step 10)
  □ Reboot the server → confirm Flask auto-restarts via systemd
  □ Simulate a kill switch: deactivate a test account → confirm instant lockout

PHASE 4 — People (1–2 days)
  □ Train waiters
  □ Train kitchen
  □ Train front desk
  □ Train gate
  □ Train manager

PHASE 5 — Shadow Week (5–7 days)
  □ Run parallel with old system for one full week
  □ Fix every bug found overnight
  □ At end of week: decide if ready to go fully live

PHASE 6 — Go Live
  □ Decommission old system
  □ All staff using new system only
  □ Monitor for 48 hours (check logs: sudo journalctl -u kurahia -f)

PHASE 7 — Payments (when business account is ready)
  □ Get Safaricom Daraja API credentials
  □ Test on sandbox
  □ Activate M-Pesa socket
```

---

## Quick Reference — Server Commands You'll Use Often

```bash
# Check if Flask is running
sudo systemctl status kurahia

# Restart Flask (after a code update or .env change)
sudo systemctl restart kurahia

# Watch live logs
sudo journalctl -u kurahia -f

# Pull new code and restart
cd /home/kurahia/app && git pull && sudo systemctl restart kurahia

# Run migrations after a code update that has schema changes
cd /home/kurahia/app && .venv/bin/flask db upgrade

# Manual backup
cd /home/kurahia/app && .venv/bin/flask system backup

# Check Nginx is running
sudo systemctl status nginx

# Reload Nginx after config change (no downtime)
sudo systemctl reload nginx
```

---

*The code is done. This document is everything between the code and the hotel
actually running on it. Work through it in order.*
