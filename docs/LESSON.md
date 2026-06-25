# Kurahia — How the Whole System Works

> Read this top to bottom once. By the end you should be able to explain every part
> of this system in an interview without guessing.

---

## 1. The Big Picture

You built a **resort management platform**. It's the nervous system of the hotel.
Every department — kitchen, bar, front desk, gate, housekeeping — runs through it.

There are **three separate codebases** all working together:

```
┌──────────────────────────────────────────────────────────┐
│                      HOTEL LAN (Wi-Fi)                   │
│                                                          │
│   Employee PWA              Owner PWA                    │
│   (port 5173)               (port 5174)                  │
│   Staff phones &            Owner's phone                │
│   department tablets        anywhere via Tailscale VPN   │
│         │                        │                       │
│         └────────────┬───────────┘                       │
│                      │  JSON over HTTP                   │
│                      ▼                                   │
│             Flask Backend (port 5000)                    │
│             ├── SQLite  (your laptop, dev only)          │
│             └── Postgres (hotel server, production)      │
└──────────────────────────────────────────────────────────┘
```

The two PWAs are the **face** — what staff and the owner see and tap.
The Flask backend is the **brain** — every rule, every money calculation, every
permission check lives here.
The database is the **memory** — nothing is ever lost.

---

## 2. The Backend (Flask)

Location: `/home/wachira/kurahia`

Flask is a Python web framework. It listens for HTTP requests and returns JSON.
That's it. The PWAs talk to it the same way your browser talks to any website —
they send a request, get a response.

### What happens when a waiter places a food order

```
1. Waiter taps "Send Order" on their tablet
2. PWA sends: POST /orders  (with their JWT token in the header)
3. Flask receives it
4. Reads the JWT → gets the user ID
5. Re-fetches that user from the DB → confirms they're still active (kill switch)
6. Checks role level ≥ 1 (waiter = level 1 → passes)
7. Creates the order rows in the DB
8. Writes an audit log entry (who did what, when)
9. Returns HTTP 201 + the new order as JSON
10. Kitchen screen polling /queue/kitchen sees the new ticket appear
```

Every single request goes through steps 3-7. Even if someone steals a token,
the moment that user's account is deactivated in the DB, the next request from
that token gets a 401 and they're logged out. JWT alone is never trusted.

### Role levels

```
owner        = 10   → sees everything, can do anything
manager      = 5    → sees everything except owner-private data
head_chef    = 3    (department: kitchen)
bar_lead     = 3    (department: bar)
front_desk   = 3    (department: front desk)
gate_lead    = 3    (department: gate)
spa          = 2
water        = 2
waiter       = 1
housekeeping = 1
grounds      = 1
```

These numbers are checked in `AppLayout.tsx` (what nav items render) AND in the
backend route (what data is returned). Both layers check. If someone bypassed the
frontend and typed `/manager` directly in the URL, the API would still 403 them.

### The 3 money rules — never break these

**Rule 1: Append-only ledgers**
Money is never edited. Every charge is a new row. Every payment is a new row.
Tab balance = SUM(all charges) − SUM(all payments). Always derivable. Never lies.

```python
# WRONG — editing in place
tab.balance -= 500

# RIGHT — appending a new fact
db.session.add(TabCharge(tab_id=tab.id, amount=500, ...))
```

**Rule 2: Decimal, never float**
```python
# WRONG — float loses cents
0.1 + 0.2 = 0.30000000000000004   # Python REPL, try it

# RIGHT — Decimal is exact
from decimal import Decimal
Decimal("0.1") + Decimal("0.2") = Decimal("0.3")   # exact
```
Every KSh amount in this codebase is `Decimal` from the DB column to the JSON response.

**Rule 3: Idempotency keys**
Every write request (create order, charge tab, make payment) sends a UUID called
an `idempotency_key`. If the network drops and the PWA retries the same request,
the backend recognises the key and returns the original result — no duplicate charge.
Enforced twice: app-level check AND a DB UNIQUE constraint as a safety net.

---

## 3. The Employee PWA

Location: `/home/wachira/kurahia/employee_pwa`

React + Vite. Installed as a PWA on staff phones and department tablets.

### Two types of devices

**Personal phones** (waiter, housekeeping, etc.)
Sees personal nav: schedule, leave, payslips, incidents, calendar, disputes.

