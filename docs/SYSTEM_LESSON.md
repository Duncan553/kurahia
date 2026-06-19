# How Kurahia Works — A Lesson for the Developer Who Built It

This is not documentation. This is a lesson. You built every line of this system.
Now you need to understand it well enough to explain it cold in an interview.
Let us walk through it piece by piece.

---

## 1. The Big Picture

Kurahia is a resort management system for Waterfront Country Club in Juja, Kenya.
It runs everything: gate entry, wristbands, food and drink orders, payments, inventory,
staff management, bookings, and financial reconciliation. The whole system is one Flask
backend (Python) that exposes a JSON API, plus two React frontends that consume it --
one for employees (waiters, kitchen, gate, managers) and one for the owner (dashboards,
finance, approvals). Both frontends are Progressive Web Apps (PWAs) installed on tablets
and phones on the resort's local network.

The architecture is simple on purpose. The Flask backend at `/home/wachira/kurahia/app/`
is the single source of truth. It owns the database, enforces every business rule, and
controls who can do what. The employee PWA at `employee_pwa/` and the owner PWA at
`owner_pwa/` are just screens. They show data and send requests. They never make
decisions -- every decision (can this user do this? is the stock sufficient? is this tab
closable?) happens in Python on the server. If you ripped out both frontends and used
`curl` to call the API, the system would still enforce every rule. That is the point.

---

## 2. How Data Flows (A Real Example)

Let us trace a real scenario end to end: **a waiter opens a table, takes an order,
sends it to the kitchen, the kitchen marks it ready, the waiter serves it, and the
customer pays.**

### Step 1: Waiter opens a table

The waiter taps "+ New Table" on the WaiterTabsScreen
(`employee_pwa/src/screens/WaiterTabsScreen.tsx`, line 80).

**Frontend:** The `openMut` mutation (line 47) fires:
```ts
api.post<Tab>('/tabs', { reference: "Table 7", idempotency_key: idem })
```

**Backend:** The request hits `POST /tabs` in `app/pos/tabs.py` (line 60).
The `@require_active_user` decorator runs first -- it checks the JWT token, then
loads the user from the database and verifies `is_active` is still `True`.
If the user was fired 10 seconds ago, they are blocked here.

The endpoint creates a new `Tab` row (`app/models/tab.py`) with `status=OPEN`,
writes an audit log entry, commits, and returns `201` with the tab ID.

**Frontend:** On success (line 51), the query cache for `['my-tabs']` is invalidated
(so the tab list refreshes), and the waiter navigates to the tab detail screen.

### Step 2: Waiter selects menu items

On WaiterTabDetailScreen (`employee_pwa/src/screens/WaiterTabDetailScreen.tsx`),
two queries fire in parallel:

1. **Tab data** (line 66): `GET /tabs/{tabId}` -- fetches the tab's charges,
   payments, orders, and derived balance.
2. **Menu items** (line 72): `GET /menu/items` -- fetches the active menu.
   The `select` transform (line 78) filters to only KITCHEN and BAR items.

The waiter taps items on the menu grid. Each tap calls `addItem()` (line 164),
which updates local React state (`draft`) -- a simple object mapping `menu_item_id`
to quantity. **No API call happens yet.** This is purely frontend state.

### Step 3: Waiter sends the order

The waiter taps "Send Order". The `sendMut` mutation (line 108) fires two API calls
back to back:

```ts
// 1. Create the order (DRAFT status)
const { data: order } = await api.post('/orders', {
  tab_id: tabId,
  items: [{ menu_item_id: "abc", quantity: 2 }, ...]
})
// 2. Immediately send it (DRAFT → SENT)
await api.post(`/orders/${order.id}/send`)
```

**Backend -- Create** (`app/pos/orders.py`, line 49): The endpoint does several things:
- Checks idempotency (line 68): if this `idempotency_key` was already used, returns the
  existing order instead of creating a duplicate.
