# SYSTEM_OVERVIEW.md — Kurahia Resort Backend

> Single-document explanation of the entire backend. Target reader: the developer
> interview-prepping in 3 months, a new engineer joining, or a partner reading along.
> Assumes solid software fundamentals but no prior knowledge of this codebase.

---

## 1. WHAT THIS SYSTEM DOES

Kurahia is a boutique waterfront resort in Kenya. This backend is the operational brain of
the property — it tracks every transaction, every staff action, every guest visit, and every
kilogram of stock in real time. It does not serve a public website. It serves the staff who
run the resort and the owner who monitors it.

**The resort it serves:**
- A day-visitor waterfront facility (wristband entry, bar, restaurant, water activities)
- Villa accommodations for overnight guests
- Event hosting (weddings, corporate days)
- Approximately 10-30 staff across front-of-house, bar, kitchen, gate, and admin

**Who uses the system:**
- **Owner** (role level 10): sees everything, including alerts, staff performance, financial summaries, and audit trails. Remote access via Tailscale VPN.
- **Manager** (role level 5): runs daily operations — opens shifts, reconciles cash, approves leave, reviews anomalies, closes the day.
- **Gate staff** (role level 3): issues and deactivates wristbands, records headcount.
- **Waiters, bar, kitchen** (role level 1): open tabs, place orders, record payments, clock in/out.
- **The system itself** (actor: "judge", "daraja", "bank_sms", "card_gateway"): automated actors that write audit log entries for non-human events.

**Hardware topology:**

```
[Owner phone]        [Staff phones/tablets]   [Bar/Kitchen tablets]
    │                        │                        │
    │ Tailscale VPN          │ Hotel LAN (ethernet)   │ Hotel LAN (WiFi)
    │                        │                        │
    └────────────────────────┴────────────────────────┘
                             │
                     [Hotel server]
                     Ubuntu 22.04
                     Python 3.12 + Flask + Waitress
                     Nginx (TLS terminator, self-signed cert)
                     SQLite (dev) / Postgres (prod)
                     UPS-backed — survives power cuts
```

**Launch state:** All manual flows are production-ready. The three payment gateway integrations
(M-Pesa Daraja, bank API, card gateway) are built and dormant — they activate when the
corresponding env vars are set. Frontend is parked until payment integrations are sandbox-verified.

---

## 2. ARCHITECTURE AT A GLANCE

```
HTTP Request
    │
    ▼
Nginx (443, self-signed TLS)
    │
    ▼
Waitress (Python WSGI server, port 5000)
    │
    ▼
Flask app (app/__init__.py: create_app factory)
    │
    ├── JWT middleware (@require_active_user — kill-switch on every protected endpoint)
    │
    ├── 35+ Blueprints (URL namespaces, one per domain or sub-domain)
    │
    ├── SQLAlchemy ORM (45+ models)
    │       │
    │       └── SQLite (dev, in-memory for tests) / Postgres (prod)
    │
    └── Response: JSON only, no HTML

Background jobs (cron or flask CLI):
    flask judge run-daily     → spoilage + watch-list alerts
    flask judge run-weekly    → consumption-to-revenue ratio analysis
    flask events deliver-due  → dispatches queued notifications
    flask gate close-day      → forfeits unused wristband credits
    flask bookings flag-no-shows
    flask system backup
```

**Key design principle — everything is recoverable.** All data is append-only. There are no
DELETE endpoints on any business entity. Staff can be deactivated, not deleted. Menu items can
be disabled, not removed. Payments are append-only rows, never patched. If something goes wrong,
you can always reconstruct what happened from the AuditLog and the append-only ledgers.

**The factory pattern:** `create_app(config_name)` in `app/__init__.py` creates a fresh Flask
instance. This is how tests run with in-memory SQLite while production runs Postgres — you pass
`"testing"` or `"production"` and everything wires up accordingly. Extensions (`db`, `jwt`,
`migrate`) are initialized with `init_app()`, not at import time.

---

## 3. DOMAIN OVERVIEW

### 3.1 Auth (`app/auth/`)

**What it does:** Login, PIN setup, token refresh, account deactivation, lockout reset.

**Two login flows:**
- Password login (`POST /auth/login`) — manager and owner. Returns JWT access + refresh tokens.
- PIN login (`POST /auth/pin-login`) — tablet/staff quick-login. PIN must be set after first password login.

**Key models:** `User` (with `password_hash`, `pin_hash`, `is_active`, `failed_attempts`, `locked_until`), `Role` (with `level` integer), `Department`.

**The kill-switch:** Every protected endpoint uses `@require_active_user` (in `app/utils/auth_decorators.py`), which re-fetches the user from the database and checks `is_active` and lockout status on every single request. Setting `is_active=False` kicks out a user within milliseconds — their JWT token stays cryptographically valid but is rejected at the application layer. This is intentional: you cannot revoke JWTs from the gateway side, so the kill-switch must be in the application.

**Lockout:** Failed password attempts are counted. After a threshold, the account is locked for a progressive duration. Managers can reset a locked user's lockout (`POST /auth/reset-lockout/<user_id>`), but only for users with lower role levels than themselves.

**Roles:** Roles have a numeric `level` — owner=10, manager=5, gate=3, general staff=1. The level is stored in the JWT claims and checked explicitly in every protected endpoint (`actor.role.level < MANAGER_LEVEL`). This is the authorization system — there is no permission table, no RBAC framework.

### 3.2 Users & Admin (`app/auth/users.py`, `app/admin/`)

**What it does:** Account creation, role and department management, judge baseline configuration.

**Key endpoints:**
- `POST /auth/users` — create a new user account (manager creates staff, owner creates managers)
- `POST /auth/users/<id>/activate` — re-activate a deactivated account
- `GET /admin/departments`, `POST`, `PATCH` — manage department list
- `GET /admin/roles`, `POST`, `PATCH` — manage role definitions
- `GET /admin/baselines`, `POST`, `PATCH` — tune consumption-to-revenue baselines for the judge

The hierarchy is enforced in code: a user can only create or modify accounts with a lower role level than their own. An owner can create a manager; a manager cannot create another manager.

### 3.3 POS / Tabs (`app/pos/`)

**What it does:** The point-of-sale layer. Tabs are running bills. Orders are the items on the bill. Payments close the balance.

**Key models:** `Tab`, `Order`, `OrderItem`, `Charge` (one row per line item on a tab), `Payment`.

**The balance formula — no stored balance:**
```
tab_balance = SUM(charges.amount) - SUM(payments.amount)
```
This formula is computed from the ledger every time it's needed. The balance is never stored.
If two waiters accidentally record the same payment, the idempotency key prevents a duplicate row.

**Tab lifecycle:**
1. Waiter opens tab: `POST /tabs` → returns tab ID
2. Waiter places order: `POST /orders` → creates Order
3. Order sent to kitchen/bar queue: `POST /orders/<id>/send`
4. Kitchen marks items ready: `POST /order-items/<id>/ready`
5. Waiter serves items: `POST /order-items/<id>/serve`
6. Customer pays: `POST /tabs/<tab_id>/payments`
7. Waiter closes tab: `POST /tabs/<tab_id>/close` (only if balance ≤ 0)

**Wristband tabs:** When a wristband is issued at the gate, a BAND-type Tab is opened automatically. A Payment of KES 3,000 (the entry fee) is recorded against the tab immediately, giving the tab a -3,000 starting balance (a credit). Every purchase at the bar or restaurant adds a Charge. Balance = charges − the 3,000 entry credit − any additional payments.

**Queue system:** Orders flow through kitchen and bar queues. `GET /kitchen/queue` and `GET /bar/queue` show what's in progress. Kitchen/bar staff mark items `ready` → waiter marks `serve`. If something goes wrong (wrong item, customer changes mind), staff can `send-back` an order item, which writes a negative stock movement automatically.

### 3.4 Inventory & Stock (`app/inventory/`)

**What it does:** Tracks every ingredient and supply item. All stock changes go through the append-only StockMovement ledger.