**Shared tablets** (kitchen, bar, spa, gate)
Sees only the department screen: kitchen queue, kiosk, band lookup.
No personal chrome — these tablets are shared between staff on different shifts,
so personal items would show the wrong person's data.

The rule that decides this is in `AppLayout.tsx`:
```ts
// personal = true if level ≥ 3 OR if the dept is not a shared station
const personal = (level, dept) => level >= 3 || !isStation(dept)
```

### Screens and who sees them

| Screen | Who | What |
|---|---|---|
| POS / Kiosk | Waiters | Place food/drink orders, open tabs |
| Kitchen Queue | Kitchen tablet | See tickets, mark done |
| Bar Queue | Bar tablet | Same for drinks |
| Check-In | Front desk | Guest check-in/check-out |
| Gate Hub | Gate | Issue wristbands |
| Band Lookup | Gate / Front desk | Find a guest by wristband |
| Villa | Housekeeping / Front desk | Room status |
| Schedule / Leave / Absence | All personal | HR self-service |
| Incidents | All personal | Log accidents and safety issues |
| Calendar | All personal | Shifts and events |
| Manager Panel | Manager | Staff, disputes, inventory alerts |

---

## 4. The Owner PWA

Location: `/home/wachira/kurahia/owner_pwa`

One person uses this — the hotel owner. Accessible remotely via **Tailscale**.

**What is Tailscale?** It's a private VPN. The owner's phone and the hotel server
both install Tailscale. Tailscale gives them a private network that only they can
see — even if the owner is in Nairobi, their phone connects to the hotel server
as if they're sitting in the same room on the same Wi-Fi.

The owner sees: revenue dashboards, full audit logs, staff management, dispute
resolution, judge engine results (the theft detection system), and financial reports.

---

## 5. Shared UI

Location: `/home/wachira/kurahia/shared_ui`

Both PWAs import components from here. Design tokens (colours, spacing, fonts),
and reusable components: `Button`, `Modal`, `ErrorBoundary`, `Toast`, etc.

This is why both apps look identical — they literally share the same source files.

---

## 6. The Security Architecture

### Login flow — full picture

```
Staff types password
→ POST /auth/login
→ Backend: Argon2 hashes the typed password and compares to stored hash
  (Argon2 is deliberately slow — takes ~200ms — so brute force would take centuries)
→ Returns: access_token (expires in 30 min) + refresh_token (expires in 7 days)
→ Stored in: sessionStorage (wiped automatically when browser tab closes)
```

### Token refresh — why it's invisible to staff

```
access_token expires (30 min)
→ Next API call gets 401
→ axios interceptor catches it before the screen sees it
→ Sends refresh_token to /auth/refresh
→ Gets a new access_token
→ Retries the original request
→ Staff sees nothing — request just works
```

If the refresh token is also expired (7 days), they get sent to the login screen.

### PIN login — for shared tablets

Staff don't type their full password on a shared tablet (next person's shift would
see it). Instead:
- Staff sets a 6-digit PIN on their own phone once
- PIN is Argon2-hashed, stored separately from password
- On the shared tablet: type employee number + PIN → logged in
- Rate limited: 5 wrong PINs per minute → locked out

### Kill switch — instant account lockout

```
Owner goes to Manager Panel → deactivates an account → is_active = False in DB

Next API request from that account:
→ require_active_user decorator re-fetches User from DB
→ Sees is_active = False
→ Returns 401
→ axios interceptor clears the session → redirects to /login

Time to lockout: < 1 second from the moment owner clicks deactivate
```

No need to wait for the token to expire. It's instant.

### Band tab credit ceiling

```
Guest arrives → pays KSh 3,000 entry fee → gets wristband
Guest charges food/drinks freely throughout the day
When total charges reach KSh 6,000 (2× entry fee):
→ check_band_credit() blocks further charges
→ Staff gets plain-English error: "Band credit ceiling reached — collect payment first"
→ Guest pays down the balance → charges resume
```

---

## 7. SQLite vs Postgres — What's the Difference

### SQLite (development — your laptop)

SQLite is a database that lives in **a single file**: `instance/dev.db`.
No server needed. No installation. Just a file Python reads directly.

```
your code → reads/writes → dev.db (a file on disk)
```