- For each item, loads the `MenuItem`, checks it is active, runs a stock pre-check
  against recipe ingredients (lines 100-112), and creates an `OrderItem` with:
  - `unit_price_snapshot` = the menu item's current price (frozen at order time)
  - `prep_station_snapshot` = KITCHEN, BAR, or NONE (frozen at order time)

Why snapshot? Because if the owner changes the menu price tomorrow, this order still
shows the price the customer saw today. History is frozen. Live values are derived.

**Backend -- Send** (`app/pos/orders.py`, line 132): This is where money enters the picture.
- The order status changes from DRAFT to SENT.
- For **every** OrderItem, a `Charge` row is created (`app/models/charge.py`):
  `amount = quantity * unit_price_snapshot`.
- Items with `prep_station_snapshot = NONE` (like spa services) skip the queue and
  are immediately marked SERVED.
- Items with KITCHEN or BAR routing stay PENDING -- they appear in the prep queue.

### Step 4: Kitchen sees the order

The kitchen screen polls `GET /kitchen/queue` (`app/pos/queues.py`, line 64).
This returns all `OrderItem` rows where `prep_station_snapshot = "KITCHEN"` and
`status` is PENDING or RECEIVED, sorted oldest first. Each item shows its age
in seconds so the kitchen can prioritize.

The chef taps "Received" on an item. The frontend calls:
```
POST /order-items/{item_id}/receive
```

**Backend** (`app/pos/orders.py`, line 243): The state machine validates the
transition (PENDING -> RECEIVED is allowed, per `VALID_TRANSITIONS` in
`app/models/order_item.py` line 32). The item's `received_at` timestamp is set.
Only kitchen staff or managers can do this -- checked by `_can_operate_station()`.

### Step 5: Kitchen marks it ready

The chef finishes cooking and taps "Ready":
```
POST /order-items/{item_id}/ready
```

**Backend** (`app/pos/orders.py`, line 262): Two important things happen here:
1. **Inventory consumption** (`consume_order_item()` at line 277): The system looks
   up the menu item's recipe (`RecipeLine` rows in `app/models/recipe_line.py`),
   calculates how much of each ingredient was used, and creates negative
   `StockMovement` rows. Stock is never stored as a number -- it is always
   `SUM(StockMovement.change_amount)`.
2. **Waiter notification** (`_notify_waiter_ready()` at line 276): An in-app
   notification is created for the waiter who took the order, plus a Web Push
   notification fires. The waiter sees it as a blinking alert on their screen
   (`WaiterTabsScreen.tsx`, line 101).

### Step 6: Waiter serves it

The waiter picks up the food and taps "Served":
```
POST /order-items/{item_id}/serve
```

**Backend** (`app/pos/orders.py`, line 283): Status changes to SERVED. Then
`_maybe_complete_order()` (line 419) checks if ALL items in this order are now
in terminal states (SERVED or CANCELLED). If yes, the whole order status becomes
FULLY_SERVED.

### Step 7: Customer pays

The waiter enters the payment amount and method on the tab detail screen. The
`payMut` mutation (line 127 in WaiterTabDetailScreen.tsx) fires:
```
POST /tabs/{tabId}/payments { method: "MPESA", amount: "1500", mpesa_code: "QHK..." }
```

**Backend** (`app/pos/payments.py`, line 20): A `Payment` row is created. The
response includes the new tab balance, calculated by `get_tab_balance()` in
`app/services/tab.py`:

```python
balance = SUM(charges.amount) - SUM(payments.amount)
```

This balance is **never stored**. It is computed fresh every time. That is a core
design principle: live values are derived from append-only records.

### Step 8: Tab closes

When balance reaches zero (or below), the "Close Table" button appears. The waiter
taps it:
```
POST /tabs/{tabId}/close
```

**Backend** (`app/pos/tabs.py`, line 123): `is_tab_closable()` checks two things:
1. Balance <= 0 (no outstanding money)
2. Every OrderItem is SERVED or CANCELLED (nothing stuck in the kitchen)

