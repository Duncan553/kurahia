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

---

## 8. How Inventory Works (the chain)

Inventory is a chain of events. Every stock change is an append-only
`StockMovement` row. The current stock level is never stored -- it is always
`SUM(StockMovement.change_amount)`. That sum IS the truth. Here is the full
lifecycle, from creating an item to the system automatically requesting more.

### Step 1: Manager creates an InventoryItem

A manager calls `POST /inventory/items` (handled in `app/inventory/items.py`,
line 67). The endpoint creates an `InventoryItem` row
(`app/models/inventory_item.py`, line 13) with these key fields:

```python
InventoryItem(
    name="Chicken",
    unit="kg",                 # free-text — never hardcoded
    department_id=kitchen.id,  # belongs to a department
    reorder_level="5.0",       # system watches this threshold
    is_watch_list=True,        # tighter tolerance + daily judge checks
)
```

At this point, stock is zero -- no movements exist yet.

### Step 2: Manager records a Purchase

The manager buys 10 kg of chicken for KSh 5,000 and records it via
`POST /inventory/purchases` (`app/inventory/purchases.py`, line 273).

Two things happen atomically inside `begin_nested()` (line 327):

**1. A StockMovement is created (positive = stock in):**
```python
StockMovement(
    item_id=item.id,
    change_amount=qty,                   # +10 (positive — stock coming in)
    reason=MovementReason.PURCHASE.value, # "PURCHASE"
    actor_id=actor.id,
    idempotency_key=f"purchase-mv-{idem_key}",
)
```

**2. Weighted-average cost updates** (lines 340-346):
```python
# new_cpu = 5000 / 10 = KSh 500/kg
new_cpu = cost / qty
if old_stock > 0 and item.cost_per_unit is not None:
    # Blend: (old_stock * old_price + new_qty * new_price) / total_qty
    item.cost_per_unit = (old_stock * old_cpu + qty * new_cpu) / (old_stock + qty)
else:
    item.cost_per_unit = new_cpu  # first purchase — no blending needed
```

**Why weighted average?** If the last purchase was KSh 450/kg and this one is
KSh 500/kg, the system blends them. This gives the judge accurate cost data
for detecting overspend, and gives the owner true inventory value on the
dashboard. A simple "last price" would swing wildly on a single expensive
purchase.

The `Purchase` row also stores `receipt_photo_path` -- every purchase requires
a receipt photo (line 289 rejects without it). This is anti-theft: a manager
cannot inflate quantities or invent purchases without a physical receipt.

### Step 3: Kitchen marks an order item Ready -- auto-consumption fires

This is where inventory meets POS. When a chef taps "Ready" on a dish:

```
POST /order-items/{oi_id}/ready
```

**Backend** (`app/pos/orders.py`, line 262): After the state machine validates
the transition (RECEIVED -> READY), line 277 calls:

```python
consume_order_item(oi, actor)   # auto-deduct recipe ingredients
```

`consume_order_item()` lives at `app/services/consumption.py`, line 28.
Here is exactly what it does:

1. **Load the recipe** (line 33): Queries `RecipeLine` rows for this
   `menu_item_id`. A RecipeLine (`app/models/recipe_line.py`) links a
   `MenuItem` to an `InventoryItem` with a quantity and unit. Example:
   "Grilled Chicken" recipe has a line: `0.3 kg Chicken`.

2. **Calculate how much to deduct** (lines 41-49):
   ```python
   order_qty = Decimal(str(oi.quantity))        # e.g. 2 (customer ordered 2)
   recipe_qty = Decimal(str(line.quantity))      # e.g. 0.3 kg per dish
   stock_qty = inv_item.recipe_to_stock(recipe_qty)  # convert ml→bottles if pack item
   deduct = -(stock_qty * order_qty)             # -(0.3 × 2) = -0.6 kg
   ```

3. **Write a StockMovement** (lines 56-63):
   ```python
   StockMovement(
       item_id=inv_item.id,
       change_amount=deduct,                     # -0.6 (negative — stock out)
       reason=MovementReason.SALE.value,          # "SALE"
       actor_id=actor.id,
       idempotency_key=f"sale-{oi.id}-{inv_item.id}",
   )
   ```

The idempotency key `sale-{order_item_id}-{inventory_item_id}` means
double-marking an item READY is harmless -- the second attempt finds the
existing movement and skips (line 53).

**Pack-size math:** For spirits, the recipe says "50ml vodka" but stock tracks
bottles (750ml). `recipe_to_stock()` (`app/models/inventory_item.py`, line 56)
divides: `50 / 750 = 0.0667 bottles`. This way the recipe is human-readable
(ml) while stock is countable (bottles).

4. **If no recipe exists** (line 37): `_notify_no_recipe()` sends a notification
   to the head chef saying "Order sold for 'X' but no recipe is set. Stock cannot
   be auto-deducted." The system does NOT guess -- it flags the gap.

### Step 4: Stock drops below reorder_level -- low-stock notification

After every SALE movement, `_check_low_stock()` runs
(`app/services/consumption.py`, line 101):

```python
current = get_current_stock(inv_item.id)           # SUM of all movements
if current >= Decimal(str(inv_item.reorder_level)):
    return                                          # still above threshold — nothing to do

# Stock is low — notify the owner
db.session.add(Notification(
    recipient_user_id=owner.id,
    subject=f"Low stock: {inv_item.name}",
    body=f"{inv_item.name} has dropped to {current} {inv_item.unit} "
         f"(reorder level: {inv_item.reorder_level} {inv_item.unit}). Please reorder.",
    ...
))
```

**Dedup** (line 122): If the same item was flagged in the last 24 hours, it
skips. This prevents 50 "low stock: Chicken" notifications on a busy Saturday
when every order further depletes the same ingredient.

### Step 5: Nightly auto-draft creates DRAFT purchase requests

Every night at 23:00 EAT, a cron job runs `flask inventory auto-draft`
(`app/cli/inventory.py`, line 68). It scans every active InventoryItem:

```python
for item in items:
    current = get_current_stock(item.id)
    if current >= item.reorder_level:
        continue   # stock is fine — skip

    # Skip if there's already an open request for this item
    existing = PurchaseRequest.query.filter(
        item_id == item.id,
        status IN ('DRAFT', 'PENDING'),
    ).first()
    if existing:
        continue

    # Suggest buying enough to reach 2x reorder level
    suggested_qty = (item.reorder_level * 2) - current
    PurchaseRequest(
        item_id=item.id,
        quantity=suggested_qty,
        status="DRAFT",            # not PENDING — needs manager review first
        system_generated=True,     # flagged so the UI can show "auto-suggested"
        requested_by_id=None,      # system, not a person
    )
```

**Why `reorder_level * 2`?** If reorder is 5 kg and current stock is 2 kg, the
suggestion is `(5 * 2) - 2 = 8 kg`. This aims to refill past the reorder point
with some buffer, so the next restock does not happen tomorrow.

### Step 6: Manager reviews, submits, owner approves

The approval chain lives in `app/inventory/purchases.py`:

1. **Manager sees DRAFT requests** via `GET /inventory/purchase-requests?status=DRAFT`
   (line 37). The `system_generated` flag tells the UI these are auto-suggestions.

2. **Manager submits** via `POST /inventory/purchase-requests/{id}/submit`
   (line 143): Changes status from DRAFT to PENDING. The manager can adjust the
   quantity before submitting.

3. **Manager proposes a budget** via `POST /inventory/purchase-requests/{id}/propose`
   (line 197): Attaches `estimated_cost` and notes.

4. **Owner approves** via `POST /inventory/purchase-requests/{id}/approve`
   (line 232): Only role level 10+. Changes status to APPROVED. The owner
   cannot approve their own request (line 244 -- anti-collusion).

5. **Manager records the actual purchase** via `POST /inventory/purchases`
   (line 273): Links back to the `purchase_request_id`, marks the request
   FULFILLED (line 321), and creates the StockMovement that increases stock.

### The full chain in one sentence

**Create item -> Purchase (stock in) -> Customer orders -> Kitchen marks Ready
-> Auto-consume (stock out) -> Low-stock alert -> Auto-draft request -> Manager
submits -> Owner approves -> Purchase (stock in again).** A loop. Every step is
an append-only record. Nothing is ever deleted or overwritten.

---

## 9. How the Judge Works (silent theft detection)

The judge is a silent anomaly detector. It does not accuse anyone. It does not
block operations. It watches numbers in the background and creates alerts when
something looks wrong. The owner sees these alerts on the Alerts screen in the
owner PWA (`owner_pwa/src/screens/AlertsScreen.tsx`). Staff never see them.

### When it runs

Two schedules, triggered by CLI commands (which cron calls):

- **Daily** (`flask judge run-daily` / `flask system run-daily`):
  Checks watch-list items for spoilage spikes. Fast -- only looks at today.

- **Weekly** (`flask judge run-weekly` / registered in `app/judge/routes.py`,
  line 84): Runs ratio analysis (consumption vs revenue), cost variance
  (expected vs actual ingredient spend), and budget checks. Covers the last
  7 days by default.

Both are defined in `app/judge/engine.py`.

### What it checks

#### RATIO (weekly -- `run_weekly()`, line 191)

"If we made KSh 100,000 in revenue this week, we should have used roughly X kg
of chicken." The expected ratio comes from `JudgeBaseline` rows
(`app/models/judge_baseline.py`), seeded by `flask judge seed-baselines`.

```python
# Example baseline: Chicken — 0.5 kg per KSh 10,000 revenue, 20% tolerance
consumption = _get_period_consumption(item.id, period_start, period_end)
expected = baseline.expected_ratio * (revenue / Decimal("10000"))
deviation_pct = abs(consumption - expected) / expected * 100

if deviation_pct > baseline.tolerance_percent:
    _fire_alert(item.id, "RATIO", severity, desc, period_start, period_end)
```

If chicken consumption is 40% above expected, someone might be taking chicken
home. Or the recipe is wrong. Either way, the owner should look.

#### COST_VARIANCE (weekly -- `_run_cost_variance()`, line 83)

Different angle on the same problem. Instead of comparing consumption to
revenue, this compares **expected ingredient cost** (from served orders *
recipe quantities * cost_per_unit) against **actual consumption cost**
(from stock movements * cost_per_unit).

```python
# Expected: what recipes say should have been used for all served orders
# Actual: what stock movements say WAS used
deviation_pct = abs(actual_cost - expected_cost) / expected_cost * 100
COST_VARIANCE_THRESHOLD = Decimal("15")   # 15% tolerance
HIGH_THRESHOLD = Decimal("25")            # above this → HIGH severity
```

If expected cost is KSh 20,000 but actual is KSh 28,000 (40% over), that is
either waste, theft, or a recipe that needs updating. All three are worth the
owner's attention.

#### SPOILAGE_SPIKE (daily -- `run_daily()`, line 246)

Checks watch-list items (high-value or high-theft-risk). If spoilage for a
single item exceeds the spike threshold in one day, it fires an alert.

```python
watch_items = InventoryItem.query.filter_by(
    is_watch_list=True, is_active=True, is_staff_food=False
).all()
for item in watch_items:
    spoilage = _get_spoilage(item.id, period_start, period_end)
    if spoilage > SPIKE_THRESHOLD:
        _fire_alert(item.id, "SPOILAGE_SPIKE", AlertSeverity.MEDIUM, desc, ...)
```

**Why this matters:** A common theft pattern is logging real food as "spoiled"
to cover the gap. If 20 kg of chicken is logged as spoiled in one day, that
deserves a question.

#### CASH_SHORTFALL_PATTERN

Detected during cash reconciliation (not in the judge engine directly, but
flagged by the auto-close health check). When a `CashReconciliation` has
status SHORT, it appears as a problem in `check_day_health()`
(`app/services/auto_close.py`, line 49). Repeated shortfalls by the same
cashier are visible in the reconciliation history.

#### VOID_ABUSE

Handled through the order cancellation audit trail. Every cancel writes to the
audit log (`app/pos/orders.py`). The dashboard aggregates void rates per staff
member. Abnormally high rates are surfaced in the owner's analytics.