**Key models:** `InventoryItem`, `StockMovement` (signed change_amount), `StockCount`, `Purchase`, `PurchaseRequest`.

**Current stock formula:**
```
stock_level = SUM(stock_movements.change_amount) WHERE item_id = ?
```
A positive change_amount is stock in (purchase, return). Negative is stock out (sale, spoilage, staff meal). The check constraint `change_amount != 0` prevents zero-amount ghost records.

**Movement reasons:** `PURCHASE`, `COUNT`, `SPOILAGE`, `STAFF_MEAL`, `SENT_BACK`, `TRANSFER`, `ADJUSTMENT`, `SALE_PLACEHOLDER`, `EVENT_ALLOCATION`. The judge ignores `EVENT_ALLOCATION` — a wedding consuming 50kg of beef is not theft.

**Purchase flow:** Staff submit a `PurchaseRequest`. Manager approves it. Once goods arrive, staff record a `Purchase` (which writes a positive StockMovement). This double-check prevents phantom inventory.

**Physical count reconciliation:** `POST /inventory/counts` records the counted quantity. The system computes the variance (counted vs system's expected) and writes a `COUNT` movement to bring the ledger in line with reality. Unexplained variances feed into the judge's analysis.

### 3.5 Gate & Wristbands (`app/gate/`)

**What it does:** Controls entry for day visitors. Issues numbered wristbands, tracks headcount, forfeits unused credits at end of day.

**Key models:** `Wristband`, `GateHeadcount`.

**Wristband issuance:** `POST /gate/issue-band` — gate staff selects payment method (CASH, M-Pesa, etc.), records the entry fee payment, and the system issues a wristband with a unique sequential band number for that day. Band numbers reset daily at midnight. The sequential counter uses `SELECT FOR UPDATE` to prevent two concurrent requests from issuing the same number.

**End-of-day forfeit:** `flask gate close-day` sweeps all ACTIVE wristbands at end of day. If a customer left without consuming their credit, the balance remains on their tab. The forfeit sweeps those tab balances as resort revenue. This is the legitimate mechanism for keeping unused entry fees.

**Reconciliation:** `GET /gate/reconciliation` shows bands issued × entry fee vs actual payments collected. Any mismatch is visible here and triggers a JudgeAlert.

### 3.6 Bookings & Villas (`app/bookings/`)

**What it does:** Reservation lifecycle for overnight villa stays and bookable day activities.

**Key models:** `BookableResource` (villa, water activity slot, event space), `Booking`, `BookingPayment` (deposit tracking), `GuestRecord`, `Waiver`.

**Booking state machine:**
```
HELD → CONFIRMED → CHECKED_IN → CHECKED_OUT
     ↘ CANCELLED  ↘ CANCELLED
     ↘ NO_SHOW
```

`base_total` is a price snapshot taken at booking creation. Changing the villa rate later does not retroactively change confirmed bookings — the snapshot is the contract.

`tab_id` is NULL until check-in. When a guest checks in, a Villa-type Tab opens and the tab_id is recorded on the Booking. All food, drinks, and activities during the stay are charged to that tab. Settlement happens at checkout.

**Guest records:** `GuestRecord` stores repeat-guest data (name, phone, ID number, visit history). Useful for villa regulars and building a CRM picture without a full CRM system.

**Waivers:** Signed liability waivers for water activities. `POST /waivers` records the signature. `POST /waivers/<id>/revoke` flags a waiver as revoked. Append-only — revocation is a new row, not an update.

### 3.7 Finance & Payments (`app/finance/`)

See Section 5 for the full payment layer explanation. Summary of what's in the finance module:

- **`cash.py`** — cash reconciliation per staff member. Manager records actual cash handed in vs what the POS says should have been collected. Three-way: BALANCED / SHORT / OVER.
- **`mpesa.py`** — manual M-Pesa and card reconciliation. `GET /finance/mpesa/pending` lists unreconciled payments for a date. `POST /finance/mpesa/reconcile` marks them MATCHED or FLAGGED.
- **`mpesa_daraja.py`** — M-Pesa Daraja dormant socket (STK Push + C2B callback).
- **`bank.py`** — manual bank transfer reconciliation.
- **`bank_transfer.py`** — bank transfer dormant socket (SMS forwarder + API).
- **`card_gateway.py`** — card gateway dormant socket (Pesapal/DPO/Cellulant).
- **`budgets.py`** — monthly department budgets. Manager sets budget; system tracks actual spend against it.
- **`analytics.py`** — void rate analysis per staff member. Abnormal void rates fire JudgeAlerts.
- **`reports.py`** — three-way reconciliation report (POS receipts + cash + stock alerts in one view), period close (locks the day's safe count), financial dashboard.

### 3.8 HR (`app/hr/`)

**What it does:** Employee lifecycle — profiles, shifts, clock-in/clock-out, leave, attendance, performance, WiFi access.

**Key models:** `EmployeeProfile`, `Shift`, `ClockEvent`, `LeaveRequest`, `AbsenceNotice`, `WiFiAllowList`.

**Clock events are append-only:** Every clock-in and clock-out is a new `ClockEvent` row. If a manager needs to correct an error, they add a `manual` clock event with a reason — the original wrong event stays in the log.

**Performance scores:** `GET /hr/performance/<profile_id>` computes a rolling score from guest feedback ratings associated with the employee. Feedback is connected to tabs; the waiter who served the tab gets the rating.

**WiFi allow-list:** Staff WiFi access is controlled by MAC address. `POST /hr/wifi` adds a device. `PATCH /hr/wifi/<id>` updates it. `POST /hr/wifi/<id>/disable` blocks it. This controls which devices can use the staff WiFi network (enforced by the router, not Flask — Flask just manages the list).

### 3.9 Events (`app/events/`)

**What it does:** Weddings, corporate days, private functions. Tracks event lifecycle, staff assignments, inventory allocations.

**Key models:** `Event`, `EventType`, `EventAssignment`, `EventInventoryAllocation`, `EventStockMovement`.

**Event lifecycle:** `PENDING → CONFIRMED → IN_PROGRESS → COMPLETED / CANCELLED`.

**Staff assignments:** Manager assigns staff to an event. `POST /events/<id>/assignments/<aid>/acknowledge` — staff member confirms they received the assignment. The acknowledgment is mandatory; unacknowledged assignments trigger a notification.

**Inventory allocation:** Events can pre-allocate stock. `POST /events/<id>/inventory/allocate` reserves ingredients. `issue` releases them from the warehouse. `return` puts unused stock back. `consume` marks stock as used. Each action writes a `TRANSFER` or `EVENT_ALLOCATION` StockMovement.

### 3.10 Conduct (`app/conduct/`)

**What it does:** Versioned staff code of conduct. Staff sign each version. Compliance is tracked.

**Key models:** `ConductRule` (versioned), `ConductSignature`.

Rules are versioned — if the owner updates the code of conduct, the version number increments. All staff must re-sign. `GET /conduct/compliance` shows who has signed the current version and who hasn't.

### 3.11 Disputes, Suggestions, Feedback (`app/disputes/`, `app/suggestions/`, `app/feedback/`)

- **Disputes:** Staff can file a dispute about a roster decision, schedule conflict, etc. Lifecycle: OPEN → CLAIMED (manager takes it) → RESOLVED / DISMISSED.
- **Suggestions:** Two-tier routing. MANAGEMENT suggestions go to managers. OWNER_PRIVATE suggestions are structurally hidden from managers — the query excludes them for non-owners. This is query-level authorization: the row doesn't appear in the result set for a manager, not just "you can see it but not act on it."
- **Feedback:** Guest feedback linked to a Tab. Staff member associated with the tab gets the performance score. Triggers a performance recalculation.

### 3.12 Equipment (`app/equipment/`)

**What it does:** Track resort equipment (generators, pumps, boats, kitchen equipment) with maintenance schedules and safety checks.

**Key models:** `Equipment`, `MaintenanceLog`, `SafetyCheck`.

`Equipment.is_due_service` is a computed `@property` — it's derived from `last_service_utc + service_interval_days`, never stored. This is the "derived state" pattern applied outside the financial domain.

### 3.13 Dashboard (`app/dashboard/`)

**What it does:** 10 owner-facing aggregation endpoints that roll up everything into a single view. These are read-only, owner-level endpoints.

Endpoints: `/dashboard/overview`, `/inventory`, `/finance`, `/bookings`, `/staff`, `/conduct`, `/suggestions`, `/calendar`, `/feedback`, `/equipment`, `/alerts`, plus alert acknowledgment (`POST /dashboard/alerts/<id>/acknowledge`).

### 3.14 Notifications (`app/notifications/`)

**What it does:** In-system inbox. The judge, the event system, and workflow transitions write notification rows. `GET /notifications/inbox` returns unread messages for the current user.

### 3.15 Calendar (`app/calendar_view/`)

**What it does:** Date-tagged planning entries — holidays, resort events, maintenance windows. Seeded with Kenyan public holidays. `flask calendar seed-kenya-holidays` loads the next 12 months.

### 3.16 Judge & Alerts (`app/judge/`)

See Section 7 for the full judge explanation. Short summary: `GET /judge/alerts` returns open JudgeAlerts. `POST /judge/alerts/<id>/acknowledge` marks one acknowledged.

---

## 4. THE PATTERNS THAT REPEAT

These patterns appear in almost every domain. Understanding them means you can read any part of the codebase quickly.

### Pattern 1 — Idempotency keys

Every write that could be retried or duplicated carries an `idempotency_key` column with a `UNIQUE` constraint. Before writing, the code checks if a row with that key already exists. If it does, the function returns the existing row silently.

**The prefix scheme prevents cross-domain collisions:**
```
daraja-{checkout_request_id}       # M-Pesa STK Push
banksms-{bank_ref}                 # bank SMS forwarder payments
cardipn-pesapal-{order_tracking_id} # Pesapal IPN
cardipn-dpo-{trans_token}          # DPO IPN
cardipn-cellulant-{merchant_tx_id} # Cellulant IPN
```

For manual payments, a UUID is generated at call time by the caller. For automated callbacks, the external transaction reference is the key. A Pesapal IPN arriving twice with the same `OrderTrackingId` will find the payment already written and return `(True, existing_payment.id)` immediately. See `app/finance/card_gateway.py::_handle_pesapal_ipn` for a concrete example.

### Pattern 2 — Atomic writes (the Cat 5.1 pattern)

Named "Category 5, Item 1" from the Phase B security review: every business write and its audit log entry must land in the **same database transaction**, or neither lands. Found in 33 files across the codebase.

**Before Cat 5.1 (wrong):**
```python
payment = Payment(...)
db.session.add(payment)
db.session.commit()    # ← payment is committed
AuditLog.log(...)      # ← if this crashes, payment exists but audit doesn't
db.session.commit()
```

**After Cat 5.1 (correct):**
```python
payment = Payment(...)
db.session.add(payment)
db.session.flush()     # assigns ID without committing
recon = PaymentReconciliation(payment_id=payment.id, ...)
db.session.add(recon)
AuditLog.log(...)      # all queued, nothing committed yet
db.session.commit()    # one commit — all or nothing
```

See `app/finance/mpesa_daraja.py::handle_stk_callback` at the success path for the canonical example.

### Pattern 3 — Append-only ledgers

The following tables are append-only — no UPDATE or DELETE endpoint exists on them:

| Table | What it records |
|---|---|
| `payments` | Money received — every payment ever made |
| `charges` | Money owed — every line item ever put on a tab |
| `stock_movements` | Every change to inventory stock |
| `audit_logs` | Every system action, hash-chained |
| `clock_events` | Every clock-in and clock-out |
| `conduct_signatures` | Every staff signature on every rule version |
| `notifications` | All dispatched notifications |
| `cash_reconciliations` | Daily cash handover records |
| `maintenance_logs` | Equipment maintenance history |

If something needs correcting, a new row is added. The old row is not touched. The audit trail is always complete.

### Pattern 4 — Dormant sockets

The payment integration pattern: build the socket in full, but gate its activation on environment variables. When the env vars are missing, the function returns `(False, "plain English error")` immediately. When the vars are set, the full integration runs.

```python
def is_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED_ENV_VARS)

def initiate_card_payment(amount, ...):
    if not is_configured():
        return False, "Card gateway not configured."
    # ... real implementation
```

Three sockets built this way: `mpesa_daraja.py`, `bank_transfer.py`, `card_gateway.py`. Each has a `GET /finance/*/status` diagnostic endpoint that tells you exactly what's missing.

### Pattern 5 — JudgeAlert with fire_if_absent

The `fire_alert_if_absent()` service (in `app/services/judge_alerts.py`) ensures that the same anomaly doesn't create 100 duplicate alerts. It queries for an existing `OPEN` alert of the same type for the same item in the same period before creating a new one.

```python
alert, created = fire_alert_if_absent(
    alert_type="RATIO",
    description_key="Tusker Lager",  # dedup key
    item_id=item.id,
    severity=AlertSeverity.HIGH.value,
    description="Tusker Lager: 48 units consumed, expected ~20...",
)
```

If an OPEN alert for "Tusker Lager" RATIO already exists, `created=False` and the existing alert is returned. If not, a new one is created. This means the judge can run daily without flooding the owner's dashboard.

### Pattern 6 — Role-based endpoints

Every protected endpoint reloads the actor from the database (not from the JWT) and checks their role level explicitly:

```python
@blueprint.post("/some-endpoint")
@require_active_user
def some_endpoint():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:   # MANAGER_LEVEL = 5
        return jsonify({"error": "Manager or above required."}), 403
```

The JWT contains the role_level as a claim, but this is not used for authorization — it's used only for quick client-side display. The database is the single source of truth. If an owner demotes someone from manager to staff, their next request will fail even if they still hold a manager-level JWT token.

### Pattern 7 — Plain-English error returns

Functions in the service/socket layer return `(bool, value_or_error)` tuples. On failure, the second element is always a plain-English string the route can put directly in the JSON response:

```python
ok, result = initiate_stk_push(amount=1500, phone_number="0712345678", ...)
if not ok:
    return jsonify({"error": result}), 400
# result is "Invalid Kenyan phone number." or "Daraja OAuth timed out after 10 seconds."
```

No raw exceptions, no technical stack traces reach the client. This matters because the frontend displays these strings directly to cashiers.

### Pattern 8 — Always-return-200 for webhooks

Any endpoint that a third-party system calls (Safaricom Daraja, bank SMS forwarder, card gateways) always returns HTTP 200, even if our internal processing fails. This prevents the third party from retrying indefinitely on a bug in our code.

```python
@mpesa_daraja_bp.post("/mpesa/callback")
def mpesa_callback():
    try:
        payload = request.get_json(silent=True) or {}
        handle_stk_callback(payload)  # may fail internally
    except Exception:
        current_app.logger.exception("Daraja callback processing failed")
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200  # always
```

Internal failures are logged via `app.logger.exception()`. The third-party system sees a success. We debug from logs, not from retry storms.

### Pattern 9 — The hash-chained audit log

Every call to `AuditLog.log()` computes a SHA-256 hash of the new row's content plus the previous row's hash. This forms a chain: if anyone edits or deletes a past row, every subsequent hash becomes invalid. `flask audit verify-chain` walks the entire chain and re-computes every hash.

```python
raw = f"{actor}|{action}|{target}|{timestamp.isoformat()}|{prev_hash or ''}"
entry_hash = hashlib.sha256(raw.encode()).hexdigest()
```

This does not prevent deletion at the database level — someone with direct DB access can still tamper. It detects the tampering after the fact. See `app/models/audit_log.py::verify_chain`.

---

## 5. THE PAYMENT LAYER

### The three-layer structure

Every payment method at Kurahia operates in three layers. Layers 1 and 2 are independent — you can skip Layer 2 and go straight from manual to full API if you want.

```
LAYER 1: Manual entry (active from day one)
  Cashier records payment by hand → Payment row written
  Manager reconciles at end of shift

LAYER 2: SMS / forwarder (dormant, activates with one env var)
  Bank credit SMS forwarded from till phone → Payment row auto-written
  No manual reconciliation needed

LAYER 3: Direct API (dormant, activates with provider env vars)
  Safaricom Daraja, Bank API, or Card Gateway called in real time
  Payment row written on callback
```

**The unified data model:** All three layers write the same `Payment` row and `PaymentReconciliation` row. The frontend, the tab balance formula, and the audit log don't care which layer created the payment. This is by design — you can swap from manual to full API without touching any other code.

### M-Pesa Daraja (`app/finance/mpesa_daraja.py`)

**Env vars needed:** `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`

**Two flows:**
- **STK Push** (cashier-initiated): `POST /finance/mpesa/charge` — cashier enters customer's phone number and amount. Safaricom prompts the customer's phone. Customer enters PIN. Safaricom calls our `POST /finance/mpesa/callback`. Handler writes Payment + PaymentReconciliation atomically.
- **C2B** (customer pays till directly): Safaricom calls `POST /finance/mpesa/callback` automatically when customer pays the shortcode. Same callback handler detects the payload shape and routes accordingly.

**OAuth token caching:** The Daraja access token is cached in `_token_cache` for 55 minutes (real expiry is 60 min). Refreshed 5 minutes before expiry to avoid mid-transaction failures.

**Diagnostic:** `GET /finance/mpesa/status` → `{"configured": bool, "message": str}`

### Bank Transfer (`app/finance/bank_transfer.py`)

**SMS forwarder env var:** `BANK_SMS_WEBHOOK_SECRET`
**API env vars:** `BANK_PROVIDER` (equity | kcb | coop) + `BANK_API_KEY`

**SMS flow:** Android SMS forwarder app on the till phone POSTs every bank credit SMS to `POST /finance/bank/sms-forward`. Header `X-Webhook-Secret` checked against `BANK_SMS_WEBHOOK_SECRET`. The handler runs the SMS body through per-bank regex patterns (Equity, KCB, Co-op) to extract amount and bank reference. Writes Payment atomically. Idempotency key: `banksms-{bank_ref}`.

**API flow:** Manager hits `POST /finance/bank/verify` with an amount and bank reference. The system calls the configured bank's API (Equity Jenga, KCB Open Banking, or Co-op Mobicash) to confirm the transfer. Returns `(True, {provider, verified_at, details})` or `(False, error)`.

**Diagnostic:** `GET /finance/bank/status` → `{"sms_configured": bool, "api_configured": bool, "provider": str, "message": str}`

### Card Gateway (`app/finance/card_gateway.py`)

**Env vars:** `CARD_PROVIDER` (pesapal | dpo | cellulant) + `CARD_API_KEY` + `CARD_MERCHANT_ID` + `CARD_IPN_URL`

**Initiation flow:** `POST /finance/card/initiate` → cashier provides amount + customer contact. System calls the configured gateway (Pesapal v3, DPO XML API, or Cellulant Tingg). Returns a `payment_url`. Customer follows the URL on their device and completes payment.

**IPN callback:** Gateway calls `POST /finance/card/callback` when customer pays. Handler detects provider from payload shape (Pesapal has `OrderTrackingId`, DPO has `TransactionApproval`, Cellulant has `merchantTransactionID` + `serviceCode`). Writes Payment atomically. Idempotency key: `cardipn-{provider}-{transaction_ref}`.

**Diagnostic:** `GET /finance/card/status` → `{"configured": bool, "provider": str, "message": str}`

### The manual flow (always active)

Manual entry (`POST /tabs/<tab_id>/payments`) is always available as a fallback. If Daraja is down, cashier records M-Pesa code by hand. Manager reconciles at end of shift via `POST /finance/mpesa/reconcile`. The reconciliation table (`PaymentReconciliation`) is identical whether the row was written by a human or by a gateway callback.

---

## 6. EVERY ENDPOINT — REFERENCE TABLE

*Role levels: 10=owner, 5=manager, 3=gate, 1=any staff. "public" = no auth.*

### Auth (`/auth`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /auth/login | public | Password login (manager/owner) | auth/routes.py:42 |
| POST | /auth/pin-login | public | PIN login (tablet/staff) | auth/routes.py:106 |
| POST | /auth/refresh | authenticated | Refresh access token | auth/routes.py:156 |
| POST | /auth/set-pin | authenticated | First-time PIN setup | auth/routes.py:178 |
| POST | /auth/change-pin | authenticated | Change own PIN | auth/routes.py:212 |
| POST | /auth/deactivate/\<id\> | 5 | Kill-switch: deactivate user | auth/routes.py:243 |
| POST | /auth/reset-lockout/\<id\> | 5 | Clear a user's lockout | auth/routes.py:272 |
| POST | /auth/users | 5 | Create a new user account | auth/users.py:25 |
| PATCH | /auth/users/\<id\> | 5 | Edit user (name, role, dept) | auth/users.py:85 |
| GET | /auth/users | 5 | List all users | auth/users.py:127 |
| POST | /auth/users/\<id\>/activate | 5 | Re-activate a user | auth/users.py:153 |

### Admin (`/admin`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| GET | /admin/departments | 5 | List departments | admin/departments.py:28 |
| POST | /admin/departments | 10 | Create department | admin/departments.py:44 |
| PATCH | /admin/departments/\<id\> | 10 | Edit department | admin/departments.py:64 |
| POST | /admin/departments/\<id\>/disable | 10 | Disable department | admin/departments.py:82 |
| POST | /admin/departments/\<id\>/enable | 10 | Enable department | admin/departments.py:98 |
| GET | /admin/roles | 5 | List roles | admin/roles.py:31 |
| POST | /admin/roles | 10 | Create role | admin/roles.py:47 |
| PATCH | /admin/roles/\<id\> | 10 | Edit role | admin/roles.py:74 |
| POST | /admin/roles/\<id\>/disable | 10 | Disable role | admin/roles.py:97 |
| POST | /admin/roles/\<id\>/enable | 10 | Enable role | admin/roles.py:113 |
| GET | /admin/baselines | 5 | List judge baselines | admin/baselines.py:30 |
| POST | /admin/baselines | 10 | Create baseline | admin/baselines.py:55 |
| PATCH | /admin/baselines/\<id\> | 10 | Edit baseline | admin/baselines.py:93 |
| POST | /admin/baselines/\<id\>/disable | 10 | Disable baseline | admin/baselines.py:115 |
| POST | /admin/baselines/\<id\>/enable | 10 | Enable baseline | admin/baselines.py:131 |

### POS — Tabs (`/tabs`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /tabs | 1 | Open a new tab | pos/tabs.py:24 |
| GET | /tabs/\<tab_id\> | 1 | Get tab + current balance | pos/tabs.py:45 |
| POST | /tabs/\<tab_id\>/close | 1 | Close tab (requires zero balance) | pos/tabs.py:86 |
| POST | /tabs/\<tab_id\>/payments | 1 | Record a payment against tab | pos/payments.py:20 |

### POS — Orders & Queues
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /orders | 1 | Create order (adds charges to tab) | pos/orders.py:48 |
| POST | /orders/\<id\>/send | 1 | Send order to kitchen/bar queue | pos/orders.py:113 |
| POST | /order-items/\<id\>/receive | 1 | Kitchen/bar receives item | pos/orders.py:166 |
| POST | /order-items/\<id\>/ready | 1 | Mark item ready for pickup | pos/orders.py:185 |
| POST | /order-items/\<id\>/serve | 1 | Waiter marks item served | pos/orders.py:204 |
| POST | /order-items/\<id\>/cancel | 1 | Cancel an item (void) | pos/orders.py:223 |
| POST | /order-items/\<id\>/send-back | 1 | Return item to kitchen | pos/orders.py:244 |
| GET | /kitchen/queue | 1 | Live kitchen queue | pos/queues.py:61 |
| GET | /bar/queue | 1 | Live bar queue | pos/queues.py:71 |
| GET | /receipts/\<tab_id\> | 1 | Generate receipt | pos/receipts.py:18 |
| GET | /reports/staff-cash | 5 | Cash collected per staff | pos/orders.py:293 |

### POS — Menu (`/menu/items`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| GET | /menu/items | 1 | List active menu items | pos/menu.py:133 |
| POST | /menu/items | 5 | Create menu item | pos/menu.py:30 |
| PATCH | /menu/items/\<id\> | 5 | Edit menu item | pos/menu.py:73 |
| POST | /menu/items/\<id\>/disable | 5 | Disable menu item | pos/menu.py:101 |
| POST | /menu/items/\<id\>/enable | 5 | Enable menu item | pos/menu.py:117 |

### Inventory (`/inventory`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| GET | /inventory/items | 1 | List inventory items + stock levels | inventory/items.py:98 |
| POST | /inventory/items | 5 | Create inventory item | inventory/items.py:25 |
| PATCH | /inventory/items/\<id\> | 5 | Edit item | inventory/items.py:65 |
| POST | /inventory/items/\<id\>/disable | 5 | Disable item | inventory/items.py:135 |
| POST | /inventory/items/\<id\>/enable | 5 | Enable item | inventory/items.py:151 |
| POST | /inventory/counts | 5 | Submit physical stock count | inventory/counts.py:29 |
| GET | /inventory/variance | 5 | Variance report (system vs physical) | inventory/variance_routes.py:24 |
| POST | /inventory/movements/spoilage | 1 | Record spoilage | inventory/movements.py:85 |
| POST | /inventory/movements/staff-meal | 1 | Record staff meal consumption | inventory/movements.py:121 |
| POST | /inventory/movements/sent-back | 1 | Record item sent back | inventory/movements.py:162 |
| POST | /inventory/purchase-requests | 1 | Submit purchase request | inventory/purchases.py:37 |
| POST | /inventory/purchase-requests/\<id\>/propose | 1 | Propose a supplier price | inventory/purchases.py:80 |
| POST | /inventory/purchase-requests/\<id\>/approve | 5 | Approve and commit purchase | inventory/purchases.py:115 |
| POST | /inventory/purchases | 5 | Record goods received | inventory/purchases.py:156 |

### Gate (`/gate`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /gate/issue-band | 3 | Issue wristband to customer | gate/core.py:51 |
| POST | /gate/deactivate-band/\<num\> | 3 | Deactivate a band (customer left) | gate/core.py:87 |
| GET | /gate/bands/\<num\> | 1 | Look up band by number | gate/core.py:110 |
| GET | /gate/active-bands | 3 | List all active bands | gate/core.py:133 |
| POST | /gate/headcount | 3 | Record gate headcount | gate/core.py:147 |
| POST | /gate/forfeit-day | 5 | EOD sweep — forfeit unused credits | gate/core.py:187 |
| GET | /gate/reconciliation | 5 | Gate revenue reconciliation report | gate/core.py:216 |

### Bookings (`/bookings`, `/bookable-resources`, `/booking-payments`, etc.)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /bookable-resources | 5 | Create bookable resource (villa, etc.) | bookings/resources.py:21 |
| GET | /bookable-resources | 1 | List resources | bookings/resources.py:65 |
| PATCH | /bookable-resources/\<id\> | 5 | Edit resource | bookings/resources.py:84 |
| POST | /bookable-resources/\<id\>/disable | 5 | Disable resource | bookings/resources.py:117 |
| POST | /bookable-resources/\<id\>/enable | 5 | Enable resource | bookings/resources.py:133 |
| POST | /bookings | 1 | Create booking (HELD) | bookings/core.py:70 |
| POST | /bookings/\<id\>/confirm | 5 | Confirm booking (takes deposit) | bookings/core.py:167 |
| POST | /bookings/\<id\>/check-in | 5 | Check in (opens villa tab) | bookings/core.py:200 |
| POST | /bookings/\<id\>/check-out | 5 | Check out | bookings/core.py:229 |
| POST | /bookings/\<id\>/cancel | 5 | Cancel booking | bookings/core.py:280 |
| GET | /bookings | 1 | List bookings | bookings/core.py:305 |
| GET | /bookings/availability | 1 | Check resource availability | bookings/core.py:336 |
| GET | /bookings/today | 1 | Today's arrivals and departures | bookings/core.py:373 |
| POST | /bookings/\<id\>/water-sessions | 1 | Add water activity session | bookings/core.py:409 |
| POST | /booking-payments | 1 | Record deposit | bookings/deposits.py:23 |
| GET | /booking-payments | 5 | List deposits | bookings/deposits.py:102 |
| GET | /guest-records | 5 | List guest records | bookings/guests.py:18 |
| GET | /guest-records/\<id\> | 5 | Get guest record | bookings/guests.py:34 |
| GET | /guest-records/\<id\>/history | 5 | Guest visit history | bookings/guests.py:46 |
| POST | /waivers | 1 | Record signed waiver | bookings/waivers.py:19 |
| GET | /waivers | 5 | List waivers | bookings/waivers.py:60 |
| POST | /waivers/\<id\>/revoke | 5 | Revoke waiver | bookings/waivers.py:87 |
| GET | /front-desk/today | 5 | Front desk dashboard (today) | bookings/dashboard.py:22 |

### HR (`/hr`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /hr/profiles | 5 | Create employee profile | hr/profiles.py:22 |
| GET | /hr/profiles | 5 | List profiles | hr/profiles.py:84 |
| GET | /hr/profiles/\<id\> | 5 | Get profile | hr/profiles.py:107 |
| PATCH | /hr/profiles/\<id\> | 5 | Edit profile | hr/profiles.py:132 |
| POST | /hr/profiles/\<id\>/disable | 5 | Disable profile | hr/profiles.py:174 |
| POST | /hr/profiles/\<id\>/enable | 5 | Enable profile | hr/profiles.py:190 |
| POST | /hr/shifts | 5 | Create shift | hr/shifts.py:48 |
| GET | /hr/shifts | 1 | List shifts | hr/shifts.py:105 |
| PATCH | /hr/shifts/\<id\> | 5 | Edit shift | hr/shifts.py:140 |
| POST | /hr/shifts/\<id\>/cancel | 5 | Cancel shift | hr/shifts.py:171 |
| POST | /hr/clock-in | 1 | Clock in | hr/clock.py:68 |
| POST | /hr/clock-out | 1 | Clock out | hr/clock.py:103 |
| POST | /hr/clock-events/manual | 5 | Manual clock correction | hr/clock.py:136 |
| GET | /hr/clock-events | 5 | List clock events | hr/clock.py:201 |
| POST | /hr/leave-requests | 1 | Submit leave request | hr/leave.py:22 |
| POST | /hr/leave-requests/\<id\>/approve | 5 | Approve leave | hr/leave.py:69 |
| POST | /hr/leave-requests/\<id\>/reject | 5 | Reject leave | hr/leave.py:98 |
| POST | /hr/leave-requests/\<id\>/cancel | 1 | Cancel own leave request | hr/leave.py:126 |
| GET | /hr/leave-requests | 5 | List leave requests | hr/leave.py:150 |
| GET | /hr/attendance/today | 5 | Today's attendance | hr/attendance.py:31 |
| GET | /hr/attendance/employee/\<id\> | 5 | Employee attendance history | hr/attendance.py:90 |
| GET | /hr/attendance/summary | 5 | Attendance summary | hr/attendance.py:138 |
| GET | /hr/performance/\<id\> | 5 | Employee performance score | hr/performance.py:32 |
| GET | /hr/payroll-draft | 10 | Draft payroll from hours | hr/performance.py:60 |
| POST | /hr/absence-notices | 1 | Submit absence notice | hr/absence.py:23 |
| GET | /hr/absence-notices | 5 | List absence notices | hr/absence.py:77 |
| POST | /hr/wifi | 5 | Add WiFi device | hr/wifi.py:28 |
| GET | /hr/wifi | 5 | List WiFi allow-list | hr/wifi.py:54 |
| PATCH | /hr/wifi/\<id\> | 5 | Edit WiFi entry | hr/wifi.py:71 |
| POST | /hr/wifi/\<id\>/disable | 5 | Block WiFi device | hr/wifi.py:96 |
| POST | /hr/wifi/\<id\>/enable | 5 | Unblock WiFi device | hr/wifi.py:112 |

### Finance (`/finance`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| GET | /finance/cash/pending | 5 | Unreconciled cash per staff | finance/cash.py:30 |
| POST | /finance/cash/reconcile | 5 | Record actual cash handover | finance/cash.py:63 |
| GET | /finance/mpesa/pending | 5 | Unreconciled M-Pesa payments | finance/mpesa.py:47 |
| POST | /finance/mpesa/reconcile | 5 | Reconcile M-Pesa/card payments | finance/mpesa.py:79 |
| GET | /finance/card/summary | 5 | Daily card total | finance/mpesa.py:172 |
| POST | /finance/mpesa/charge | 5 | Initiate Daraja STK Push | finance/mpesa_daraja.py:365 |
| POST | /finance/mpesa/callback | public | Daraja IPN receiver | finance/mpesa_daraja.py:399 |
| GET | /finance/mpesa/status | 5 | Daraja socket diagnostic | finance/mpesa_daraja.py:416 |
| GET | /finance/bank/pending | 5 | Unreconciled bank transfers | finance/bank.py |
| POST | /finance/bank/reconcile | 5 | Reconcile bank transfers | finance/bank.py |
| POST | /finance/bank/sms-forward | public | Bank SMS forwarder receiver | finance/bank_transfer.py |
| POST | /finance/bank/verify | 5 | Verify transfer via bank API | finance/bank_transfer.py |
| GET | /finance/bank/status | 5 | Bank socket diagnostic | finance/bank_transfer.py |
| POST | /finance/card/initiate | 5 | Initiate card payment | finance/card_gateway.py:628 |
| POST | /finance/card/callback | public | Card gateway IPN receiver | finance/card_gateway.py:664 |
| GET | /finance/card/status | 5 | Card socket diagnostic | finance/card_gateway.py:678 |
| POST | /finance/budgets | 5 | Create monthly budget | finance/budgets.py:28 |
| PATCH | /finance/budgets/\<id\> | 5 | Edit budget | finance/budgets.py:82 |
| POST | /finance/budgets/\<id\>/disable | 5 | Disable budget | finance/budgets.py:110 |
| POST | /finance/budgets/\<id\>/enable | 5 | Enable budget | finance/budgets.py:126 |
| GET | /finance/budgets/status | 5 | Budget utilization | finance/budgets.py:142 |
| GET | /finance/anomalies/voids | 5 | Void rate analysis per staff | finance/analytics.py |
| GET | /finance/anomalies/discounts | 5 | Discount anomalies (placeholder) | finance/analytics.py |
| GET | /finance/reconciliation | 5 | Three-way daily reconciliation | finance/reports.py:37 |
| POST | /finance/close-period | 5 | Lock day (safe count) | finance/reports.py:162 |
| GET | /finance/dashboard | 10 | Owner financial dashboard | finance/reports.py:275 |

### Events (`/events`, `/event-types`)
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /event-types | 10 | Create event type | events/core.py (event_types_bp) |
| POST | /event-types/\<id\>/disable | 10 | Disable event type | events/core.py:111 |
| POST | /events | 5 | Create event | events/core.py:129 |
| PATCH | /events/\<id\> | 5 | Edit event | events/core.py:179 |
| POST | /events/\<id\>/confirm | 5 | Confirm event | events/core.py:224 |
| POST | /events/\<id\>/start | 5 | Start event (in-progress) | events/core.py:240 |
| POST | /events/\<id\>/complete | 5 | Complete event | events/core.py:249 |
| POST | /events/\<id\>/cancel | 5 | Cancel event | events/core.py:258 |
| GET | /events | 1 | List events | events/core.py:281 |
| GET | /events/upcoming | 1 | Upcoming events | events/core.py:304 |
| GET | /events/\<id\> | 1 | Get event detail | events/core.py:318 |
| POST | /events/\<id\>/assignments | 5 | Assign staff to event | events/core.py:332 |
| POST | /events/\<id\>/assignments/\<aid\>/acknowledge | 1 | Staff acknowledges assignment | events/core.py:377 |
| POST | /events/\<id\>/assignments/\<aid\>/cancel | 5 | Cancel assignment | events/core.py:402 |
| GET | /events/\<id\>/assignments | 1 | List event assignments | events/core.py:423 |
| POST | /events/\<id\>/inventory/allocate | 5 | Pre-allocate inventory | events/core.py:435 |
| POST | /events/\<id\>/inventory/\<aid\>/issue | 5 | Issue allocated stock | events/core.py:484 |
| POST | /events/\<id\>/inventory/\<aid\>/return | 5 | Return unused stock | events/core.py:506 |
| POST | /events/\<id\>/inventory/\<aid\>/consume | 5 | Mark stock consumed | events/core.py:535 |

### Other domains
| Method | Path | Min role | Description | File |
|---|---|---|---|---|
| POST | /conduct/rules | 10 | Create conduct rule | conduct/core.py:38 |
| GET | /conduct/rules | 1 | List rules | conduct/core.py:85 |
| GET | /conduct/rules/\<id\>/versions | 1 | Rule version history | conduct/core.py:100 |
| POST | /conduct/sign | 1 | Sign current conduct rules | conduct/core.py:117 |
| GET | /conduct/signatures/\<id\> | 5 | Staff signature records | conduct/core.py:160 |
| GET | /conduct/compliance | 5 | Compliance overview | conduct/core.py:182 |
| POST | /disputes | 1 | File a dispute | disputes/core.py:61 |
| POST | /disputes/\<id\>/claim | 5 | Manager claims dispute | disputes/core.py:121 |
| POST | /disputes/\<id\>/resolve | 5 | Resolve dispute | disputes/core.py:143 |
| POST | /disputes/\<id\>/dismiss | 5 | Dismiss dispute | disputes/core.py:168 |
| GET | /disputes | 1 | List disputes | disputes/core.py:192 |
| POST | /suggestions | 1 | Submit suggestion | suggestions/core.py:48 |
| GET | /suggestions | 5 | List suggestions | suggestions/core.py:119 |
| GET | /suggestions/\<id\> | 5 | Get suggestion | suggestions/core.py:140 |
| POST | /suggestions/\<id\>/review | 5 | Review suggestion | suggestions/core.py:159 |
| POST | /feedback | 1 | Submit guest feedback | feedback/core.py |
| GET | /feedback | 5 | List feedback | feedback/core.py |
| POST | /equipment | 5 | Create equipment record | equipment/core.py:36 |
| GET | /equipment | 1 | List equipment | equipment/core.py:61 |
| PATCH | /equipment/\<id\> | 5 | Edit equipment | equipment/core.py:74 |
| POST | /equipment/\<id\>/disable | 5 | Retire equipment | equipment/core.py:99 |
| POST | /equipment/\<id\>/maintenance | 5 | Log maintenance | equipment/core.py:116 |
| POST | /equipment/\<id\>/safety-check | 1 | Log safety check | equipment/core.py:162 |
| GET | /judge/alerts | 10 | List open judge alerts | judge/routes.py:26 |
| POST | /judge/alerts/\<id\>/acknowledge | 10 | Acknowledge alert | judge/routes.py:55 |
| GET | /notifications/inbox | 1 | Personal notification inbox | notifications/core.py:35 |
| POST | /notifications/\<id\>/mark-read | 1 | Mark notification read | notifications/core.py:49 |
| GET | /notifications | 5 | All notifications | notifications/core.py:66 |
| POST | /calendar | 5 | Create calendar entry | calendar_view/core.py:86 |
| GET | /calendar | 1 | List calendar entries | calendar_view/core.py:132 |
| POST | /calendar/\<id\>/disable | 5 | Disable entry | calendar_view/core.py:150 |
| GET | /dashboard/* | 10 | Owner dashboard (10 endpoints) | dashboard/core.py |
| GET | /health | public | Health check for load balancers | app/__init__.py |

---

## 7. THE SILENT JUDGE

The judge is an anti-theft and anomaly detection system. It runs silently in the background —
staff don't know it's watching, and that's intentional. It writes `JudgeAlert` rows that only
the owner can see. No alert is ever shown to the staff member being flagged.

### What it watches

**Weekly analysis — consumption-to-revenue ratios (`flask judge run-weekly`):**

For each inventory item with a `JudgeBaseline`, the engine computes how much of that item was
consumed in the period vs how much revenue was generated. The baseline says something like:
"Tusker Lager should consume 5 cases per KSh 100,000 of bar revenue, ±20%."

If actual consumption deviates from the expected ratio beyond the tolerance, a `RATIO` alert fires:

```
"Tusker Lager: consumed 48 units, expected ~20 units (140% deviation vs 20% tolerance)"
```

This catches bartenders giving away drinks or diverting stock. The judge stays dormant until
real payment data exists — it only runs ratio analysis when `SUM(payments.amount) > 0` for
the period.

**Daily analysis — spoilage spikes (`flask judge run-daily`):**

For items flagged `is_watch_list=True`, the engine checks daily spoilage. If spoilage exceeds
the spike threshold (currently 10 units as a conservative placeholder), a `SPOILAGE_SPIKE`
alert fires. This catches suspicious disposal of stock.

**Other automatic alerts (fired inline by business logic, not by the judge engine):**

- `CASH_SHORTFALL_PATTERN` — three consecutive cash shortfalls by the same staff member
- `MPESA_FLAGGED` — M-Pesa payment flagged as unverified during reconciliation
- `BANK_FLAGGED` — bank transfer flagged during reconciliation
- `VOID_ABUSE` — waiter void rate is 2× the team average (from `analytics.py`)
- `SAFE_COUNT_MISMATCH` — period close detects gap between POS total and physical safe count

All are fired via `fire_alert_if_absent()` — idempotent, so the same anomaly doesn't create
a flood of duplicate alerts.

### What "baseline" means

A `JudgeBaseline` is a human-set ratio: "this item should consume X units per Y units of business driver." Example: `expected_ratio=0.5`, `driver_unit="per KSh 10k revenue"` means "0.5 kg of cooking oil consumed per KSh 10,000 of restaurant revenue."

Baselines are NOT learned by the system. They are seeded by the owner/manager using their own knowledge of the business. The judge reads them and flags deviations — it does not update them. Calibrate them conservatively (wide tolerance) at launch. Tighten over time as you accumulate real data.

### Alert lifecycle

```
OPEN → ACKNOWLEDGED (owner has seen it) → RESOLVED (issue investigated + addressed)
                                         → DISMISSED (false positive, owner dismissed it)
```

`ACKNOWLEDGED` just means the owner tapped "I see this." `RESOLVED` means the underlying
issue was addressed. `DISMISSED` is for false positives — the judge was wrong, or the anomaly
was explained. Only the owner can acknowledge/dismiss/resolve alerts.

### The override flow

When a manager needs to do something that looks like an anomaly (void an entire table's order
because a food order was wrong, approve a large cash adjustment), they record a reason in the
notes field of the relevant action. The audit log captures their username and the reason. The
judge will still fire an alert if the threshold is crossed — the owner then sees the alert and
can dismiss it with confidence knowing the audit log explains it.

---

## 8. THE SIX SECURITY CATEGORIES (Phase B Summary)

Phase B was an adversarial security review run against 453 tests across 6 categories.
13 production bugs were caught and fixed.

### Category 1 — Business Logic
**What was tested:** Tab balance manipulation (negative amounts, double-close), payment idempotency, wristband credit forfeit, booking state machine violations, inventory manipulation.
**Bugs caught:** Tab balance could briefly show wrong value under concurrent requests; wristband forfeit was not atomic.
**Residual risk:** The tab balance derivation formula is correct but not transaction-isolated — under very high concurrency (>50 concurrent writes to the same tab), two writes could interleave. At hotel scale this is not a realistic risk.

### Category 2 — Auth & Authorization
**What was tested:** JWT tampering, role escalation, cross-user data access, kill-switch effectiveness, PIN brute force.
**Bugs caught:** One endpoint was checking role from JWT claims instead of reloading from DB — the kill-switch did not apply to it.
**Residual risk:** JWT tokens remain cryptographically valid for their full lifetime after deactivation. The application-layer kill-switch handles this, but a compromised JWT used in the first millisecond after deactivation could succeed.

### Category 3 — Data Integrity & Concurrency
**What was tested:** Wristband number uniqueness under race conditions, duplicate payment submission, concurrent stock movements.
**Bugs caught:** Wristband numbering without `SELECT FOR UPDATE` could issue the same band number twice.
**Residual risk:** SQLite in development mode does not enforce row-level locking the same way Postgres does. Concurrency tests pass on SQLite but the production guarantee comes from Postgres.

### Category 4 — Information Leaks
**What was tested:** Username enumeration via timing attacks, error messages revealing internal state, owner-only data visible to managers.
**Bugs caught:** Login endpoint revealed whether a username existed via slightly different response times. Fixed by always running the dummy hash computation even for nonexistent users.
**Residual risk:** Some error messages include field names that could reveal schema structure to an attacker with API access.

### Category 5 — Operational & Disaster Recovery
**What was tested:** Audit log atomicity (the Cat 5.1 sweep), backup completeness, alert deduplication.
**Bugs caught:** 33 files had audit log writes outside the business transaction — audit log could be written even if the business write failed, or missing if the server crashed between commits.
**How fixed:** The Cat 5.1 sweep unified all audit log writes into the same commit as the business write. See Pattern 2 (atomic writes) for the canonical shape.

### Category 6 — Human Attacks & Collusion
**What was tested:** Social engineering, PIN sharing, manager-waiter collusion, off-books sales.
**No code bugs caught** — these are human threats, not code vulnerabilities.
**Documented in:** `HUMAN_THREATS.md` — a plain-English runbook for the owner covering what the system can detect, what it cannot, and what human controls are required.

---

## 9. OPERATIONAL DESIGN

### The audit chain
Every action writes an `AuditLog` row. Each row includes a SHA-256 hash of its own content plus the previous row's hash. If anyone edits or deletes a row in the database directly, every subsequent hash becomes invalid. Run `flask audit verify-chain` to confirm integrity. The chain does not prevent tampering — it detects it.

### Daily backups
`flask system backup` creates a full backup. On SQLite (dev): copies the database file. On Postgres (prod): runs `pg_dump`. Configure this as a cron job pointing to a USB drive or a remote location. DEPLOY.md has the cron schedule.

### The three-way reconciliation
At end of day, `GET /finance/reconciliation` assembles:
1. **Receipts**: what the POS recorded as revenue, broken down by payment method (cash, M-Pesa, card, bank transfer).
2. **Cash**: what staff actually handed over vs what the POS expected.
3. **Stock**: open judge alerts for the period (spoilage, ratio anomalies).

Any gap between (1) and (2) is a cash shortfall. Any gap between (2) and (3) is potential stock leakage. The three-way report makes both visible in one screen.

`POST /finance/close-period` locks the day. It records the physical safe count, computes the difference from the POS total, and fires a `SAFE_COUNT_MISMATCH` JudgeAlert if the gap exceeds the threshold. Once a period is closed, the records for that day are frozen.

### The "trust for 12 hours" model
The system trusts that a waiter's POS entries are honest for approximately one shift (8-12 hours). The manager verifies at end of shift. The judge verifies weekly across all shifts. This three-tier check (immediate, daily, weekly) is the intended rhythm. No single point of failure — a waiter can lie on a single shift, but systematic patterns across shifts get caught by the judge.

### The judge as asynchronous safety net
The judge does not block transactions. A bartender can serve a drink. The stock movement is written. The payment is recorded. Hours or days later, the judge looks at the ratio and flags an anomaly. This is intentional — blocking every transaction for real-time analysis would make the system unusable at the bar. The judge is the accountability layer, not the gatekeeper.

---

## 10. DEPLOYMENT STATE & READINESS CHECKLIST

### Ready for production deployment
- [x] Full application factory with environment-specific config (dev/testing/production)
- [x] Flask-Migrate with all schema migrations tracked in git (`migrations/versions/`)
- [x] Argon2 password and PIN hashing (production-grade KDF)
- [x] JWT authentication with kill-switch on every endpoint
- [x] TLS/HTTPS config documented with Nginx (self-signed cert for LAN, valid for 10 years)
- [x] Waitress WSGI server config documented
- [x] Cron schedule for daily/weekly jobs documented in DEPLOY.md
- [x] `.env.production.example` template with all required env vars
- [x] `flask system backup` command operational
- [x] `flask audit verify-chain` operational
- [x] 453 tests passing (453 passed, 1 skipped, zero regressions)

### Deliberately deferred
- [ ] **Frontend apps** — parked until payment integrations are sandbox-verified. Three apps planned: staff tablet PWA, owner phone app, gate screen.
- [ ] **Real data seeding** — the current seed script creates synthetic test data. Production requires the owner to seed real menu items, real staff accounts, real baselines.
- [ ] **M-Pesa Daraja sandbox verification** — `docs/MPESA_SANDBOX_TESTING.md` has the runbook. Requires Safaricom developer account + Cloudflare Tunnel.
- [ ] **Bank socket verification** — `docs/BANK_SOCKET_ACTIVATION.md` has the runbook. TODO markers remain in `bank_transfer.py` for exact API endpoint paths.
- [ ] **Card gateway verification** — `docs/CARD_GATEWAY_ACTIVATION.md` has the runbook. TODO markers remain for all three providers.
- [ ] **Postgres migration test** — development runs SQLite; production runs Postgres. The schema should migrate cleanly but a dry run on a test Postgres instance before go-live is recommended.
- [ ] **Judge baselines calibration** — the default baselines are conservative placeholders. They need 30-60 days of real operational data before they become useful signal.

### 7-step deployment runbook reference
Full steps in DEPLOY.md. Summary:
1. Set `.env` (FLASK_ENV=production, SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL)
2. `flask db upgrade` — apply all migrations
3. `flask seed` — load roles, departments, default users
4. Seed domain data (resources, event types, conduct rules, holidays)
5. Configure TLS + Nginx
6. Configure cron for daily/weekly jobs + backup
7. Run one KSh 1 live payment transaction per gateway before enabling for staff

---

## 11. GLOSSARY

**Tab** — A running bill for a customer visit. Balance = SUM(charges) − SUM(payments). Never closed with a positive balance.

**Wristband / Band** — Entry token for a day visitor. Numbered sequentially per day, resets at midnight. Activates a BAND-type Tab with a 3,000 entry-fee credit.

**Idempotency key** — A unique string stored with every write. If the same key arrives twice, the second write is silently ignored and the existing record is returned. Prevents duplicate payments from retried network requests.

**Append-only ledger** — A table with no UPDATE or DELETE endpoint. Corrections are new rows. Stock movements, payments, charges, and audit logs are all append-only.

**Dormant socket** — A payment integration that is fully built but gated by environment variables. Returns a plain-English error when env vars are missing. Activates automatically when vars are set.

**STK Push** — Safaricom Daraja cashier-initiated payment. Cashier enters customer's phone + amount. Customer's phone receives a PIN prompt. Customer approves. Money moves.

**C2B (Customer-to-Business)** — Safaricom's auto-receive mechanism. Customer pays the resort's shortcode or till number directly. Safaricom POSTs a callback to our server.

**IPN (Instant Payment Notification)** — Card gateway callback. Gateway calls our `/finance/card/callback` endpoint after a customer completes payment to confirm the transaction.

**JudgeAlert** — An anomaly detected by the judge engine or flagged inline by business logic. Owner-only visibility. Statuses: OPEN → ACKNOWLEDGED → RESOLVED / DISMISSED.

**JudgeBaseline** — A human-set consumption-to-revenue ratio for an inventory item. The judge compares actual consumption against the baseline and flags deviations.

**Reconciliation** — The process of verifying that recorded payments match an external source (Safaricom statement, bank statement, physical safe count). PaymentReconciliation rows track MATCHED / UNMATCHED / FLAGGED status.

**Pending Payments** — Payments recorded but not yet matched against an external source. Visible via `GET /finance/mpesa/pending` (M-Pesa and card) and `GET /finance/bank/pending` (bank transfers).

**Kill-switch** — The `is_active=False` flag on a User record. Every protected endpoint re-fetches the user from the database and checks this flag. Setting it to False denies access immediately, regardless of JWT validity.

**Period close** — `POST /finance/close-period`. Locks the day's records. Records the physical safe count. Fires a JudgeAlert if the count doesn't match the POS total.

**Hash chain** — The AuditLog's tamper-detection mechanism. Each row includes a SHA-256 hash of its own content plus the previous row's hash. A broken chain proves tampering.

**Tier** — In the wristband/gate context, "Tier" is a placeholder term for a pricing level (standard, VIP entry fee). Currently unused but the data model accommodates it.

**Actor** — In audit log context: the `actor` field on AuditLog. For human actions, this is the `username`. For automated actions, it's a descriptive string: `"judge"`, `"daraja"`, `"bank_sms"`, `"card_gateway"`.

---

## 12. WHERE TO FIND THINGS

**If you want to understand the authentication system:**
→ `app/auth/routes.py` (login flows, PIN lifecycle)
→ `app/utils/auth_decorators.py` (the kill-switch decorator)
→ `app/utils/auth.py` (lockout logic, active/unlocked check)

**If you want to understand the payment data model:**
→ `app/models/payment.py` (Payment, PaymentMethod enum)
→ `app/models/payment_reconciliation.py` (reconciliation status)
→ `PAYMENTS_DESIGN.md` (full design rationale and all three sockets)

**If you want to understand the tab balance derivation:**
→ `app/services/tab.py` (the formula lives here)
→ `app/pos/tabs.py` (GET /tabs/:id calls this)

**If you want to understand the audit chain:**
→ `app/models/audit_log.py` (the chain hashing logic)
→ `tests/test_security_category_5.py` (atomicity tests)
→ `app/cli/system.py` (the verify-chain CLI command)

**If you want to understand the judge:**
→ `app/judge/engine.py` (ratio and spoilage analysis)
→ `app/models/judge_baseline.py` (how baselines are structured)
→ `app/services/judge_alerts.py` (the fire_if_absent helper)
→ `HUMAN_THREATS.md` (what the judge cannot catch)

**If you want to understand the M-Pesa Daraja integration:**
→ `app/finance/mpesa_daraja.py` (OAuth caching, STK Push, C2B handler, Flask routes)
→ `docs/MPESA_SANDBOX_TESTING.md` (how to test with Safaricom sandbox)

**If you want to understand the bank socket:**
→ `app/finance/bank_transfer.py` (SMS forwarder, three bank APIs, Flask routes)
→ `docs/BANK_SOCKET_ACTIVATION.md` (activation runbook)

**If you want to understand the card gateway:**
→ `app/finance/card_gateway.py` (Pesapal/DPO/Cellulant, IPN handler, Flask routes)
→ `docs/CARD_GATEWAY_ACTIVATION.md` (activation runbook)

**If you want to understand the wristband gate system:**
→ `app/gate/core.py` (issue, deactivate, forfeit, reconciliation routes)
→ `app/services/gate.py` (the sequential band number allocator)
→ `app/models/wristband.py` (the data model)

**If you want to understand the booking lifecycle:**
→ `app/bookings/core.py` (state machine transitions)
→ `app/models/booking.py` (VALID_BOOKING_TRANSITIONS, base_total snapshot)

**If you want to run the system locally:**
→ `CLAUDE.md` (project context, commands, invariants)
→ `DEPLOY.md` (production deployment steps)
→ `CLI_REFERENCE.md` (all `flask` commands)
→ `.env.example` (required environment variables)