If both pass, the tab status becomes CLOSED.

**That is the full data flow. Seven models touched. Nine API calls. Every step
audited. Every price frozen. Every balance derived.**

---

## 3. State Management -- What It Means and How Kurahia Uses It

State management answers one question: **where does the app keep data that it
needs to remember between renders?**

In Kurahia, two tools handle this, and each has a different job.

### Zustand -- The In-Memory Box

Zustand is a tiny state library. Think of it as a JavaScript object that lives
in memory for the entire session. Any component can read from it or write to it.
When the data changes, every component that reads it re-renders automatically.

**The authStore** (`employee_pwa/src/stores/authStore.ts`) is the clearest example.
Here is what it stores:

```ts
{
  user: { id: "abc", username: "wachira", role_level: 5, department: "Kitchen" },
  accessToken: "eyJhbG...",     // the JWT token for API calls
  isAuthenticated: true,
  setupToken: null,             // only used during first-time PIN setup
}
```

**How login fills it:** When the user logs in (`LoginScreen.tsx`, line 43), the
mutation's `onSuccess` callback does this:

```ts
const claims = decodeJWT(data.access_token)  // read claims from the JWT payload
setAuth(
  { id: claims.sub, username, role_level: claims.role_level, department: claims.department },
  data.access_token,
)
```

`setAuth` is a Zustand action defined in the store (line 28):
```ts
setAuth: (user, accessToken) =>
  set({ user, accessToken, isAuthenticated: true, setupToken: null })
```

This replaces the entire auth state in one shot. Every component that reads
`isAuthenticated` or `user` re-renders.

**How components read it:** The `AuthGate` component (`employee_pwa/src/components/AuthGate.tsx`,
line 14) reads one value:

```ts
const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
if (!isAuthenticated) return <Navigate to="/pin" replace />
```

That selector `(s) => s.isAuthenticated` means: "give me only the `isAuthenticated`
field, and only re-render me when THAT field changes." This is efficient -- if the
username changes but `isAuthenticated` stays `true`, this component does not re-render.

**How logout clears it:** `clearAuth()` (line 34) sets everything back to `null`:
```ts
clearAuth: () =>
  set({ user: null, accessToken: null, isAuthenticated: false, setupToken: null })
```

The axios interceptor calls `clearAuth()` when a token refresh fails
(`employee_pwa/src/lib/axios.ts`, line 61), which kicks the user to `/login`.

**Why Zustand and not React Context?** Zustand is simpler. No Provider wrappers.
No re-render cascades. You can read the store from outside React (the axios
interceptor does this -- `useAuthStore.getState().accessToken` at line 14).
Context cannot do that.

### TanStack Query (React Query) -- The Server Data Cache

Zustand holds client-side state (who is logged in). TanStack Query holds
server-side state (what the API returned).

The difference matters. Client state is under your control -- you set it, you
clear it. Server state is someone else's truth -- you fetch it, cache it, and
re-fetch it when it might be stale.

**Example: the menu items query** (`WaiterTabDetailScreen.tsx`, line 72):

```ts
const { data: items = [], isLoading: menuLoading } = useQuery<MenuItem[]>({
  queryKey: ['menu-items'],
  queryFn: () => api.get<MenuItem[]>('/menu/items').then(r => r.data),
  refetchInterval: 30_000,
  refetchIntervalInBackground: false,
  select: (all) => all.filter(i => i.prep_station === 'KITCHEN' || i.prep_station === 'BAR'),
})
```

What each piece does:

- `queryKey: ['menu-items']` -- a unique label for this cached data. If another
  component uses the same key, they share the same cache entry. No duplicate
  network requests.
- `queryFn` -- the function that actually calls the API. TanStack Query calls it
  automatically when the data is needed.
- `refetchInterval: 30_000` -- re-fetch every 30 seconds. If the manager adds a
  new menu item, all waiter screens see it within 30 seconds without a page refresh.