#### MPESA_FLAGGED / BANK_FLAGGED

When a `PaymentReconciliation` has status FLAGGED
(`app/models/payment_reconciliation.py`), it means an M-Pesa code or bank
reference could not be verified. This shows up in the auto-close health check
(`app/services/auto_close.py`, line 58) and blocks auto-close until resolved.

#### BUDGET_EXCEEDED (weekly -- `_run_budget_exceeded()`, line 150)

Checks every active `Budget` row. If a department has spent more than 100% of
its monthly budget, the judge fires an alert:

```python
if spent > budget_amt:
    _fire_alert(
        item_id=None,
        alert_type="BUDGET_EXCEEDED",
        severity=HIGH if spent > budget_amt * 1.2 else MEDIUM,
        description=f"{dept_name} department has spent {pct}% of its monthly budget...",
    )
```

### How alerts are created -- `fire_alert_if_absent` (idempotent)

Every alert goes through one function: `fire_alert_if_absent()`
(`app/services/judge_alerts.py`, line 18).

```python
def fire_alert_if_absent(alert_type, description_key, **alert_fields):
    # Check: is there already an OPEN alert of this type with this key in description?
    existing = JudgeAlert.query.filter(
        alert_type == alert_type,
        status == OPEN,
        description LIKE '%{description_key}%',
    ).first()
    if existing:
        return existing, False   # already exists — do nothing

    alert = JudgeAlert(alert_type=alert_type, status=OPEN, **alert_fields)
    db.session.add(alert)
    return alert, True           # new alert created
```

**Why idempotent?** The cron might run twice. A developer might run the judge
manually then the cron fires 10 minutes later. Without this guard, you get
duplicate alerts. The dedup key is `(alert_type, description_key, OPEN status)`
-- if an OPEN alert already mentions this item for this type, no new row is
created.

### Where the owner sees alerts

The owner PWA has an Alerts screen (`owner_pwa/src/screens/AlertsScreen.tsx`)
that calls `GET /judge/alerts` (`app/judge/routes.py`, line 26). This endpoint
is **owner-only** (line 20 checks `role.level >= 10`). Staff never see judge
alerts -- the system is silent to them by design.

The owner can filter by status (OPEN / ACKNOWLEDGED / ALL) and acknowledge
alerts via `POST /judge/alerts/{id}/acknowledge` (line 55), which sets
`acknowledged_at` and `acknowledged_by_id`.

### Alert lifecycle

```
OPEN → ACKNOWLEDGED → RESOLVED (or DISMISSED)
```

OPEN alerts with HIGH severity block auto-close (see section 10). This forces
the owner to look at them before the day can close.

---

## 10. How Auto-Close Works

At the end of every business day, the system checks whether the day was
"clean" enough to close automatically. If yes, it locks the day's records and
sends a quiet summary. If not, it alerts the owner with the specific problems.

### Business day cutoff

The business day does NOT end at midnight. It ends at a configurable hour,
defaulting to 6:00 AM EAT (East Africa Time, UTC+3). This is set in
`SystemSetting` and read by `_get_start_hour()` in
`app/services/business_day.py` (line 31).

**Why 6 AM?** Because the resort runs late. A customer paying their bar tab at
1:00 AM belongs to yesterday's business day, not today's. The 6 AM cutoff
means "yesterday" runs from 6:00 AM yesterday to 6:00 AM today. Any payment
at 2:00 AM still counts as yesterday's revenue.

The function `business_day_bounds()` (line 55) converts a date string to UTC
start/end timestamps:

```python
def business_day_bounds(date_str: str) -> tuple[datetime, datetime]:
    d = dt.strptime(date_str, "%Y-%m-%d")
    start_local = d.replace(hour=start_hour, tzinfo=EAT)  # 6:00 AM EAT
    start_utc = start_local.astimezone(timezone.utc)       # 3:00 AM UTC
    return start_utc, start_utc + timedelta(hours=24)      # 24-hour window
```

### The auto-close trigger

The CLI command `flask system auto-close` (`app/cli/system.py`, line 202)
runs via cron shortly after the cutoff:

```python
now = datetime.now(timezone.utc)
prev = business_day_for(now - timedelta(hours=1))   # which business day just ended?
start, end = business_day_bounds(prev.strftime("%Y-%m-%d"))
closed, problems = auto_close_day(start, end)
```

It subtracts 1 hour from now to find the business day that just ended, then
calls `auto_close_day()`.

### The 5 health checks

`check_day_health()` (`app/services/auto_close.py`, line 33) returns a list
of problems. Empty list = all green. Here are the 5 conditions:

**1. Every CASH payment is reconciled** (lines 38-46):
```python
unreconciled = Payment.query.filter(
    method == CASH,
    created_at_utc in [day_start, day_end),
    id NOT IN reconciled_payment_ids,
).count()
if unreconciled > 0:
    problems.append(f"{unreconciled} cash payment(s) not reconciled")
```
If a waiter collected KSh 3,000 cash but no `CashReconciliation` row covers
that payment, the day cannot close. Someone needs to count the cash.

**2. No cash shortfalls** (lines 49-55):
```python
shortfalls = CashReconciliation.query.filter(
    created_at_utc in [day_start, day_end),
    status == SHORT,
).all()
for s in shortfalls:
    problems.append(f"Cash shortfall KSh {abs(s.difference)} ({cashier.username})")
```
A reconciliation with status SHORT means the physical cash was less than
expected. The owner needs to know whose drawer was short and by how much.

**3. No flagged payment reconciliations** (lines 58-64):
```python
flagged = PaymentReconciliation.query.filter(
    created_at_utc in [day_start, day_end),
    status == FLAGGED,
).count()
```
A FLAGGED M-Pesa or bank payment means the reference code could not be
verified. It might be a typo, or it might be a fake payment.

**4. No open disputes** (lines 67-71):
```python
open_disputes = Dispute.query.filter(
    status IN (OPEN, UNDER_REVIEW),
).count()
```
A customer or staff dispute that has not been resolved. The day should not be
locked while money or service complaints are unresolved.