Perfect for development: zero setup, fast, works offline.
**Not for production** because:
- Only one writer at a time (would crash with multiple staff simultaneously)
- No user access control (anyone with the file can read everything)
- File corruption risk on power loss

### Postgres (production — hotel server)

Postgres is a full database **server**. It runs as a separate process, listens on
port 5432, handles hundreds of simultaneous connections, has built-in user auth,
and writes to disk in a way that survives power loss.

```
your code → TCP connection → Postgres server process → hotel_db (managed storage)
```

**Flask talks to both using the exact same SQLAlchemy code.** The only thing that
changes is the `DATABASE_URL` environment variable.

```bash
# SQLite (dev) — Flask figures this out automatically with no DATABASE_URL set
sqlite:///instance/dev.db

# Postgres (prod) — set this in .env
postgresql://kurahia:mypassword@localhost:5432/kurahia
#              ↑user  ↑password  ↑host    ↑port ↑database name
```

SQLAlchemy reads that URL and knows which driver to use. Your actual Python models,
queries, and migration files don't change at all between dev and prod.

### Setting up Postgres on the hotel server

```bash
# 1. Install Postgres
sudo apt install postgresql postgresql-contrib

# 2. Create a database user and database
sudo -u postgres psql
CREATE USER kurahia WITH PASSWORD 'a_strong_password_here';
CREATE DATABASE kurahia OWNER kurahia;
\q

# 3. Set the DATABASE_URL in .env
DATABASE_URL=postgresql://kurahia:a_strong_password_here@localhost:5432/kurahia

# 4. Run migrations (creates all tables)
flask db upgrade

# 5. Seed initial data (roles, departments, menu items)
flask seed run
```

That's it. Flask connects, creates all the tables from your migration files,
and the app runs on Postgres exactly as it ran on SQLite.

---

## 8. The .env File — What Every Line Does

The `.env` file is a plain text file that holds **secrets and config that should
never be in the code**. Flask reads it on startup. The file is in `.gitignore`
so it never gets committed to git.

Here is `.env.production` with every line explained:

```bash
# ── Environment ──────────────────────────────────────────────────────────────

FLASK_ENV=production
# Tells Flask which config class to use (config.py has development/testing/production).
# In production: debug mode OFF, strict error handling, JSON logging.
# NEVER run with FLASK_ENV=development on the hotel server.

FLASK_APP=app
# Tells the `flask` CLI where your app factory is.
# app = the /app folder → finds create_app() in app/__init__.py


# ── Secret Keys ───────────────────────────────────────────────────────────────

SECRET_KEY=c917ad2122100c2e47ca50b0703c4072ff1b08b6e889f7689e15282e9a0aac77
# Used by Flask to sign session cookies and security tokens.
# If someone learns this key, they can forge sessions and impersonate any user.
# Must be: long (32+ bytes), random, never the same as the dev key.
# Generated with: python3 -c "import secrets; print(secrets.token_hex(32))"

JWT_SECRET_KEY=5ccc8b88c272d64f4b12e099fbf4a4fb4070a4730d3c1d94bed1e33b01510888
# Used to sign every JWT access token and refresh token.
# A JWT looks like: eyJhbGci...eyJ1c2Vy...SflKxw
# The third part (after the last dot) is a cryptographic signature made with this key.
# When Flask receives a token, it verifies the signature. If the key is wrong → rejected.
# If someone learns this key, they can mint fake tokens and log in as any user.
# Must be: different from SECRET_KEY, 32+ random bytes, never committed to git.


# ── Database ──────────────────────────────────────────────────────────────────

DATABASE_URL=postgresql://kurahia:CHANGE_PASSWORD@localhost:5432/kurahia
# Format:  postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
#
# postgresql://  → tells SQLAlchemy to use the psycopg2 Postgres driver
# kurahia        → the Postgres user you created (step 2 above)
# CHANGE_PASSWORD→ the password for that user — change this to something strong
# localhost      → Postgres is on the same machine as Flask (most common)
# 5432           → Postgres default port
# kurahia        → the database name you created
#
# If Postgres is on a different machine (rare):
# DATABASE_URL=postgresql://kurahia:pass@192.168.1.50:5432/kurahia


# ── Auth Policy ───────────────────────────────────────────────────────────────

FAILED_ATTEMPTS_LOCKOUT=5
# How many wrong passwords before the account is locked.

LOCKOUT_MINUTES=15
# How long the lockout lasts.

BUSINESS_DAY_START_HOUR=6
# Used by shift and attendance calculations. 6 = business day starts at 6 AM.


# ── Web Push Notifications (VAPID) ───────────────────────────────────────────

VAPID_PRIVATE_KEY=instance/private_key.pem
# Path to the private key file used to sign push notification messages.
# Kept in the instance/ folder (not committed to git).
# Generated once when you set up notifications — never regenerate in prod
# because the public key is baked into the installed PWAs.

VAPID_PUBLIC_KEY=BAZtayY69rs32BUE5TWB1gaNi_tIYtdsPLjCWasqc-...
# The matching public key — baked into the PWA build at compile time.
# Browsers use this to verify that push messages came from your server.
# This one is safe to commit (it's a public key by definition).

VAPID_CLAIM_EMAIL=dwachira2002@gmail.com
# Identifies you as the operator to browser push services.
# Required by the Web Push spec. Just needs to be a valid email.


# ── Payment Sockets (dormant until accounts are ready) ───────────────────────

MPESA_CONSUMER_KEY=
MPESA_CONSUMER_SECRET=
MPESA_SHORTCODE=
MPESA_PASSKEY=
MPESA_CALLBACK_URL=
# M-Pesa Daraja API credentials. Leave empty — socket stays dormant.
# When you have a Safaricom till number and API credentials, fill these in.
# The socket activates automatically when the values are present.
# See: docs/MPESA_SANDBOX_TESTING.md for the full activation guide.
```