- `select` -- transforms the data AFTER caching. The cache holds all menu items;
  this component only sees KITCHEN and BAR items. Another component using the same
  `['menu-items']` key could select different items without a second API call.
- `isLoading` -- `true` while the first fetch is in flight. You use this to show
  skeleton placeholders.

**How cache invalidation works:** When the waiter sends an order, the mutation's
`onSuccess` callback (line 117) does:

```ts
qc.invalidateQueries({ queryKey: ['tab', tabId] })
qc.invalidateQueries({ queryKey: ['my-tabs'] })
```

`invalidateQueries` marks those cache entries as stale. TanStack Query immediately
re-fetches them in the background. The UI updates when the fresh data arrives.
You do not manually update the cached data -- you just say "this is stale now"
and let the library handle the rest.

**Why two tools?** Zustand for things the client controls (auth state, UI
preferences). TanStack Query for things the server controls (tabs, orders, menu
items, inventory). Mixing them would be a mess -- you would be manually syncing
server data that TanStack Query already syncs for you.

---

## 4. How Frontend Talks to Backend

Every API call from both frontends goes through one file:
`employee_pwa/src/lib/axios.ts` (the owner PWA has an identical copy at
`owner_pwa/src/lib/axios.ts`).

### The axios instance (lines 6-10)

```ts
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL as string,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})
```

- `baseURL` -- every call is relative to this. `api.get('/tabs')` actually hits
  `http://192.168.1.x:5000/tabs` (the Flask server on the LAN).
- `withCredentials: true` -- tells the browser to send the httpOnly refresh token
  cookie with every request. The access token is in-memory (Zustand); the refresh
  token is in a cookie the browser manages.

### Request interceptor -- adding the JWT token (lines 13-17)