**5. No unresolved HIGH judge alerts** (lines 74-79):
```python
high_alerts = JudgeAlert.query.filter(
    status == OPEN,
    severity IN (HIGH,),
).count()
```
The judge found something serious (e.g., cost variance above 25%). The owner
must acknowledge or resolve it before the day locks.

### ALL GREEN -- auto-close

If `check_day_health()` returns an empty list, `auto_close_day()`
(`app/services/auto_close.py`, line 114) creates a `PeriodClose` row:

```python
PeriodClose(
    period_start_utc=day_start,
    period_end_utc=day_end,
    closed_by_id=owner.id,
    safe_count=expected,
    expected_total_cash=expected,
    difference=Decimal("0"),
    status=PeriodCloseStatus.BALANCED.value,
    notes="Auto-closed (all green)",
    idempotency_key=f"autoclose-{day_start.date().isoformat()}",
)
```

Then it sends a quiet notification to the owner (line 160):
```
"Day closed · KSh 85,000 revenue · all reconciled"
```

The idempotency key `autoclose-{date}` means running the command twice on the
same day is harmless -- the second run finds the existing PeriodClose (line 118)
and returns immediately.

### ANY FAIL -- alert the owner

If problems exist, the day is NOT closed. Instead, the owner gets a notification
(line 128):

```
Subject: "Day not auto-closed — needs attention"
Body: "The following issues prevented auto-close:
  • 3 cash payments not reconciled
  • Cash shortfall KSh 1,200 (waiter_jane)
  • 1 unresolved HIGH judge alert"
```

The owner can then investigate, resolve the problems, and manually close via
`POST /finance/close-period` (which always works regardless of health checks).

**Why this design?** The owner should not have to babysit clean days. If
everything checks out, the system closes quietly. But if something is wrong,
the owner is notified with the exact problems -- no guessing, no "something
went wrong", just a bullet list of what needs attention.

---

## 11. How the Frontend Knows What to Show

The employee PWA serves every role -- waiter, kitchen, bar, gate, spa, manager
-- from one app. But a kitchen worker should not see waiter tables, and a waiter
should not see inventory management. The nav filtering happens in one file:
`employee_pwa/src/layouts/AppLayout.tsx`.

### The NavItem interface (line 200)

Every navigation item is an object:

```ts
interface NavItem {
  id: string
  path: string
  label: string
  Icon: () => ReactElement
  badge?: boolean
  visible: (level: number, dept: string | null) => boolean
}
```

The `visible` function is the gatekeeper. It takes the user's role level (from
the JWT claims in Zustand) and their department name, and returns `true` or
`false`. The layout renders only items where `visible` returns `true`:

```ts
const visibleItems = NAV_ITEMS.filter((item) => item.visible(roleLevel, department))
```

That single line (AppLayout.tsx, line 394) is why different users see different
nav items.

### The `deptIs()` helper (line 183)

```ts
function deptIs(dept: string | null, ...keywords: string[]): boolean {
  if (!dept) return false
  const d = dept.toLowerCase()
  return keywords.some((k) => d.includes(k))
}
```

This does case-insensitive substring matching. `deptIs(dept, 'kitchen')` returns
true for "Kitchen", "Head Kitchen", or "kitchen-prep". It is intentionally fuzzy
because department names are owner-configurable (stored in the DB, not hardcoded).
The owner might call it "Kitchen" or "Food Prep" -- as long as it contains
"kitchen", the routing works.

### The `isStation()` helper (line 192)

```ts
function isStation(dept: string | null): boolean {
  return deptIs(dept, 'kitchen', 'bar', 'front-of-house', 'waiter', 'restaurant',
    'spa', 'gym', 'wellness', 'water', 'activit', 'aqua', 'villa', 'housekeep')
}
```

Station departments work on **shared tablets** bolted to a counter. The kitchen
has one tablet showing the queue. The bar has one tablet. These are not personal
devices -- multiple staff share them throughout a shift.

**Why this matters:** Personal items like Clock, Alerts, and Profile should not
appear on a shared kitchen tablet. Nobody clocks in from the kitchen tablet --
they use their phone. So `isStation()` returns `true` for these departments,
and personal nav items use it to hide themselves:

```ts
const personal = (level: number, dept: string | null) => level >= 3 || !isStation(dept)
```

This means:
- **Level 5+ (managers):** Always see personal items. Managers have their own
  tablets.
- **Level 3-4 (gate/front desk):** Always see personal items. Gate staff use
  dedicated devices that are both personal and station.
- **Level 1 (staff) on a station device:** Personal items hidden. The kitchen
  tablet shows only the kitchen queue.
- **Level 1 (staff) on a non-station device:** Personal items visible. A
  maintenance worker on their phone sees Clock, Alerts, Profile.

### How department drives what you see

Here is how the `visible` function filters for key roles:

**Kitchen staff** (department contains "kitchen"):
```ts
{ id: 'kitchen', visible: (_level, dept) => deptIs(dept, 'kitchen') }
```
They see: Kitchen queue. That is it (plus Clock/Alerts if on a personal device).
They do NOT see waiter tables, inventory management, bar queue, or anything
else. Their tablet is a single-purpose kitchen display.

**Waiters** (department contains "waiter", "restaurant", "front-of-house"):
```ts
{ id: 'waiter', visible: (_level, dept) =>
    deptIs(dept, 'waiter', 'restaurant', 'food', 'beverage', 'f&b', 'front-of-house') }
```
They see: Tables (the waiter POS screen). On a personal phone, also Clock and
Alerts.

**Bar staff** (department contains "bar"):
```ts
{ id: 'bar', visible: (_level, dept) => deptIs(dept, 'bar') }
```
They see: Bar queue. Same idea as kitchen.

**Gate staff** (level 3-4):
```ts
{ id: 'gate-hub', visible: (level) => level >= 3 && level <= 4 }
{ id: 'checkin',  visible: (level) => level >= 3 && level <= 4 }
{ id: 'band-lookup', visible: (level) => level >= 3 && level < 5 }
```
Gate staff are not filtered by department keyword -- they are filtered by role
level. Level 3-4 is the "front desk / gate supervisor" range. They see Gate,
Check-In, Band Lookup, plus personal items.

