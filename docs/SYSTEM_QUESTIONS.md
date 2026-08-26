# SYSTEM_QUESTIONS.md — What can this system actually answer?

> Research date: 2026-08-26. Every claim below was verified against code, not docs.
> Route inventory taken from a live `app.url_map` dump of `create_app("testing")` — **268 routes**.
> All `file:line` references are to paths under `/home/wachira/kurahia/`.

**How to read this**
- ✅ **YES** — an endpoint or CLI command exists today that returns the answer.
- ⚠️ **PARTIAL** — an endpoint returns some of it, but the answer is incomplete or has a caveat.
- ❌ **NO** — the data exists but nothing surfaces it. These land in Section A.

---

## 0. The architectural spine (read this first)

Three ideas explain most of the answers below.

**1. Live values are DERIVED, never stored.** Two keystone functions:

| Live value | Formula | Where |
|---|---|---|
| Stock level | `SUM(StockMovement.change_amount) WHERE item_id = ?` | `app/services/stock.py:18-24` |
| Stock as of a timestamp | same, `+ WHERE timestamp_utc <= as_of` | `app/services/stock.py:41-47` |
| Tab balance | `SUM(Charge.amount) − SUM(Payment.amount)` | `app/services/tab.py:23-33` |
| Equipment service due | `(now − last_service_utc).days >= service_interval_days` | `app/models/equipment.py:47-54` |
| Hours worked | pair CLOCK_IN/CLOCK_OUT chronologically, sum deltas | `app/services/hr.py:144-171` |
| Budget spend | `SUM(Purchase.actual_cost)` joined via `InventoryItem.department_id` | `app/services/finance.py:53-65` |

There is **no `current_stock` column and no `balance` column anywhere**. This is why "what was stock on the 3rd?" is answerable at all — you replay the ledger.

**2. Historical facts are FROZEN at write time.** `OrderItem.unit_price_snapshot`, `CashReconciliation.expected_amount`, `Booking.base_total`, every `AuditLog` row. A menu price change never rewrites yesterday's receipts.

**3. Reversals are new rows, never edits.** A manager refund writes a *negative* `Charge` — `app/pos/orders.py:188` `_reverse_charge()`, called from `refund_item` at `app/pos/orders.py:459`. Cancelling a READY item writes equal positive `StockMovement` rows to undo the deduction — `app/services/consumption.py` `reverse_consumption`. The original rows are never touched.

---

## 1. MONEY

### 1.1 "How much did we take today / this week / this month, and by what method?"
✅ **YES.**
- `GET /finance/dashboard?period=YYYY-MM` — owner only (level 10) — `app/finance/reports.py:323-439`. Returns revenue today/week/month, expenses (purchases + payroll), `profit_month`, budget rows, open shortfalls, open judge alerts.
- `GET /dashboard/overview?period=today|week|month` — manager+ — `app/dashboard/core.py:40-151`. Revenue split **by tab type AND by payment method** in one grouped query (`core.py:62-69`).
- **Source:** `SUM(Payment.amount)` between UTC bounds, grouped by `Payment.method` — `app/services/finance.py:68-81`. Nothing is stored as a "daily total".

### 1.2 "Show me the revenue trend for the last N days"
✅ **YES.** `GET /finance/revenue-history?days=7` (max 90), owner-only — `app/finance/reports.py:37-68`. One `SUM(Payment.amount)` per day, looped in Python.

### 1.3 "Did the money in the safe match what the system says we collected?"
✅ **YES.** `POST /finance/close-period` — `app/finance/reports.py:210-318`. You post `safe_count`; expected = `SUM(CashReconciliation.actual_amount)` for the period (`app/services/finance.py:84-93`); status is BALANCED / SHORT / OVER; a mismatch fires a `SAFE_COUNT_MISMATCH` JudgeAlert (`reports.py:294-307`).

### 1.4 "Which staff member is holding cash they haven't handed in?"
✅ **YES.** Two ways:
- `GET /finance/cash/pending` — `app/finance/cash.py:31`.
- `GET /finance/reconciliation?date=YYYY-MM-DD` — `app/finance/reports.py:73-205` — corner 2 lists `pending_staff` by username plus `unreconciled_amount`.
- **Source:** a payment is reconciled *iff its id appears in the `cash_recon_payments` join table*. `get_staff_pending_cash` at `app/services/finance.py:36-50` does `~Payment.id.in_(reconciled_ids)`. The join table's `payment_id` is the **primary key** (`app/models/cash_reconciliation.py:31`) — so the DB itself makes double-reconciling one payment impossible.

### 1.5 "Who has come up short on cash, and how often?"
✅ **YES.**
- Per-day list with names and amounts: `GET /finance/reconciliation` → `shortfalls[]` — `app/finance/reports.py:114-123`.
- Chronic pattern: `count_staff_shortfalls(staff_id, last_n=3)` — `app/services/finance.py:96-109`. **Caveat:** this helper is a service function; grep shows no HTTP endpoint calls it. See Section A.

### 1.6 "Do the POS receipts, the cash handed in, and the stock records all agree for a given day?"
✅ **YES — this is the flagship report.** `GET /finance/reconciliation?date=YYYY-MM-DD`, manager+ — `app/finance/reports.py:73-205`. Three corners assembled in one response:
1. **Receipts** — revenue by method.
2. **Cash** — expected vs handed in, named shortfalls, named pending staff.
3. **Stock** — open JudgeAlerts whose `period_end` falls in the day.
Then a `gaps[]` array of plain-English sentences and a `balanced` boolean. The code carries an honest comment at `reports.py:111-113` that `recon_diff` reads 0.00 when today's cash simply hasn't been reconciled yet — which is why `unreconciled_amount` (`reports.py:149`) exists as the scope-correct number.

### 1.7 "Can the day close itself if everything is clean?"
✅ **YES.** `flask system auto-close` — `app/cli/system.py:202-217` → `app/services/auto_close.py`. "All green" is five explicit conditions (`auto_close.py:34-80`): no unreconciled cash, no SHORT reconciliation, no FLAGGED payment reconciliation, no open/under-review disputes, no open HIGH judge alerts. If any fail it does **not** close and notifies the owner naming the problem.