```ts
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

Every outgoing request gets the access token injected as `Authorization: Bearer eyJ...`.
This is why components never need to think about tokens -- they just call
`api.get('/tabs')` and the interceptor handles auth.

### Response interceptor -- handling 401 errors (lines 28-81)

This is the most complex part, and it solves a real problem: **what happens when
the access token expires mid-session?**

The access token is short-lived (default 15 minutes). When it expires, the
backend returns `401`. The interceptor catches this and:

1. Sends `POST /auth/refresh` (line 52) with the httpOnly refresh cookie.
2. The backend issues a new access token.
3. The interceptor updates the Zustand store with the new token (line 55).
4. The **original failed request is retried** with the new token (line 57).

The user never sees the refresh. Their request just takes a fraction longer.

**The queue pattern (lines 20-26):** If three requests fail simultaneously because
the token expired, you do not want three refresh calls. The interceptor uses a
queue: the first 401 triggers a refresh. Subsequent 401s during the refresh
are queued and retried once the new token arrives.

**The 403 handler (lines 69-77):** If the backend returns `403`, the user's account
was deactivated (the kill switch). The interceptor clears auth, shows a toast
message, and redirects to `/login`. There is no recovery from this -- the owner
or manager deliberately disabled this account.

---

## 5. The Models -- Your Database Tables

All models live in `app/models/`. Here are the key ones and how they connect.

### User (`user.py`)
Every human in the system. Stores username, password hash (argon2), PIN hash,
`is_active` (kill switch), `failed_attempts` + `locked_until` (brute-force
protection). Links to a `Role` and optionally a `Department`.

### Role (`role.py`)
Named permission level. `level` is the number that matters: owner=10, manager=5,
staff=1. The code checks `actor.role.level >= MANAGER_LEVEL` -- never role names.
This means you can add new roles (head_chef=6, supervisor=4) without changing code.

### Tab (`tab.py`)
A running bill for a customer visit. Types: WALK_IN, VILLA, BAND. Status: OPEN
or CLOSED. **Balance is never stored** -- always derived from charges minus
payments. Links to the user who opened/closed it.

### Order (`order.py`)
A round of items placed against a tab. States: DRAFT -> SENT -> FULLY_SERVED (or
CANCELLED). One tab can have many orders. Every order has an `idempotency_key`
(unique in the DB) so duplicate submissions are caught.

### OrderItem (`order_item.py`)
One line on an order. The state machine drives the kitchen/bar workflow:
```
PENDING -> RECEIVED -> READY -> SERVED    (normal path)
PENDING -> CANCELLED                       (waiter cancels before kitchen sees it)
RECEIVED -> CANCELLED                      (kitchen cannot make it)
READY -> CANCELLED                         (manager-only, triggers stock reversal)
```
`unit_price_snapshot` and `prep_station_snapshot` freeze the menu item's values
at order time. Even if you change the price or routing later, old orders keep
their original values.

### Charge (`charge.py`)
Append-only record of what the tab owes. One charge per OrderItem, created when
the order is SENT. Amount = quantity * unit_price_snapshot. Cancellations add a
**negative** charge row (a reversal) -- the original row is never modified.
Tab balance = SUM(charges) - SUM(payments).

### Payment (`payment.py`)
Append-only record of money received. Methods: CASH, CARD, MPESA, BANK_TRANSFER.
`received_by_id` tracks which staff member collected it (important for cash
reconciliation). M-Pesa codes are captured as-typed; verification is a separate
reconciliation step.

### MenuItem (`menu_item.py`)
What the venue sells. `price` is Decimal. `prep_station` determines routing:
KITCHEN (food queue), BAR (drinks queue), or NONE (no queue, served immediately).
Each item belongs to a Department. `is_active` = soft delete.

### RecipeLine (`recipe_line.py`)
One ingredient line in a menu item's recipe. Links a `MenuItem` to an
`InventoryItem` with a quantity and unit. When the kitchen marks an order item
READY, the system reads the recipe lines and deducts stock.

### InventoryItem (`inventory_item.py`)
Physical stock tracked in a department. Units are free-text (kg, litre, bottle).
`is_watch_list` = tighter tolerance + daily count. `pack_size` + `pack_unit`
handle the spirits math (1 bottle = 750ml; recipes use ml, stock tracks bottles).
Stock level is NEVER stored -- it is `SUM(StockMovement.change_amount)`.

### Wristband (`wristband.py`)
Gate entry token for day visitors. One band = one customer. `band_number` is
unique per `issue_date`. Links to a Payment (the KSh 3,000 entry fee) and a Tab
(the band's spending tab). Status: ACTIVE -> DEACTIVATED (customer leaves) or
FORFEITED (end-of-day sweep, unused credit becomes resort revenue).

### GateEntry (`gate_entry.py`)
Links a wristband to an arrival event. `head_count` is always 1 (one band, one
person). Exists as a separate model so arrival records are append-only even if
the band status changes later.

### How they connect

```
User ---< Tab ---< Order ---< OrderItem >--- MenuItem ---< RecipeLine >--- InventoryItem
              \---< Charge
              \---< Payment ---< PaymentReconciliation
              \---  Wristband --- GateEntry