**Managers** (level 5+):
```ts
{ id: 'inventory',   visible: (level) => level >= 5 }
{ id: 'restock',     visible: (level) => level >= 5 }
{ id: 'meals',       visible: (level) => level >= 5 }
{ id: 'maintenance', visible: (level) => level >= 5 }
{ id: 'manager',     visible: (level) => level >= 5 }
{ id: 'schedule',    visible: (level) => level >= 5 }
```
Managers see everything staff-level screens show for their department, PLUS
management tools: Inventory, Restock, Staff Meals, Maintenance, the Manager
dashboard, and Schedule. These are level-gated, not department-gated, because
a manager of any department needs these tools.

### Station auto-redirect (line 412)

When a station device loads, the default route is `/clock`. But clock-in on a
shared kitchen tablet makes no sense. So the layout auto-redirects based on
department:

```ts
if (location.pathname === '/clock' && roleLevel < 5) {
  if (deptIs(department, 'kitchen'))                          return <Navigate to="/pos/kitchen" replace />
  if (deptIs(department, 'bar'))                              return <Navigate to="/pos/bar" replace />
  if (deptIs(department, 'front-of-house', 'waiter', 'restaurant')) return <Navigate to="/pos/tabs" replace />
  // ... spa, water, villa, gate
}
```

The kitchen tablet logs in and immediately lands on the kitchen queue. No tap
required. The waiter logs in and lands on their tables. Each role gets dropped
on the screen they actually need.

Managers (level 5+) are excluded from this redirect. They land on `/clock`
because they actually use it -- managers clock in from their own tablets.

### Why this design works

1. **One app, many roles.** You do not build separate apps for kitchen, waiter,
   bar, gate, and manager. You build one app and filter the nav. This means one
   codebase, one deploy, one PWA install -- the server-side JWT claims determine
   what the user sees.

2. **Department names are data, not code.** The `deptIs()` function uses
   substring matching against DB-stored department names. The owner can rename
   "Kitchen" to "Food Production" and as long as it still contains "kitchen"
   (or the `deptIs` keywords are updated), routing works. No code change needed.

3. **Station vs personal is a real resort problem.** A kitchen has one tablet
   screwed to the wall. It should show the queue and nothing else. A waiter
   carries a phone -- it should show tables plus their personal clock and
   alerts. `isStation()` solves this split cleanly.

4. **Security is backend-enforced.** The nav filtering is UX convenience, not
   security. If a kitchen worker somehow navigated to `/inventory/count`, the
   backend would reject the request with `403 Manager or above required`. The
   frontend hides what you should not need. The backend blocks what you must
   not access.

---

## 12. How File Uploads Work

The system needs images everywhere: menu item photos, employee profile
pictures, purchase receipt scans, villa gallery shots. All uploads go through
one endpoint in `app/uploads/__init__.py`. Here is how it works, step by step.

### The endpoint: POST /uploads/<category>

The URL has a dynamic segment: `<category>`. This tells the backend WHERE to
save the file. The valid categories are defined in a dictionary (line 24):

```python
UPLOAD_TARGETS = {
    "menu":    "employee_pwa/public/images/menu",
    "profile": "employee_pwa/public/images/profiles",
    "receipt": "employee_pwa/public/images/receipts",
    "villa":   "employee_pwa/public/images/villas",
    "spa":     "employee_pwa/public/images/spa",
    "water":   "employee_pwa/public/images/water",
    "general": "employee_pwa/public/images/uploads",
}
```

So `POST /uploads/menu` saves to the menu folder. `POST /uploads/profile`
saves to the profiles folder. If someone sends `POST /uploads/banana`, the
endpoint rejects it with `400 Unknown category` (line 56). The dictionary is
the allowlist -- nothing else gets through.

### How files are saved

When a valid upload arrives, the endpoint does four things:

**1. Validate the file type** (line 62):
```python
def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
```
`ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}` -- only image formats.
No PDFs, no ZIPs, no `.exe` hiding as a `.jpg`. The check uses the file
extension, not the content type header (which can be spoofed, but the
extension determines what the browser renders).

**2. Check the file size** (lines 65-69):
```python
file.seek(0, os.SEEK_END)   # jump to end of file
size = file.tell()            # tell() gives position = file size in bytes
file.seek(0)                  # rewind for saving
if size > MAX_FILE_SIZE:      # MAX_FILE_SIZE = 5 * 1024 * 1024 = 5MB
    return jsonify({"error": "File too large. Maximum 5MB."}), 400
```
Why `seek` instead of `len()`? Because `request.files['file']` is a stream,
not a byte string. You cannot call `len()` on a stream. Instead, you seek to
the end, ask where you are (that is the size), then rewind so `file.save()`
reads from the beginning.

**3. Generate a UUID filename** (lines 71-72):
```python
ext = file.filename.rsplit(".", 1)[1].lower()        # "photo.JPG" → "jpg"
unique_name = f"{uuid.uuid4().hex[:12]}.{ext}"       # "a1b2c3d4e5f6.jpg"
```
The original filename is thrown away. Why? Two reasons:
- **Collision prevention:** Two staff members uploading `photo.jpg` would
  overwrite each other. UUID filenames are unique.
- **Security:** Original filenames can contain path traversal attacks like
  `../../etc/passwd.jpg`. By generating our own name, the attacker's filename
  is never used in any file path.

**4. Save and return the public path** (lines 73-81):
```python
dest = _upload_dir(category) / unique_name       # e.g. employee_pwa/public/images/menu/a1b2c3d4e5f6.jpg
file.save(str(dest))

public_path = f"/images/{category}/{unique_name}"  # "/images/menu/a1b2c3d4e5f6.jpg"
```
The file is saved to `employee_pwa/public/images/<category>/`. The response
returns the PUBLIC path -- the path the browser uses to load the image. Vite
serves everything in `public/` at the root URL, so `/images/menu/a1b2c3d4e5f6.jpg`
maps directly to the file on disk.

### How the path connects to the database

The response JSON looks like:
```json
{"path": "/images/menu/a1b2c3d4e5f6.jpg", "filename": "a1b2c3d4e5f6.jpg"}
```

The frontend takes that `path` value and saves it to the relevant model:

- **Menu items:** `MenuItem.image_path = "/images/menu/a1b2c3d4e5f6.jpg"`
  (`app/models/menu_item.py`, line 31). The waiter's menu grid uses this path
  in an `<img src={item.image_path}>` tag.

- **Employee profiles:** `EmployeeProfile.photo_path = "/images/profiles/x9y8z7w6v5u4.jpg"`
  (`app/models/employee_profile.py`, line 25). The profile screen and staff
  directory use this.

The path is just a string in the database. The actual file lives in the PWA's
`public/` directory. This is important: if you delete the file but not the
database row, the image breaks. If you delete the database row but not the
file, the file becomes an orphan. Both models store the path, neither owns
the file lifecycle -- that is a deliberate simplicity trade-off for a v1
system.

### Security measures (summary)

1. **Category allowlist** -- only 7 known categories. Unknown = 400.
2. **File type check** -- only jpg, jpeg, png, webp. Everything else = 400.
3. **Size limit** -- 5MB max. Prevents a staff member filling the disk.
4. **UUID filename** -- original filename discarded. Prevents path traversal
   and collisions.
5. **`@require_active_user`** -- kill switch. Fired staff cannot upload.
6. **Audit log** -- every upload is logged with actor, category, and filename.

### How the PWA service worker precaches uploaded images

Here is the key insight: uploaded images are NOT individually precached. The
service worker precaches the **app shell** -- the HTML, CSS, JS bundles, fonts,
and icons that make the app work offline. This is configured in
`vite.config.ts` (line 19):

```ts
injectManifest: {
  globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2,wav}'],
},
```

That `**/*.png` pattern catches any PNG in the `public/` directory at BUILD
time. So if an image was uploaded before the next deploy, it gets precached
in the next service worker update. But images uploaded AFTER the build are
NOT precached -- they load from the network like any dynamic content.

This is fine for a resort on a LAN. The tablets are always connected to the
local server. Menu images load fast over the local network. If the network
drops, the app shell still works (offline-capable), but new images from the
server would not load until the connection returns.

The service worker (`employee_pwa/src/sw.ts`) also registers runtime caching
for the `/menu/items` API route with a NetworkFirst strategy (line 32):
```ts
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/menu/items'),
  new NetworkFirst({
    cacheName: 'menu',
    plugins: [new ExpirationPlugin({ maxEntries: 10, maxAgeSeconds: 3600 })],
  })
)
```
This caches the menu DATA (including `image_path` strings) for 1 hour. The
images themselves are served as static files from Vite's `public/` directory.

---

## 13. How the Frontend Routes Work

The employee PWA is a single-page app. All routing happens in
`employee_pwa/src/main.tsx`. Here is how it is structured.

### React Router setup

The app uses `createBrowserRouter` (line 89) -- React Router v6's data router.
This creates a route tree that looks like a nested folder structure:

```
/login              → LoginScreen        (public)
/pin                → PinEntryScreen      (public)
/pin/setup          → PinSetupScreen      (public)

AuthGate (checks login)
├── /kiosk/*        → Kiosk screens      (no nav chrome)
└── AppLayout (nav bar, sidebar)
    ├── /clock      → ClockScreen        (all staff)
    ├── /schedule   → ScheduleScreen     (all staff)
    ├── /pos/tabs   → WaiterTabsScreen   (dept-filtered)
    ├── /pos/kitchen → KitchenQueueScreen (dept-filtered)
    ├── RoleGate (level 3+)
    │   ├── /gate/hub    → GateHubScreen
    │   └── /gate/issue  → WristbandScreen
    └── RoleGate (level 5+)
        ├── /manager          → ManagerScreen
        ├── /inventory/count  → InventoryCountScreen
        └── /manager/staff    → StaffAccountsScreen
```

### What lazy() does and why

Most screens are loaded with `lazy()` (lines 44-83):

```ts
const ScheduleScreen = lazy(() => import('./screens/ScheduleScreen'))
const ManagerScreen = lazy(() => import('./screens/ManagerScreen'))
```

`lazy()` tells React: "do NOT load this component's JavaScript until someone
actually navigates to its route." This is called **code splitting**.

**Why it matters:** Without lazy loading, the browser downloads ALL screen
code on first load -- the manager screen, inventory screen, gate screen,
every screen -- even if you are a kitchen worker who will never see most of
them. With lazy loading, the kitchen worker's browser only downloads the
kitchen queue code. The manager screen code is never fetched until a manager
navigates to `/manager`.

Notice which screens are NOT lazy (lines 17-23):
```ts
import LoginScreen       from './screens/LoginScreen'
import PinEntryScreen    from './screens/PinEntryScreen'
import PinSetupScreen    from './screens/PinSetupScreen'
import ClockScreen       from './screens/ClockScreen'
```

These are eagerly loaded because EVERY user hits them: login, PIN entry, and
clock-in. Making these lazy would add a visible loading spinner on the first
screen every user sees. Not worth it.

**How Suspense catches the loading state:** When a lazy component is loading,
React needs a fallback to show. The `AuthGate` component
(`employee_pwa/src/components/AuthGate.tsx`, line 17) wraps `<Outlet />` in
`<Suspense>`:

```tsx
return <Suspense fallback={chunkFallback}><Outlet /></Suspense>
```

`chunkFallback` (line 7) is a simple spinner:
```tsx
const chunkFallback = (
  <div className="min-h-screen flex items-center justify-center bg-cream-card">
    <div className="w-8 h-8 rounded-full border-2 border-primary-dark border-t-transparent animate-spin" />
  </div>
)
```

So the user sees a centered spinner for a fraction of a second while the lazy
chunk downloads, then the real screen appears. On the resort LAN, this is
near-instant.

### How AppLayout wraps all routes

The route tree nests staff routes inside `<AppLayout />` (line 109):

```tsx
{
  element: <ErrorBoundary><AppLayout /></ErrorBoundary>,
  children: [
    { path: '/clock',    element: <ClockScreen /> },
    { path: '/schedule', element: <ScheduleScreen /> },
    // ... all staff routes
  ],
}
```