### 1.8 "Are we over budget in any department this month? This year?"
✅ **YES.** `GET /finance/budgets/status?period=YYYY-MM` **or** `?period=YYYY` — manager+ — `app/finance/budgets.py:146-200`. The 4-digit-year branch (`budgets.py:166-195`) sums every month's budget and spend per department without any schema change. Also mirrored in `GET /finance/dashboard` → `budgets[]`.
- **Source:** budget amount is stored (`app/models/budget.py:18`); **spend is derived** — `SUM(Purchase.actual_cost)` joined through `InventoryItem.department_id` (`app/services/finance.py:53-65`).

### 1.9 "Which waiter voids the most orders?"
⚠️ **PARTIAL — YES with a definitional caveat.** `GET /finance/anomalies/voids?from=…&to=…`, manager+ — `app/finance/analytics.py:39-78`. Returns per-staff `void_rate_pct`, the house average, and a `flagged` boolean; flagged staff automatically get a `VOID_ABUSE` JudgeAlert.
- **Source:** `get_void_rates` — `app/services/finance.py:112-163`. Flag rule: `total >= 5 and rate > avg_rate * 2` (`finance.py:160`).
- **The caveat, stated plainly:** attribution is to `Order.created_by_id` — *who opened the order*, not who pressed cancel (`finance.py:136-140`, with the code's own comment "proxy for staff responsible"). If a manager voids another waiter's item, the void lands on the waiter. The judge's ghost-ticket check does it properly by reading the audit log instead (§5.3).

### 1.10 "Who's giving away free food / comping bills?"
❌ **NO.** `GET /finance/anomalies/discounts` exists but is an **honest, self-documenting stub** — `app/finance/analytics.py:81-102`. It returns `{"staff_rates": [], "flagged_count": 0}` and a note saying it needs a `discount_amount` field on `Charge`. There is no discount model. Do not claim this works.

### 1.11 "What did this guest's bill consist of?"
✅ **YES.** `GET /receipts/<tab_id>` — `app/pos/receipts.py:64`; PDF at `GET /reports/receipt/<tab_id>` — `app/reports/routes.py:58`. Line items use `unit_price_snapshot`, so an old receipt reprints at the old price.

### 1.12 "Which M-Pesa / bank / card payments haven't matched to a POS payment?"
✅ **YES.** `GET /finance/mpesa/pending` (`app/finance/mpesa.py:47`), `GET /finance/bank/pending` (`app/finance/bank.py`), `GET /finance/card/summary` (`app/finance/mpesa.py:172`). Unmatched count also surfaces on `GET /dashboard/finance` (`app/dashboard/core.py:244`) and drives a red/yellow/green traffic light (`core.py:260-264`).

### 1.13 "Are our payment integrations actually switched on?"
✅ **YES — and this is a nice design detail.** `GET /finance/mpesa/status`, `/finance/bank/status`, `/finance/card/status`. Each returns `{"configured": bool, "message": str}` where the message is plain English about *what env var is missing*. `app/finance/bank_transfer.py:60-80` distinguishes three states — configured / dormant / **misconfigured** (provider set but unsupported, named in the message). Same shape at `app/finance/card_gateway.py` `card_status`.

---

## 2. STOCK

### 2.1 "How much of X do we have right now?"
✅ **YES.** `GET /inventory/items` (`app/inventory/items.py`), `GET /dashboard/inventory` (`app/dashboard/core.py:156-204`).
- **Source:** purely derived — `get_current_stock` sums the ledger (`app/services/stock.py:18-24`). Never cached.

### 2.2 "What was our stock on the 3rd, before the count?"
✅ **YES, as a function; ❌ NO as an endpoint.** `get_stock_at(item_id, as_of)` — `app/services/stock.py:41-47` — replays the ledger to any past timestamp. It's used internally by variance math. **No route exposes it.** Section A.

### 2.3 "Did we lose stock between counts?" — *the theft question*
✅ **YES.** `GET /inventory/variance?dept=<id>&from=<ISO>&to=<ISO>`, manager+ — `app/inventory/variance_routes.py:24-71`.
- **Source & formula** — `app/services/variance.py:26-104`:
  ```
  opening          = latest StockCount at or before period_start
  purchases        = SUM(PURCHASE movements in period)
  consumption      = ABS(SUM(SPOILAGE + STAFF_MEAL + SENT_BACK + SALE_PLACEHOLDER + SALE))
  expected_closing = opening + purchases − consumption
  actual_closing   = latest StockCount inside the period
  variance         = actual_closing − expected_closing        # negative = unexplained loss
  ```
- Flagged when `|variance| / |expected_closing| × 100 > item.effective_tolerance()` (`variance.py:82-102`) — per-item tolerance, configured in data, not hardcoded.
- **Honest limitation, handled well:** with no closing count in the period the function returns `None` and the endpoint emits `{"no_closing_count": true}` per item (`variance_routes.py:57-59`) rather than a fake zero.

### 2.4 "What's running low / needs reordering?"
✅ **YES.** `GET /dashboard/inventory` → `low_stock_count` + per-item `is_low` (`app/dashboard/core.py:176-183`); `GET /dashboard/overview` → `inventory_alerts` (`core.py:112-113`). `flask system check-alerts` turns each into a `LOW_STOCK` JudgeAlert (`app/cli/system.py:109-115`).
- **Source:** `get_current_stock(item.id) <= item.reorder_level`. Reorder level is per-item, owner-editable.

### 2.5 "Did the kitchen use more of an ingredient than the recipes say they should have?"
✅ **YES.** `_check_portion_variance` in `app/judge/engine.py:246-315`, run by `flask judge run-daily`.
- **Expected** = `Σ(OrderItem.quantity SERVED × RecipeLine.quantity)` (`engine.py:279-288`).
- **Actual** = consumption movements in the same window (`engine.py:42-50`).
- Fires `PORTION_VARIANCE` at >15% (MEDIUM) / >25% (HIGH), description literally says "Possible over-portioning, waste, or theft" (`engine.py:306-311`).
- Only flags **over**-usage; under-usage is deliberately a different signal (`engine.py:301-303`).

### 2.6 "Are our ingredient costs out of line with what we sold?"
✅ **YES.** `_run_cost_variance` — `app/judge/engine.py:83-147`, run by `flask judge run-weekly`. Same expected-vs-actual quantities, multiplied by `cost_per_unit`, flagged at 15%/25%, worded as "overspent/underspent by N% this week."

### 2.7 "Is a watch-list item spoiling abnormally?"
⚠️ **PARTIAL.** `flask judge run-daily` → `app/judge/engine.py:382-413` checks items with `is_watch_list=True`. **But the threshold is a hardcoded placeholder** — `SPIKE_THRESHOLD = Decimal("10")` raw units, with the code's own comment "conservative placeholder — will be calibrated once we have real usage data" (`engine.py:401-403`). It is not proportional to usage, so it is meaningless for a high-volume item and trigger-happy for a low-volume one. Do not oversell this one.

### 2.8 "Does consumption track revenue the way it should?"
✅ **YES, but data-gated.** `run_weekly` ratio analysis — `app/judge/engine.py:191-243`. `expected = baseline.expected_ratio × (revenue / 10000)`, deviation vs `baseline.tolerance_percent`. Baselines are DB rows (`JudgeBaseline`), owner-editable via `POST /admin/baselines`. If there are no payments in the period, `_get_sales_revenue` returns `None` (`engine.py:25-39`) and the whole block is skipped — **silent, not wrong.**

### 2.9 "Was every purchase backed by a receipt?"
✅ **YES — structurally guaranteed.** `Purchase.receipt_photo_path` is `nullable=False` (`app/models/purchase.py:26`). `GET /finance/dashboard` reports `no_receipt_purchases: 0` with an honest comment saying it is always 0 by model design (`app/finance/reports.py:392-394`). That's not a stat — it's a constraint. Say it that way in an interview.

### 2.10 "Where did this purchase request get stuck?"
✅ **YES.** `GET /inventory/purchase-requests` — `app/inventory/purchases.py:37`. Lifecycle: DRAFT → submit (`:143`) → propose budget (`:197`) → approve (`:236`) → record purchase (`:277`). `GET /dashboard/finance` counts `pending_approvals` across both PENDING **and** PROPOSED, with a comment explaining why counting only PENDING would silently drop items off the badge (`app/dashboard/core.py:247-253`).

### 2.11 "Which supplier is cheapest for tomatoes?"
❌ **NO.** `Supplier` is a standalone address book (`app/models/supplier.py`) — name, contact, phone, `items_supplied` as a free-text string. **`Purchase` has no `supplier_id` FK** — only a nullable free-text `supplier_name` (`app/models/purchase.py:27`, comment: "full supplier table later"). Price history per supplier cannot be computed reliably.

---

## 3. PEOPLE

### 3.1 "Who is on duty right now?"
✅ **YES.** `GET /hr/attendance/today` (`app/hr/attendance.py:31`); also `GET /dashboard/overview` → `staff.on_duty_names` (`app/dashboard/core.py:80-91`).
- **Source:** derived — for each active profile, take the **latest** `ClockEvent`; on-duty iff it is a `CLOCK_IN` within 16 hours. No `is_on_duty` flag exists.

### 3.2 "Who was scheduled today but didn't show?"
✅ **YES.** `GET /dashboard/staff` → `absent_today` (`app/dashboard/core.py:403-409`); richer per-employee breakdown at `GET /hr/attendance/summary` (`app/hr/attendance.py:144`), which splits **absent_with_notice vs absent_no_notice** by checking approved leave (`app/services/hr.py:110-119`) and absence notices (`hr.py:122-139`).

### 3.3 "How many hours did each person work, and what do we owe them?"
✅ **YES.** `GET /finance/payroll?period=YYYY-MM` (manager+, `app/finance/reports.py:444-473`) and `GET /hr/payroll-draft` (`app/hr/performance.py:60`).
- **Source:** `app/services/payroll.py:82-127`. Hours derived from paired clock events. Gross by wage period — HOURLY `hours × rate`, DAILY `(hours/8) × rate`, MONTHLY flat (`payroll.py:58-79`). **Staff meals are deducted at cost**: `Σ |StockMovement.change_amount| × item.cost_per_unit` for that user's `STAFF_MEAL` movements (`payroll.py:25-55`). Net is floored at zero.
- **Honest gap, handled honestly:** `net_pay` is `None` for anyone with no `wage_rate` set; `/finance/dashboard` counts those as 0 with a comment explaining that's an honest reflection of missing data, not a bug (`app/finance/reports.py:409-417`).

### 3.4 "Who are my best and worst performers?"
⚠️ **PARTIAL — and there is a real bug here. Read this before quoting the number.**
`GET /hr/performance/<profile_id>` (`app/hr/performance.py:32`) and `GET /dashboard/staff` → `top_performers` / `bottom_performers` (`app/dashboard/core.py:429-443`).
- **Composite formula** — `app/services/hr.py:284-289`, weights at `hr.py:16-21`: punctuality 30%, attendance 40%, cash_health 15%, void_health 15%.
- **The bug:** `compute_performance` is called with an **`EmployeeProfile.id`** (`app/hr/performance.py:50`, `app/dashboard/core.py:434`). But inside:
  - cash_health queries `CashReconciliation.staff_id == employee_id` (`app/services/hr.py:267-272`) — and `staff_id` is an FK to **`users.id`** (`app/models/cash_reconciliation.py:39`).
  - void_health matches `row["staff_id"] == employee_id` (`app/services/hr.py:278-281`) — and that row's `staff_id` is `Order.created_by_id`, also a **User** id (`app/services/finance.py:153`).
  - `EmployeeProfile.id` and `User.id` are **separate UUIDs** (`app/models/employee_profile.py:21-22`).
  
  Result: those two lookups never match. `cash_health` is permanently 100 and `void_health` is permanently 100 — **30% of the composite score is a constant.** The score is really punctuality+attendance rescaled. Fix is one line each: pass/compare `profile.user_id` for those two components. (Guest rating at `hr.py:176-190` is correct — `GuestFeedback.served_by_employee_id` genuinely FKs to `employee_profiles.id`.)

### 3.5 "How do guests rate each staff member and each department?"
✅ **YES.** `GET /dashboard/feedback?period=…` — `app/dashboard/core.py:588-662`. Two real `GROUP BY` aggregations: `AVG(score)` by `department_id` (`core.py:610-618`) and by `served_by_employee_id` (`core.py:630-638`), each with a count, plus the 10 most recent comments. Per-staff detail at `GET /feedback/staff/<employee_id>` (`app/feedback/core.py:124`).

### 3.6 "Has everyone signed the current version of the conduct rules?"
✅ **YES.** `GET /conduct/compliance` (`app/conduct/core.py:191`) and `GET /dashboard/conduct` (`app/dashboard/core.py:458-500`) — per-rule `signed_pct` + `unsigned_count`, plus an `overall_compliance_pct`. Rules are **versioned** (`GET /conduct/rules/<rule_id>/versions`, `app/conduct/core.py:101`), and signatures are append-only — a new rule version resets who has signed *that version*.
- `flask system check-alerts` raises `CONDUCT_UNSIGNED` alerts (`app/cli/system.py:136-146`).

### 3.7 "Who's on leave, and who asked for time off?"
✅ **YES.** `GET /hr/leave-requests` (`app/hr/leave.py`) with approve/reject/cancel transitions; absence notices at `GET /hr/absence-notices`.

### 3.8 "Can a fired employee still use their phone app?"
✅ **NO, they cannot — and that's enforced per request.** `require_active_user` (`app/utils/auth_decorators.py:29-41`) re-loads the User from the DB and re-runs `check_active_and_unlocked` on **every** protected request. The decorator order comment at `auth_decorators.py:40` is deliberate: `jwt_required` is applied last so it runs first. Deactivation takes effect in milliseconds, not at token expiry.

### 3.9 "Is anyone working off the books?"
✅ **YES, structurally prevented.** `require_clocked_in` (`app/utils/auth_decorators.py:47-67`) gates POS/tab/payment endpoints on the employee's latest ClockEvent being a `CLOCK_IN`. You cannot take an order without a clock record existing.

---

## 4. GUESTS & OPERATIONS

### 4.1 "Who's arriving today, who's leaving, who's in-house?"
✅ **YES.** `GET /front-desk/today` (staff+, `app/bookings/dashboard.py:22`) and `GET /dashboard/bookings` (owner, `app/dashboard/core.py:279-366`). Both use `business_day_bounds_today()` — a resort day is not a calendar day, and that cutoff logic lives in one place (`app/services/business_day.py`).

### 4.2 "Which bookings still owe a deposit?"
✅ **YES.** `GET /dashboard/bookings` → `pending_deposits[]` with guest name, required and paid (`app/dashboard/core.py:321-330`).
- **Source:** derived — `get_deposit_total(b.id) < b.deposit_required`, where `deposit_required` is a frozen snapshot on the booking and the paid figure is summed from `BookingPayment` rows.

### 4.3 "Which water-activity guests haven't signed a waiver?" — *the liability question*
✅ **YES, in three places.** `GET /front-desk/today` → today's (`app/bookings/dashboard.py:51-69`); `GET /dashboard/bookings` → **tomorrow's**, so you can chase them in advance (`app/dashboard/core.py:332-348`); and `flask system check-alerts` raises a HIGH `WAIVER_MISSING` alert naming the guest (`app/cli/system.py:117-134`).

### 4.4 "How full were the villas last month?"
✅ **YES.** `GET /reports/occupancy?from=&to=` — owner-only PDF — `app/reports/routes.py:321`. Builds a per-villa, per-day occupancy grid from booking date ranges.

### 4.5 "Has this guest stayed with us before? What did they spend?"
⚠️ **PARTIAL.** `GET /guest-records/<guest_id>/history` — `app/bookings/guests.py:46` — returns every past booking with resource, dates, status and `base_total`. **It does not return their POS spend** (tab charges), only room totals. Lifetime value is not computed.

### 4.6 "How many wristbands did we sell today, and how many people are still inside?"
✅ **YES.** `GET /gate/today-stats` — `app/gate/core.py:88-102` — `issued_today`, `inside_now` (count of ACTIVE bands), `total_entry_fees`.

### 4.7 "Did the gate take the money it should have?" — *the gate theft question*
✅ **YES.** `GET /gate/reconciliation?date=` — `app/gate/core.py:238` → `app/services/gate.py:203-236`.
- Check 1: `bands_issued × 3000` must equal `SUM(entry payments)`.
- Check 2: an **independent physical headcount** (`POST /gate/headcount`) is compared to bands issued. `headcount > bands_issued` means someone walked in without paying.
- `check_gate_signals` (`app/services/gate.py:241-336`) turns both into alerts, plus a third: any gate staffer whose band-forfeit rate is ≥3× the day average, minimum sample of 3 (`gate.py:311-333`).

### 4.8 "What happened to unused wristband credit at end of day?"
✅ **YES.** `flask gate close-day` / `POST /gate/forfeit-day` → `forfeit_day` (`app/services/gate.py:159-178`). Flips ACTIVE bands to FORFEITED, closes their tabs, returns `(count, total_unused_credit)`. Policy is explicit in the docstring: *"Unused credit is forfeit — no refund logic exists or will be added"* (`gate.py:142`).

### 4.9 "Can a guest run up an unlimited tab on a wristband?"
✅ **NO — capped.** `check_band_credit` — `app/services/tab.py:39-67`. Ceiling = `ENTRY_FEE × 2` = KSh 6,000. Band tabs only; villa/walk-in tabs are uncapped by design (`tab.py:54-56`). The rejection message tells the guest what to do: "Ask the guest to add more credit at the gate."

### 4.10 "Which rooms are dirty / being cleaned / failed inspection?"
✅ **YES.** `GET /housekeeping/status` — `app/housekeeping/__init__.py:93`, with a full state machine (`assign → start → complete → inspect`, plus `flag`) validated against `VALID_CLEANING_TRANSITIONS` (`app/models/cleaning_status.py:28`, enforced at `app/housekeeping/__init__.py:71`).

### 4.11 "What equipment is overdue for service?"
✅ **YES.** `GET /dashboard/equipment` — `app/dashboard/core.py:667-689`.
- **Source:** `Equipment.is_due_service` is a `@property`, **not a column** (`app/models/equipment.py:47-54`) — it recomputes from `last_service_utc` on every read, so it can never go stale.

### 4.12 "What's coming up — events, holidays, peak days?"
✅ **YES.** `GET /dashboard/calendar?from=&to=` — `app/dashboard/core.py:537-583` — merges `CalendarEntry` rows (with `is_peak`) and non-cancelled `Event` rows. `GET /dashboard/overview` carries a 7-day look-ahead inline (`core.py:122-130`).

### 4.13 "What incidents / lost property were logged?"
✅ **YES.** `GET /incidents` (`app/incidents/__init__.py`), `GET /lost-found` (`app/lost_found/__init__.py:43`).

---

## 5. SECURITY & AUDIT

### 5.1 "Has anyone tampered with our records?"
✅ **YES — via CLI only.** `flask audit verify-chain` — `app/cli/system.py:166-176` → `AuditLog.verify_chain()` at `app/models/audit_log.py:88-103`.
- **How:** `entry_hash = SHA256(actor|action|target|timestamp|prev_hash)` (`audit_log.py:49-60`). Each row's hash covers the previous row's hash. Editing or deleting *any* past row invalidates every hash after it. Verification walks all rows in timestamp order and re-computes; the failure message names the exact breaking row (`audit_log.py:101`).
- **Portability detail worth knowing:** timestamps are normalised to naive-UTC ISO before hashing (`audit_log.py:56-58`) specifically so SQLite (which drops tzinfo) and Postgres produce identical hashes. Without that the chain would "break" on a DB migration.
- ❌ **But there is no HTTP endpoint to read or verify the audit log.** Confirmed against the full 268-route map. The owner PWA cannot show it. Section A.

### 5.2 "Who did this specific thing?"
⚠️ **PARTIAL.** Every mutating endpoint writes `AuditLog.log(actor=..., action=..., target=...)` — the pattern is everywhere (e.g. `app/dashboard/core.py:751`, `app/finance/reports.py:287`, `app/gate/core.py:145`). The data is complete. **Nothing queries it over HTTP.** The only consumer in the whole codebase is the judge's ghost-ticket check (§5.3).

### 5.3 "Is someone making food and then cancelling it so they can eat free?"
✅ **YES — the cleverest check in the system.** `_check_ghost_tickets` — `app/judge/engine.py:318-379`.
- Find `OrderItem` rows that are CANCELLED **but have a non-null `ready_at`** — the kitchen already made the food (`engine.py:333-338`).
- `OrderItem` has no `cancelled_by_id`, so the engine **reads the audit log** to find who cancelled it: `AuditLog.action == "order_item.cancel" AND AuditLog.target == oi.id` (`engine.py:348-351`).
- Fire HIGH `GHOST_TICKET` for anyone over 2 in the period (`engine.py:359-377`), worded "Food was made but never paid for."
- This is the one place the audit log stops being passive evidence and becomes an active data source. Good interview material.

### 5.4 "Can a manager read the private complaints staff sent me?"
✅ **NO — structurally, not by filtering.** `app/suggestions/core.py`.
- **List:** the WHERE clause itself is different for managers — `q.filter_by(category='MANAGEMENT')` when `role.level < 10` (`core.py:128-130`). OWNER_PRIVATE rows are never in the result set.
- **Direct GET by id:** returns **404, not 403** (`core.py:151-154`). Same on the review endpoint (`core.py:171-174`). A 403 would confirm the row exists; a 404 says it doesn't exist for you.
- Anonymous submission is permitted **only** for OWNER_PRIVATE (`core.py:65-68`); MANAGEMENT suggestions require attribution.
- The same `is_owner_only` split exists on disputes (`app/models/dispute.py`, counted separately at `app/dashboard/core.py:412-419`).

### 5.5 "Can a staff member clock in from home?"
✅ **NO, if the allow-list is populated.** `is_ip_allowed` — `app/services/hr.py:26-43` — checks `request.remote_addr` against active `WiFiAllowList` CIDRs. The list is DB-resident and owner-editable (`GET/POST /hr/wifi`, `app/hr/wifi.py`) — config through data, not code.

### 5.6 "Can the same request be submitted twice by accident?"
✅ **NO — defence in depth.** Every write carries an `idempotency_key`. Two layers:
1. App-level: query for the existing key and return it with `"duplicate": true` (e.g. `app/finance/reports.py:244-246`, `app/suggestions/core.py:70-72`, `app/services/gate.py:97-99`).
2. DB-level: `unique=True` on the column (e.g. `app/models/stock_movement.py:59`, `app/models/purchase.py:39`).
The app check handles the common case gracefully; the constraint handles the concurrent race the app check can't see.

### 5.7 "Do we get duplicate alerts if a cron job runs twice?"
✅ **NO.** All alert writes funnel through `fire_alert_if_absent` — `app/services/judge_alerts.py:18-45`. Dedup key is `(alert_type, description_key, status=OPEN)`, matched with `description LIKE '%key%'`.
- **Honest caveat:** the dedup is a `LIKE` on the description, not a structured column. In `app/judge/engine.py:70` the key is derived as `description.split(":")[0]`. For `GHOST_TICKET` the description has no colon, so the key is the whole sentence *including the count* — so an alert saying "cancelled 3 items" and a later "cancelled 4 items" are different keys and both appear. Minor, but know it before an interviewer finds it.

---

## Section A — Questions the system ALMOST answers

These are the highest-value gaps: **the data is already there and correct; nothing surfaces it.** Ordered by value-per-line-of-code.

### A1. "Show me the audit log." ❌ *(highest value, lowest effort)*
The hash-chained log is the system's crown jewel and there is **no HTTP endpoint for it at all** — verified against all 268 routes. `flask audit verify-chain` (`app/cli/system.py:166`) is CLI-only, so the owner PWA can't display it and the owner can't answer "who voided that KSh 4,000 order at 9pm?" without SSH.
**What's missing:** `GET /audit?actor=&action=&target=&from=&to=` (owner-only, paginated) and `GET /audit/verify` wrapping `AuditLog.verify_chain()`. Data model needs nothing.

### A2. "What are our best-selling menu items?" ❌
There are only **four `GROUP BY` clauses in the entire application** (`app/dashboard/core.py:69`, `:618`, `:638`, `app/services/finance.py:75`) and none of them group by menu item. `OrderItem` stores `menu_item_id`, `quantity`, `unit_price_snapshot` and `served_at` — everything needed. The judge already runs `SUM(OrderItem.quantity) GROUP BY menu_item` logic ingredient-by-ingredient (`app/judge/engine.py:281-286`) but never for reporting.
**What's missing:** `GET /pos/reports/top-items?from=&to=` — one grouped query. This is the single most-requested restaurant report and it does not exist.

### A3. "Which departments actually make money?" ❌
`GET /dashboard/finance` builds `dept_summary` with **budget only and no spend** — the code says so at `app/dashboard/core.py:235`: *"Spending: sum payments by tab's department — simplified: total payments in period."* Meanwhile `GET /finance/dashboard` does compute per-department spend properly (`app/finance/reports.py:363-378`). Two endpoints, one honest and one placeholder.
Revenue per department is harder — `Payment` links to `Tab`, not to a department. `MenuItem` → `department_id` exists, so revenue could be attributed via `Charge` → `OrderItem` → `MenuItem`. Nothing does this.

### A4. "Is this cashier chronically short?" ❌
`count_staff_shortfalls(staff_id, last_n=3)` is written, correct, and documented at `app/services/finance.py:96-109` — and **grep finds no caller anywhere in `app/`.** Dead code awaiting one endpoint or one line in the reconciliation report.

### A5. "What was our stock level last Tuesday?" ❌
`get_stock_at(item_id, as_of)` exists and works (`app/services/stock.py:41-47`) but is only called internally by variance math. No route exposes point-in-time stock, so nobody can reconstruct a historical stock report without running the variance endpoint over an artificial window.

### A6. "What is this guest worth to us?" ⚠️
`GET /guest-records/<id>/history` (`app/bookings/guests.py:46`) returns bookings and `base_total` but **not POS spend**. `GuestRecord → Booking → Tab → Charge` is all FK-connected. Lifetime value = one join away.

### A7. "Which supplier is cheapest?" ❌ *(needs schema, not just an endpoint)*
Blocked by a missing FK: `Purchase.supplier_name` is free text (`app/models/purchase.py:27`) and `Supplier` (`app/models/supplier.py`) is unlinked. Add `Purchase.supplier_id` and the whole price-history question opens up.

### A8. "Who's comping bills?" ❌ *(needs schema)*
`GET /finance/anomalies/discounts` is an intentional stub that documents its own fix (`app/finance/analytics.py:84-90`): add `Charge.discount_amount`, then mirror `void_analytics`.

### A9. Budget-exceeded alerts never fire — **dead code** ❌
`_run_budget_exceeded()` (`app/judge/engine.py:150-188`) reads `b.spent` behind `hasattr(b, 'spent')` at `engine.py:168`. **`Budget` has no `spent` column** — it's derived by `get_budget_spend()` (`app/services/finance.py:53`). So `spent` is always `Decimal("0")`, line 170's `if spent <= budget_amt: continue` always fires, and the function can never raise an alert. `run_weekly` counts it as a contributor (`engine.py:235`) but it always returns 0.
**Fix:** one line — `spent = get_budget_spend(b.department_id, month_start, month_end)`.

### A10. The performance score is 30% constant — **bug** ⚠️
See §3.4. Profile-id vs user-id mismatch at `app/services/hr.py:267-272` and `:278-281`. `cash_health` and `void_health` are always 100.

### A11. Spoilage spike threshold is a hardcoded placeholder ⚠️
`SPIKE_THRESHOLD = Decimal("10")` raw units for every item (`app/judge/engine.py:403`). Everything else in the judge is proportional and DB-configurable via `JudgeBaseline`. This one isn't. The code admits it.

---

## Section B — Interview questions, with answers grounded in this code

### B1. "Why don't you store the current stock level? Isn't summing the whole ledger slow?"

**Answer.** Storing it creates two sources of truth that drift. If a `UPDATE items SET stock = stock - 5` fails halfway, or two waiters decrement concurrently, the number is wrong and there is no way to tell it's wrong. Summing an append-only ledger cannot drift: `get_current_stock` at `app/services/stock.py:18-24` is the *only* way stock is read anywhere.

Three things fall out for free:
1. **Time travel.** `get_stock_at(item_id, as_of)` (`stock.py:41-47`) is the same query with one extra WHERE. Point-in-time stock is not a feature I built — it's a property of the shape.
2. **Auditability.** Every unit that moved has a row with an actor, a reason, and a timestamp.
3. **Variance math becomes trivial.** `app/services/variance.py:26-104` compares the ledger's prediction against a physical count. That's the theft detector, and it only exists because the ledger exists.

On speed: `stock_movements.item_id` is indexed (`app/models/stock_movement.py:48`). At resort scale this is a few thousand rows per item per year. If it ever mattered, the fix is a periodic snapshot row plus a delta sum — but I'd want a profiler to tell me that, not a guess. There's a real cost I do pay: `GET /dashboard/inventory` loops `get_current_stock` per item (`app/dashboard/core.py:176-177`), which is N+1. That's the honest weak spot.

The same pattern applied to money is `get_tab_balance` — `SUM(charges) − SUM(payments)` at `app/services/tab.py:23-33`. One idea, two domains.

---

### B2. "You snapshot some things and derive others. How do you decide which?"

**Answer.** The rule is: **derive what is true now, freeze what was true then.**

Frozen: `OrderItem.unit_price_snapshot`, `CashReconciliation.expected_amount`, `Booking.base_total`, every `AuditLog` row. If the owner raises beer from 300 to 350 tonight, last week's receipts must still print 300. A foreign key to `menu_items.price` would silently rewrite history.

Derived: stock level, tab balance, `Equipment.is_due_service`, hours worked, budget spend. These answer "right now", and "right now" must never be stale.

The tell for which side something belongs on is the question *"if an input changes later, should this number change?"* For a receipt, no — freeze it. For service-due, yes — so it's a `@property`, not a column (`app/models/equipment.py:47-54`). It literally cannot go stale because there's nothing to update.

---

### B3. "Explain the hash-chained audit log. What attack does it actually stop?"

**Answer.** `entry_hash = SHA256(actor|action|target|timestamp|prev_hash)` — `app/models/audit_log.py:49-60`. Each row's hash ingests the previous row's hash, so the rows form a chain.

**The attack it stops** is not an outsider — it's someone with DB access covering their tracks. Delete the row that says you voided a KSh 4,000 order, or edit the actor from your name to someone else's, and every hash from that point forward no longer recomputes. `verify_chain()` (`audit_log.py:88-103`) walks the rows in timestamp order, recomputes each hash, and names the exact row where it breaks.

**What it does NOT stop, and I'd say this before being asked:** someone who can write arbitrary SQL can recompute the entire chain forward from their edit. This is tamper-*evident*, not tamper-*proof*. Real tamper-proofing needs the chain head published somewhere I don't control — offsite, daily. That's a go-live item, not a code item.

**The detail I'm proudest of:** timestamps are normalised to naive UTC before hashing (`audit_log.py:56-58`) because SQLite silently drops tzinfo on retrieval and Postgres doesn't. Without that line, the chain "breaks" the moment you migrate dev→prod — and you'd spend a day hunting a security bug that was actually a serialization bug.

---

### B4. "You have idempotency keys AND a unique constraint. Isn't one of those redundant?"

**Answer.** No — they catch different failures.

The **app check** handles the common case: a waiter's tablet loses WiFi, retries, and the second request finds the existing row and returns it with `"duplicate": true` and a 200 (`app/finance/reports.py:244-246`, `app/suggestions/core.py:70-72`). Graceful, no error shown to the user.

The **DB unique constraint** (`app/models/stock_movement.py:59`, `app/models/purchase.py:39`) handles what the app check structurally cannot see: two requests that both SELECT before either INSERTs. That's a genuine race, and no amount of application code closes it — only the database can, because only the database serialises the write.

So: app check for UX, constraint for correctness. If I only had the constraint, every retry would surface an ugly 500. If I only had the check, concurrency would produce duplicate stock movements and the ledger — my source of truth — would be wrong.

Same reasoning drives `cash_recon_payments.payment_id` being the **primary key** of the join table (`app/models/cash_reconciliation.py:31`). "A payment can only be reconciled once" isn't validation code I have to remember to write on every path — it's the table's shape.

---

### B5. "Why `SELECT ... FOR UPDATE` for wristband numbers? Why not a sequence or a UUID?"

**Answer.** Because the number is read aloud at a gate. "Band 47" has to be a small integer a human can shout, and it has to restart at 1 each day. A UUID is unusable and a global sequence gives you band #12,043.

`allocate_band_number` — `app/services/gate.py:30-50` — takes a row lock on that day's counter row with `.with_for_update()`, reads `next_number`, increments, flushes. Concurrent gate tablets serialise on that row instead of both reading 47.

**And then the belt-and-braces:** a `UniqueConstraint(band_number, issue_date)` on the wristband table. If the lock ever fails — a driver quirk, someone running SQLite in dev where `FOR UPDATE` is a no-op — the DB rejects the duplicate rather than issuing two band #47s. The docstring at `gate.py:33-35` says exactly this. Same philosophy as B4: lock for the happy path, constraint for the truth.

---

### B6. "Walk me through how you hide the owner's private feedback from managers."

**Answer.** I don't filter it out of the response — **I never put it in the query.**

`app/suggestions/core.py:128-130`: if `actor.role.level < OWNER_LEVEL`, the query gets `.filter_by(category='MANAGEMENT')` appended. For a manager's session, OWNER_PRIVATE rows are not in the result set to be leaked. There's no `if not owner: del row` step that a future refactor can accidentally drop.

Direct access by ID is the interesting part: it returns **404, not 403** (`core.py:151-154`, and again on review at `:171-174`). A 403 leaks information — it confirms the row exists and that you're not allowed to see it, which tells a manager that a staff member complained about them. A 404 says: for you, this does not exist. Same treatment on disputes via `is_owner_only`.

**Where it stops.** `GET /dashboard/staff` counts owner-private disputes and suggestions (`app/dashboard/core.py:416-427`) — but that whole endpoint is owner-gated by `_require_owner` (`core.py:21-24`), so the count never reaches a manager. Worth checking that boundary explicitly, because a count is a leak too.

---

### B7. "You built three payment integrations that aren't switched on. Why isn't that wasted work?"

**Answer.** The socket pattern: the integration is complete, and an env var is the switch.

`app/finance/bank_transfer.py:44-58` — `is_sms_configured()` and `is_api_configured()` are pure env-var reads. `GET /finance/bank/status` returns `{"configured": bool, "message": str}` where the message is **plain English about what's missing** — and it distinguishes three states, not two (`bank_transfer.py:60-80`): configured (names the provider), dormant (no `BANK_PROVIDER` set), and **misconfigured** (`BANK_PROVIDER` set to something unsupported — names the bad value and lists the valid ones). That third state is the one that costs you an afternoon at 6am on go-live day if you skip it.

Why this isn't waste: the resort's M-Pesa paybill and bank API credentials are a business process I don't control — weeks of paperwork. Building the integration *after* credentials arrive means go-live blocks on my coding speed. Building it now means go-live blocks on `export MPESA_CONSUMER_KEY=...` and a status endpoint that says "configured".

Same idea, smaller scale, for notifications: `send_whatsapp` and `send_sms` (`app/services/notifications/whatsapp.py`, `sms.py`) return `("UNCONFIGURED", ...)` today. Activating each is one function body — every caller and every test already exists.

---

### B8. "What does your theft detection actually detect, and what would you say to someone who called it security theatre?"

**Answer.** I'd say: it's not security, it's **anomaly surfacing**, and I designed it to be quiet on purpose. `app/judge/engine.py`. Five real checks:

1. **Portion variance** (`:246-315`) — expected ingredient use from `recipes × orders served` vs actual consumption movements. >15% over → MEDIUM, >25% → HIGH.
2. **Cost variance** (`:83-147`) — the same gap priced at `cost_per_unit`, weekly.
3. **Ratio analysis** (`:191-243`) — consumption vs revenue against owner-editable `JudgeBaseline` rows.
4. **Ghost tickets** (`:318-379`) — my favourite. Food that reached `ready_at` and was then CANCELLED: made, never paid for. `OrderItem` has no `cancelled_by_id`, so the engine **queries the audit log** for `action='order_item.cancel', target=order_item.id` to find who did it (`:348-351`). Over 2 in a period → HIGH.
5. **Gate signals** (`app/services/gate.py:241-336`) — revenue vs `bands × 3000`, an independent physical headcount vs bands issued, and per-staff forfeit-rate outliers at ≥3× the day average with a minimum sample of 3.

**Where I'd push back on "theatre":** these are cross-checks between records written by *different people at different times for different reasons*. The waiter who cancels the ticket isn't the chef who marked it ready. The gate clerk who issues the band isn't the person doing the headcount. Faking one record is easy; faking two that must agree is much harder. That's the actual security property.

**Where I'd concede:** it's tuned wide deliberately — the file header says *"better silent than crying wolf"* — because a false-positive theft accusation in a 40-person workplace is worse than a missed one. And I'd volunteer the three flaws I know about before the interviewer finds them:
- `_run_budget_exceeded` (`:150-188`) reads `b.spent`, but `Budget` has no `spent` column (`app/models/budget.py`) — it's derived elsewhere. So the guard at `:170` always short-circuits and **that check has never fired**. One-line fix: call `get_budget_spend()`.
- The spoilage-spike threshold is a hardcoded 10 raw units for every item (`:403`), not proportional. Placeholder, and the comment says so.
- Alert dedup is a `LIKE '%key%'` on the description (`app/services/judge_alerts.py:33`), not a structured column — so a ghost-ticket alert whose count changes creates a second alert.

Knowing what your own detector misses is the point. A detector you can't critique is the one that's theatre.

---

### B9. "Why does every endpoint re-fetch the user from the database? That's a query on every request."

**Answer.** Because a JWT is a claim about the past, and firing someone is a fact about the present.

`require_active_user` (`app/utils/auth_decorators.py:29-41`) re-loads the User and re-runs `check_active_and_unlocked` on **every** protected request. Without it, a fired employee's still-valid token works until it expires — the docstring at `auth_decorators.py:14-19` states exactly this threat. In a resort where someone gets walked off the property for stealing, "revoked within milliseconds" is worth one indexed primary-key lookup.

**The subtle bit** is the decorator order at `auth_decorators.py:40-41`: `jwt_required()` is applied *last* so it runs *first*. Token signature validated before I touch the database — otherwise an unauthenticated attacker could make me do a DB lookup per request. That comment is in the file because I got the order wrong once.

The same shape gates operations on being clocked in — `require_clocked_in` (`auth_decorators.py:47-67`) checks that the employee's latest `ClockEvent` is a `CLOCK_IN` before letting them touch POS. You can't take an order off the books, because taking an order requires a clock record to exist.

---

### B10. "You have a `refund` endpoint that bypasses your own state machine. Isn't that a hole?"

**Answer.** It's a deliberate exception, and the important part is *how* it breaks the rule.

Normally `SERVED` is terminal — `VALID_TRANSITIONS` at `app/models/order_item.py:35` is a declarative dict, and `_transition_item` (`app/pos/orders.py:248`) rejects anything not in it with a plain-English message. Six state machines in the codebase work this way (`booking.py:26`, `event.py:23`, `dispute.py:33`, `cleaning_status.py:28`, `event_assignment.py:19`, `event_inventory_allocation.py:23`) — the rule lives in a dict next to the model, not scattered across route handlers.

But a manager must be able to reverse a served item — the guest complained, the food was wrong. `refund_item` (`app/pos/orders.py:459`) is manager-gated and skips the transition table. **What it does not do is edit anything.** `_reverse_charge` (`orders.py:188`) writes a *negative* `Charge` row; the original positive row is untouched, and the docstring says so at `orders.py:465-467`. The tab balance changes because `SUM(charges) − SUM(payments)` now includes a negative — the derived value moves without any history being rewritten.

So the append-only invariant survives the exception. That's the test I'd apply to any "bypass": does it write a compensating record, or does it mutate one? Mutation is the hole. A negative row is just accounting.

---

## Summary scorecard

| Domain | Strong | Weak |
|---|---|---|
| Money | Three-way reconciliation, auto-close health check, derived budget spend, socket status diagnostics | No discount/comp tracking; void attribution is by order-opener not canceller |
| Stock | Ledger-derived levels, variance vs physical count, recipe-vs-actual portion variance, mandatory receipts | No top-selling-items report; no supplier price history; spoilage threshold is a placeholder |
| People | Derived hours + payroll with staff-meal deductions, absence-with/without-notice split, versioned conduct compliance, per-request kill switch | Performance composite is 30% constant (profile-id vs user-id bug) |
| Guests | Business-day-aware arrivals/departures, waiver chasing a day ahead, occupancy grid PDF | No guest lifetime value (bookings only, no POS spend) |
| Security | Hash-chained audit log, query-level authorization with 404-not-403, idempotency at two layers, `FOR UPDATE` + unique constraint | **No HTTP endpoint for the audit log at all** — CLI only |
| Judge | Five cross-record checks, idempotent alert firing, deliberately wide tolerances | Budget-exceeded check is dead code; dedup key is a `LIKE` match |

**Route count: 268. `GROUP BY` clauses in the entire application: 4.** That ratio is the shape of the biggest opportunity — this system captures excellent data and aggregates very little of it.