```

A User opens a Tab. The Tab collects Orders. Each Order has OrderItems that
reference MenuItems. When items are cooked, RecipeLines determine how much
InventoryItem stock to deduct. Charges and Payments accumulate on the Tab.
Wristbands link to both a Tab and a Payment.

---

## 6. Security -- How the System Protects Itself

### The Kill Switch (`require_active_user`)

Every protected endpoint uses `@require_active_user` instead of Flask-JWT's
standard `@jwt_required()`. The decorator lives at `app/utils/auth_decorators.py`.

Here is what it does on EVERY request:

1. Validates the JWT token (signature + expiry) -- standard Flask-JWT.
2. Loads the `User` from the database by the JWT's `sub` claim.
3. Calls `check_active_and_unlocked()` (`app/utils/auth.py`, line 36):
   - Is `user.is_active` True? If False -> 403, session over.
   - Is `user.locked_until` in the future? If yes -> 403 with time remaining.

**Why re-check on every request?** Because a JWT is a signed piece of paper.
Once issued, it is valid until it expires. If a manager fires a waiter at 2:00 PM
and their token does not expire until 2:15 PM, the waiter has 15 minutes of
access without the kill switch. With the kill switch, deactivation takes effect
on the next request -- within milliseconds.

### Role Levels

Roles use numeric levels, not names:
- **Owner (10):** Can do everything. Can deactivate managers.
- **Manager (5):** Can manage staff, view all queues, run reconciliation,
  cancel READY items. Can deactivate staff but not other managers.
- **Staff (1):** Can take orders, serve items, record payments. Cannot access
  manager-only endpoints.

The hierarchy is enforced strictly: you can only deactivate or reset lockout for
users whose `role.level` is **lower** than yours. An owner (10) can deactivate a
manager (5). A manager (5) cannot deactivate another manager (5).

### How JWT Works (Simple Version)

When you log in, the backend creates two tokens:

1. **Access token** -- short-lived (15 minutes). Contains your user ID,
   `role_level`, and `department`. Stored in Zustand (JavaScript memory).
   Sent with every API call via the `Authorization` header. When it expires, the
   axios interceptor silently refreshes it.

2. **Refresh token** -- longer-lived. Stored in an httpOnly cookie (JavaScript
   cannot read it, which protects it from XSS attacks). Used only for
   `POST /auth/refresh` to get a new access token.

The backend decodes the JWT on each request to know who you are. But it does NOT
trust the JWT alone -- it re-loads your user from the database (the kill switch)
to check `is_active` and lockout status.

### Anti-Enumeration

The login endpoints (`app/auth/routes.py`) use a timing trick: when a username
does not exist OR the user is inactive, the server runs a dummy argon2 hash
verification (line 66) so the response time is the same as a real password check.
An attacker cannot tell whether a username exists by measuring how fast the
server responds.

### Lockout

After N failed login attempts (`FAILED_ATTEMPTS_LOCKOUT` in config), the account
is locked for `LOCKOUT_MINUTES`. The lockout is timed -- it clears itself. A
higher-ranked user can also clear it early via
`POST /auth/reset-lockout/{user_id}`.

### Audit Log

Every write operation logs to the `AuditLog` (`app/models/audit_log.py`). The
log is **hash-chained**: each entry's `entry_hash` covers the previous entry's
hash. If anyone modifies or deletes a past entry, every subsequent hash becomes
invalid. You can verify the chain with `flask audit verify-chain`.

---

## 7. The Money Flow

Here is how Kenya Shillings move through the system, from gate entry to
end-of-day reconciliation.

### Gate Entry -> Wristband -> Tab Credit

A day visitor arrives. Gate staff issue a wristband via `POST /gate/issue-band`.
The `issue_band()` service (`app/services/gate.py`, line 89) does this atomically:

1. **Allocates band number** -- uses `SELECT FOR UPDATE` to lock the counter row,
   preventing two staff from issuing the same number simultaneously.
2. **Opens a BAND tab** with reference "Band #7".
3. **Creates a Payment** of KSh 3,000 (the entry fee) on that tab.

That single Payment record does double duty: it is both the revenue record (the
resort received 3,000) and the tab credit (the guest has 3,000 to spend). The
tab balance is now **-3,000** (negative means the customer has credit).

### Wristband Spending

The waiter looks up the wristband number (`GET /gate/bands/7`), gets the
`tab_id`, and opens the tab detail screen. From here, ordering works exactly
like a walk-in table -- the waiter adds items, sends the order, charges are
created.

With each charge, the balance moves toward zero:
```
Start:    -3,000 (credit from entry fee)
Charge:   +1,200 (lunch)
Balance:  -1,800 (still has credit)
Charge:   +800  (drinks)
Balance:  -1,000 (still has credit)
```

If the guest spends more than KSh 3,000, the balance goes positive (they owe
money). They pay the difference before leaving.

### Walk-In Spending

Walk-in customers do not get wristbands. The waiter opens a WALK_IN tab, takes
orders, and the charges accumulate from zero:
```
Start:    0
Charge:   +1,500 (food)
Balance:  +1,500 (customer owes)
Payment:  -1,500 (MPESA)
Balance:  0 (settled, tab can close)
```

### End of Day -- Forfeit

At closing time, a manager runs `POST /gate/forfeit-day` (or the CLI
`flask gate close-day`). This does:

1. Finds all ACTIVE wristbands for today.
2. For each one, checks the tab balance. If negative (unused credit), that money
   becomes resort revenue -- no refund.
3. Sets band status to FORFEITED, closes the tab.
4. Runs the **judge** -- theft detection signals:
   - Does total gate revenue match `bands_issued * 3,000`? If not, someone may
     have pocketed an entry fee.
   - Does any gate staff member have a forfeit rate 3x higher than the day
     average? If so, they may be issuing bands without collecting payment.

### Cash Reconciliation

For CASH payments, reconciliation happens per staff member:

1. A manager uses `GET /reports/staff-cash` to see how much cash a waiter
   collected during their shift.
2. The waiter counts their physical cash and hands it in.
3. A `CashReconciliation` row (`app/models/cash_reconciliation.py`) records:
   - `expected_amount` -- sum of their CASH payments (derived, then frozen).
   - `actual_amount` -- what they physically handed in.
   - `difference` -- if negative (SHORT), the staff member is short on cash.

### M-Pesa Reconciliation

M-Pesa codes (like "QHK7B2X9") are captured as-typed when the payment is
recorded. Reconciliation happens later:

- **Manual:** The cashier compares typed codes against the Safaricom statement
  and creates `PaymentReconciliation` rows (MATCHED, UNMATCHED, or FLAGGED).
- **Automated (when activated):** The M-Pesa Daraja API socket
  (`app/finance/mpesa_daraja.py`) receives real-time callbacks from Safaricom
  and auto-matches.

### Card and Bank Transfer

Same pattern: capture the reference at payment time, reconcile later. Three
payment sockets are built but dormant until activated via environment variables:
- M-Pesa Daraja (`docs/MPESA_SANDBOX_TESTING.md`)
- Bank Transfer via SMS/API (`docs/BANK_SOCKET_ACTIVATION.md`)
- Card Gateway via Pesapal/DPO (`docs/CARD_GATEWAY_ACTIVATION.md`)

### The Core Accounting Rule

Every money movement in the system follows one rule:

**Tab balance = SUM(charges.amount) - SUM(payments.amount)**

This is computed fresh every time by `get_tab_balance()` in `app/services/tab.py`.
It is never stored. Charges are append-only (corrections are negative rows).
Payments are append-only. You cannot edit or delete either. This makes the
financial trail tamper-evident -- if money goes missing, the audit log and the
append-only ledgers will show where.

---

## Summary: The Patterns You Should Be Able to Explain

If someone asks you how this system works, you should be able to explain these
five things clearly:

1. **Derived state:** Stock levels and tab balances are never stored. They are
   always computed from append-only ledger rows. This prevents desync bugs and
   makes the system auditable.

2. **Frozen history:** Prices, prep stations, and expected cash amounts are
   snapshotted at write time. Tomorrow's changes never rewrite yesterday's facts.

3. **State machines:** OrderItems move through defined transitions (PENDING ->
   RECEIVED -> READY -> SERVED). The code rejects invalid transitions with
   plain-English error messages.

4. **Kill switch:** The backend re-checks `is_active` on every single request,
   not just at login. JWT alone is never trusted.

5. **Two kinds of frontend state:** Zustand for auth (client-owned data).
   TanStack Query for API data (server-owned data, cached and auto-refreshed).

You built all of this. Now you can explain all of it.