`AppLayout` renders the sidebar nav, the top bar, and an `<Outlet />` where
the child route's component appears. Every screen inside AppLayout gets the
nav chrome automatically. Kiosk routes sit OUTSIDE AppLayout (line 100-105)
because kiosks are customer-facing and should not show the staff nav bar.

The `<ErrorBoundary>` wrapping AppLayout is a React error boundary. If any
screen throws a render error, the boundary catches it and shows a recovery
UI instead of crashing the entire app. This is important for a resort system
-- a bug in one screen should not take down the whole tablet.

### How RoleGate guards work

Some routes need role-level restrictions BEYOND just being logged in. The
`RoleGate` component (`employee_pwa/src/components/AuthGate.tsx`, line 21)
handles this:

```tsx
export function RoleGate({ minLevel }: { minLevel: number }) {
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <EmptyState
        title="You don't have access to this area."
        description="Ask your manager if you think this is a mistake."
        actionLabel="Go back"
        onAction={() => navigate(-1)}
      />
    )
  }
  return <Outlet />
}
```

It reads `role_level` from the Zustand auth store (which got it from the JWT
claims at login). If the user's level is below `minLevel`, they see a locked
icon and a "Go back" button -- not a redirect. This is deliberate: the nav
shell stays visible so the user is not disoriented. They just see "you cannot
access this" inside the content area.

In the route tree, `RoleGate` wraps groups of routes (lines 148-157, 163-181):
```tsx
// Gate routes — level 3+
{ element: <RoleGate minLevel={3} />, children: [
    { path: '/gate/hub', element: <GateHubScreen /> },
    { path: '/gate/issue', element: <WristbandScreen /> },
] },

// Manager routes — level 5+
{ element: <RoleGate minLevel={5} />, children: [
    { path: '/manager', element: <ManagerScreen /> },
    { path: '/inventory/count', element: <InventoryCountScreen /> },
] },
```

**Remember: this is UX, not security.** A determined user could type
`/manager` in the URL bar and the RoleGate would block the UI -- but the
REAL security is the backend. Every API call behind `/manager` checks
`@require_active_user` and role level. Even if the frontend gate broke,
the backend would return `403`.

### How the PIN entry screen gates the main app

The very first thing a user sees is `/pin` -- the PinEntryScreen. The root
route `/` redirects to `/clock` (line 111), but `/clock` is inside `AuthGate`.
If the user is not authenticated, `AuthGate` (line 14-15) redirects to `/pin`:

```tsx
const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
if (!isAuthenticated) return <Navigate to="/pin" replace />
```

The flow is:
1. User opens the app -> hits `/` -> redirects to `/clock`
2. `/clock` is inside `AuthGate` -> not authenticated -> redirects to `/pin`
3. User enters their PIN -> backend returns JWT tokens -> Zustand stores them
4. `isAuthenticated` becomes `true` -> `AuthGate` lets them through
5. User sees `/clock` (or gets auto-redirected to their department screen,
   as described in section 11)

The catch-all route `{ path: '*', element: <LoginScreen /> }` (line 187)
sends any unknown URL to the login screen. So if someone types `/asdf`,
they land on login instead of a blank page.

---

## 14. How Glass Cards Work (the CSS trick)

The app uses a frosted glass effect on panels and cards. This is the same
visual trick Apple uses in macOS and iOS. The code is in
`employee_pwa/src/index.css`, and it is surprisingly simple once you
understand the three ingredients.

### Ingredient 1: backdrop-filter: blur(20px) saturate(160%)

The core of the glass effect is one CSS line (line 123):
```css
backdrop-filter: blur(20px) saturate(160%);
```

`backdrop-filter` applies visual effects to what is BEHIND the element, not
the element itself. Think of it like looking through frosted glass at a
painting -- the painting gets blurry, the glass itself stays sharp.

- **blur(20px)** -- blurs everything behind the panel by 20 pixels. This
  creates the frosted effect. Higher values = more frosted, less see-through.
- **saturate(160%)** -- boosts the color saturation of the blurred content
  by 60%. This is Apple's secret sauce. Without it, the blur looks washed
  out and flat -- like smudged paint. With 160% saturation, the blurred
  colors stay rich and vibrant, which makes the glass feel luminous, alive.
  It is the difference between cheap frosted plastic and expensive crystal.

### Ingredient 2: Ambient gradients behind the glass

Here is the thing most people miss: `backdrop-filter: blur()` blurs whatever
is behind the element. If what is behind it is a flat solid color, blurring a
flat color gives you... the same flat color. The glass looks invisible. No
depth, no texture, no point.

That is why `body::before` (lines 109-118) paints subtle gradients:
```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: -1;
  background:
    radial-gradient(ellipse 60% 50% at 15% 80%, rgba(250, 92, 41, 0.04) 0%, transparent 100%),
    radial-gradient(ellipse 50% 60% at 85% 20%, rgba(66, 49, 44, 0.08) 0%, transparent 100%);
}
```

Two very faint radial gradients: a warm orange glow in the bottom-left corner
and a dark brown glow in the top-right. Both are nearly invisible on their own
(4% and 8% opacity). But when a glass panel sits on top of them, the blur
amplifies these subtle color shifts into visible texture. The glass picks up
a slight warm tint in the bottom-left and a cooler tone in the top-right.

**This is the recipe:** ambient gradients BEHIND + blur + saturate ON TOP =
convincing frosted glass. Remove the gradients and the glass goes flat.

### Ingredient 3: The inset highlight trick

Look at the `box-shadow` on `.glass-card` (lines 127-129):
```css
box-shadow:
  0 8px 32px rgba(0, 0, 0, 0.3),               /* outer shadow — depth */
  inset 0 1px 0 rgba(255, 255, 255, 0.12);      /* inner top highlight */
```

Two shadows working together:
- **Outer shadow** (0 8px 32px, black at 30%): Makes the card float off the
  background. Standard depth cue.
- **Inset top highlight** (inset 0 1px, white at 12%): A thin white line at
  the very top of the card. This simulates light catching the top edge of a
  real glass panel. It is subtle -- 12% opacity -- but it is what makes the
  panel look three-dimensional instead of flat. Without this single pixel of
  light, the card looks like a colored rectangle. With it, your brain reads
  it as a physical surface catching light from above.