### How to generate new secrets (if you ever need to rotate them)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Run twice — once for SECRET_KEY, once for JWT_SECRET_KEY. Never reuse the same value
for both. Never use the dev values in production.

### What NOT to do

```bash
# NEVER commit .env or .env.production to git
git add .env             # ← wrong, dangerous
git add .env.production  # ← wrong, dangerous

# Check .gitignore has these
cat .gitignore | grep env
```

---

## 9. Full Deploy Checklist

When the hotel server is ready, in order:

```bash
# On the hotel server:

# 1. Clone the code
git clone <repo-url> /home/kurahia/app
cd /home/kurahia/app

# 2. Create Python virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Set up Postgres (see Section 7 above)
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER kurahia WITH PASSWORD 'strong_password';"
sudo -u postgres psql -c "CREATE DATABASE kurahia OWNER kurahia;"

# 4. Create the .env file (copy .env.production, fill in DATABASE_URL + real password)
cp .env.production .env
nano .env   # change CHANGE_PASSWORD to the real Postgres password

# 5. Run migrations (creates all tables in Postgres)
.venv/bin/flask db upgrade

# 6. Seed initial data
.venv/bin/flask seed run

# 7. Start the production server (Waitress — no debug mode, stable)
.venv/bin/waitress-serve --port=5000 "app:create_app()"

# 8. Build the PWAs pointing at the hotel server IP
# (in employee_pwa/.env.production and owner_pwa/.env.production)
VITE_API_URL=http://192.168.1.100:5000   # hotel server's local IP
npm run build

# 9. Serve the built PWA files
# Copy employee_pwa/dist to a static file server (Nginx, Caddy, or even a USB stick
# served by a simple Python HTTP server on the local network)
```

---

## 10. The Incident Logging Feature (just built)

Any staff member can log an accident or safety concern. Managers can view all
incidents and acknowledge them.

**Backend:** `app/incidents/core.py`
- `POST /incidents` — any authenticated staff logs an incident
- `GET /incidents` — manager+ lists all, filterable by severity and actioned status
- `PATCH /incidents/<id>/action` — manager acknowledges an incident

**Frontend:** `employee_pwa/src/screens/IncidentScreen.tsx`
- Top half: log form (all staff see this)
- Bottom half: history with Acknowledge buttons (only renders if `role_level >= 5`)

**Severities:** LOW / MEDIUM / HIGH
**Fields:** description, location, severity, involved guest (optional), idempotency key
**Append-only:** incidents are never edited or deleted — same rule as every other record.

---

## 11. Test Count

```
696 passed, 1 skipped
```

Every endpoint has tests for: happy path, role gates, idempotency, audit log written,
plain-English error messages. 1 skipped = a payment integration test that needs live
Safaricom credentials.

---

*You built this. You can explain every part of it. That's the goal.*