### The three glass levels

The CSS defines three levels of glass with decreasing intensity:

**`.glass-card`** -- the strongest glass (line 121):
```css
background: rgba(255, 255, 255, 0.06);     /* very faint white tint */
backdrop-filter: blur(20px) saturate(160%); /* heavy blur + saturation */
border: 1px solid rgba(255, 255, 255, 0.08); /* subtle white border */
```
Used for primary cards -- the main content panels on every screen.

**`.glass-card-sage`** -- medium glass (line 131):
```css
background: rgba(255, 255, 255, 0.04);     /* even fainter tint */
backdrop-filter: blur(16px) saturate(150%); /* less blur, less saturation */
```
Used for secondary panels -- things like list items inside a glass card. The
weaker blur prevents a distracting "glass on glass" effect.

**`.glass-surface`** -- lightest glass (line 141):
```css
background: rgba(255, 255, 255, 0.05);
backdrop-filter: blur(12px) saturate(140%);
border-radius: 0.75rem;                     /* slightly smaller radius */
```
Used for small interactive elements like buttons, input backgrounds, status
badges. Just enough glass to feel part of the system without being heavy.

### Accessibility: prefers-reduced-transparency

The CSS also handles users who have reduced transparency enabled in their OS
(lines 148-152):
```css
@media (prefers-reduced-transparency) {
  .glass-card { background: var(--color-cream-card); backdrop-filter: none; }
  .glass-card-sage { background: var(--color-cream-alt); backdrop-filter: none; }
  .glass-surface { background: var(--color-cream-card); backdrop-filter: none; }
}
```
This turns off the blur entirely and falls back to solid background colors.
The app still works and looks clean -- it just loses the glass effect.

---

## 15. How the Color Palette Tells a Story

The palette is called "Stitch lakeside noir." Every color was chosen to match
the subject matter: a lakeside resort with wooden decks, sunset views, and
warm hospitality. This is not a random dark theme. The colors tell you WHERE
you are.

### The background: #1e100c (warm brownish black)

```css
--color-cream-card: #1e100c;   /* warm dark brown bg */
```

This is NOT a cold gray-black like `#171717` (what you get from Tailwind's
`zinc-900`) or a blue-black like `#0f172a` (Tailwind's `slate-900`). It is a
warm brownish black -- like dark wood or coffee. If you put `#1e100c` next to
`#171717` on screen, you immediately feel the difference. The warm one feels
like an evening lounge. The cold one feels like a code editor.

**Why it matters:** A resort app lives on tablets at poolside bars, lakeside
restaurants, wooden reception desks. Cold tech colors feel alien in that
environment. Warm browns feel natural -- they match the wood, the soil, the
evening light. The staff sees this screen 8 hours a day. It should feel like
it belongs in the building.

### The text: #f9dcd5 (warm off-white)

```css
--color-ink-primary: #f9dcd5;  /* warm off-white text */
```

This is NOT `#DEDEDE` (neutral gray) or `#ffffff` (pure white). It is a warm
peachy off-white. If you squint, it has a faint pink-orange tint. Next to pure
white text, `#f9dcd5` looks softer, easier on the eyes, and -- critically --
it matches the warm background. Cool white text on a warm background fights
itself. Warm text on a warm background feels unified.

The secondary text uses `rgba(227, 190, 180, 0.7)` -- the same warm tone but
at 70% opacity. Tertiary text (labels, timestamps) drops to
`rgba(170, 137, 128, 0.5)` -- a muted warm gray at 50%. Same warmth
throughout. The hierarchy is built with opacity, not hue shifts.

### The accent: #fa5c29 (orange)

```css
--color-primary-main: #fa5c29; /* warm orange accent (use sparingly) */
```

Orange is the only bright color in the system. It is used SPARINGLY:
- Primary action buttons (CTA -- "Send Order", "Issue Band", "Submit")
- The gradient-hero class: `linear-gradient(135deg, #fa5c29, #af3000)`
- Badge counts (unread notifications)

That is it. Orange never appears in body text, secondary buttons, status
colors, or backgrounds. Why? Because a bright accent loses its power if you
use it everywhere. If every button is orange, none of them feel important. By
keeping orange rare, the eye is drawn to it instantly -- "this is the thing
to tap."

**Why orange specifically?** It is the color of a Kenyan sunset over the lake.
It is the color of ripe fruit, warm firelight, terra cotta. It belongs at a
resort in a way that blue (#3b82f6) or purple (#8b5cf6) never would. Blue
says "tech company." Orange says "sunset bar."

### The secondary: #aa8980 (muted warm gray)

```css
--color-ink-tertiary: rgba(170, 137, 128, 0.5);  /* warm tertiary */
```

The muted warm gray (`#aa8980` at 50% opacity) handles secondary text,
timestamps, placeholder text, and subtle dividers. It is warm -- not the cool
`#9ca3af` (Tailwind `gray-400`) you see in most dark themes. It sits
naturally between the dark background and the light text without introducing
a cold note.

### The design principle: "ground in subject matter"

The entire palette follows one principle: **the colors should feel like the
place the app lives in.** This is what designers call "grounding in subject
matter."

- A bank app uses navy blue and white -- trust, authority, clean.
- A fitness app uses neon green on black -- energy, intensity, performance.
- A resort app uses warm browns, peachy whites, and sunset orange -- wood,
  warmth, hospitality, evening light by the lake.

If you took this palette and put it on a hospital app, it would feel wrong.
If you took a hospital's cool blues and put them on this resort system, it
would feel wrong. The colors match the building. That is the point.

### How this connects to the glass effect

The warm palette is what makes the glass cards work. The ambient gradients
behind the glass use `rgba(250, 92, 41, 0.04)` -- a ghost of the orange
accent -- and `rgba(66, 49, 44, 0.08)` -- a ghost of the brown background.
When the glass blurs these warm gradients, the panels pick up a subtle warm
glow that matches everything else. If the palette were cold blue and the
gradients were warm orange, the glass would look muddy and confused. The
warmth is consistent from background to gradient to glass to text. Everything
belongs together.
