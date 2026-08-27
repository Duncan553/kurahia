# Kurahia — Master To-Do

Everything discussed and discovered in the 2026-08-26/27 session, in one place.
Ordered by what it costs you to leave undone, not by effort.

Status key: ✅ done and committed · 🔴 blocker · 🟠 real gap · 🔵 needs your call · ⚪ nice to have

---

## 🔴 P0 — Production blockers

### 1. No VAT, and no eTIMS. This is a legal blocker, not a feature gap.

**Verified:** `grep` across `app/models`, `app/pos`, `app/finance` finds **no VAT
field, no tax rate, no tax amount, no KRA PIN, no eTIMS integration anywhere**.
Every price is a flat number and no invoice carries a tax component.

Kenya requires every VAT-registered hospitality business to issue an
**eTIMS-compliant invoice for every single sale** — cash, card and mobile money
alike. Non-compliance is penalised at **KES 50,000 per month**. The threshold is
KES 5M annual turnover; a resort with a gate, bar, restaurant, spa and villas
will be well past it.

A compliant invoice must carry: seller PIN, buyer PIN (when input tax is
claimed), **serial number**, date-time of issue, **gross and tax amounts**, item
code, description, quantity, unit, **tax rate**, a unique system identifier, an
invoice identifier, and a **QR code**.

**Why this decides the receipts question below.** Today's receipt is *derived* —
`GET /receipts/<tab_id>` rebuilds it from Charges and Payments every time. That
is excellent internal design (it can never drift from the ledger, and it
regenerates identically years later). But a serial number, a unique identifier
and a QR code are **issued once and must never change**, so they have to be
STORED. A derived receipt cannot be a tax invoice.

**Do not build a generic "receipt archive".** It would be immediately obsolete.
Build the invoice store eTIMS-shaped or not at all:

- [ ] Confirm the resort's VAT-registration status and PIN with the owner
- [ ] Add VAT to pricing: is the menu price VAT-inclusive or exclusive? (Kenya
      hospitality is normally inclusive — must be decided before any tax maths)
- [ ] `TaxInvoice` model: immutable, serial-numbered, one row per completed sale,
      storing gross/tax/net and the KRA identifiers returned by eTIMS
- [ ] eTIMS integration — fits the existing dormant-socket pattern (see the
      M-Pesa/bank/card sockets in `PAYMENTS_DESIGN.md`), so it can be built and
      tested before credentials exist
- [ ] QR code rendering on the printed/emailed receipt
- [ ] Confirm the retention period with KRA directly — sources disagree, and it
      varies by tax type

**Cross-check before building:** the owner may already file through an external
accountant or a separate ETR device. If so the requirement is a bridge/export,
not a full integration. **Ask first — this is the single most expensive thing on
this list to get wrong.**

### 2. Nothing has ever been proven to work from an empty database

Every test leans on `_seed_test_db`. A **cold start has never been exercised**,
so "can a real person build this resort through the app, with nothing
pre-loaded?" is unanswered — and in production nobody seeds.

- [ ] Cold-start test: from an empty DB, via the API only —
      department → ingredient → menu item → recipe → sale → verified deduction
- [ ] Any step that needs a hand-seeded row is a production blocker; fail loudly
- [ ] Same for services: manager creates a spa treatment and sells it end to end

### 3. `station_pwa` is not a PWA

No `vite-plugin-pwa` dependency, no `VitePWA` in its vite config, and no
`dist/sw.js` while employee and owner both emit one. No service worker, no
manifest, no offline, not installable.

It matters most here: these are the POS and kitchen tablets on the resort LAN,
and `employee_pwa` even has an offline clock-in queue while station has nothing.

- [ ] Decide scope: read-only shell caching (safe) vs offline order/payment
      queueing (real money logic, conflict resolution, much bigger)
- [ ] Manifest + icons + caching strategy — kitchen queues are live data where a
      stale read is actively harmful

---

## 🟠 P1 — Real gaps found and measured

### 4. 24 of 28 menu items still need classifying

The machinery is now in place (see §11) but the data is not. Current state:
**4 RECIPE, 24 UNTRACKED, 0 DIRECT.**

- [ ] Head chef: recipes for the 3 kitchen + 5 bar items
- [ ] Head chef / manager: `DIRECT` links for bottled stock (Tusker etc.)
- [ ] Manager: `SERVICE` for the ~16 that genuinely consume nothing
      (pool pass, hiking, cycling, kayaking)
- [ ] Jet ski and golf cart **do** burn fuel — those need real recipes, not SERVICE

### 5. Seed data is thin where it matters most

- [ ] `GET /inventory/items` returns `[]` — **no ingredients exist at all**, so no
      recipe can be written and the judge's variance and spoilage checks have
      nothing to run against
- [ ] `GET /equipment` returns `[]` — safety-check submission is unreachable

### 6. No HTTP route for the audit log

The hash-chained trail is the system's best feature and is reachable **only** via
`flask audit verify-chain`. The owner PWA cannot answer "who voided that order at
9pm?" without SSH.

- [ ] Owner-only endpoint + screen, filterable by actor/action/date

### 7. No movement-ledger read endpoint

Only POSTs exist (`spoilage`, `staff-meal`, `sent-back`). Stock *level* is
readable; the history behind it is not.

- [ ] `GET /inventory/movements` with item/date filters, so variance is explainable

### 8. Reporting gaps

- [ ] **No top-selling-items report** — 4 `GROUP BY` clauses in the whole app and
      none group by menu item
- [ ] `GET /finance/anomalies/discounts` is an intentional stub returning empty
      arrays, but CLAUDE.md reads as though discount analytics exist
- [ ] `/dashboard/finance` department rows carry budget with **no spend** (code
      says "simplified"); `/finance/dashboard` does it properly — two endpoints,
      one is a placeholder
- [ ] Spoilage-spike threshold is a hardcoded 10 raw units for every item —
      meaningless at high volume

---

## 🔵 P2 — Needs your decision

### 9. Manager pricing screen

Agreed in principle. **Build it as a margin screen, not a price editor** — the
per-item `food_cost`, `gross_margin`, `food_cost_pct` and `in_stock` are already
computed in `app/pos/menu.py` and currently unused by any UI.

- [ ] `/manager/pricing`, grouped by department
- [ ] Columns: Price · Food cost · **Margin %** · In stock · **Tracking**
- [ ] Inline edit, one Save, each row audited individually
- [ ] Bulk action: +N% across a department
- [ ] Skip effective-date scheduling — that exists for chains pushing prices to
      hundreds of tills overnight. One resort, one database. YAGNI.

### 10. Open questions

- [ ] Menu price VAT-inclusive or exclusive? (blocks §1)
- [ ] Should `SERVICE` classification require manager sign-off, or can the head
      chef self-certify a kitchen item as consuming nothing?
- [ ] Retention: how long must closed tabs and invoices be kept?

---

## ✅ Done this session

Backend **810 passing / 5 skipped**, all three apps `tsc -b` clean and building,
`shared_ui` 62/62.

**Money and stock integrity**
- Direct-service inventory leak — spa, water and every non-kitchen department
  deducted **nothing**, because consumption only fired on `READY` and those items
  jump straight to `SERVED`. The no-recipe safety net never fired either.
- Direct depletion (`MenuItem.inventory_item_id`) — a Tusker or an apple deducts
  itself, no fake one-line recipe
- Explicit `stock_tracking` (RECIPE / DIRECT / SERVICE / UNTRACKED) — separates
  "deliberately consumes nothing" from "nobody decided", which is what makes the
  block enforceable
- Untracked items **cannot be put on sale**
- `BUDGET_EXCEEDED` alert had **never fired** — `Budget` has no `spent` column
- 30% of every performance score was a hardcoded 100 (profile id vs user id)

**Ownership and access**
- Head chef owns kitchen + bar dishes, recipes, ingredients **and prices**
- Manager owns every department's service catalogue and prices
- A chef cannot reclassify a spa service into the kitchen to seize it
- `/uploads` had **no role check** — any waiter could replace guest-facing menu photos
- Behind Nginx the **whole resort shared one login rate-limit bucket** (no ProxyFix)
- Menu edits now audit **old → new**, so repricing is answerable

**Correctness**
- "Clock Out" posted `/hr/clock-in` — nobody could clock out; payroll-affecting
- Owner could not select the **current month** in Finance (UTC vs EAT)
- `Modal` rendered every child **twice**; `Drawer` sat off-screen and flew away on any press
- Front desk was a dead end — `deposit → confirm → check-in` had no UI for the first two steps
- `/inventory/quick-entry` had a dropdown with **zero options**
- "Access restricted" screen had no explanation and no way back

**Test infrastructure**
- Suite **25 minutes → ~100 seconds** (Argon2 in fixtures + no xdist)
- Two genuinely flaky timing tests identified and quarantined correctly
- `tsc --noEmit` was checking **zero files** (`files: []` + project references)
- Schema drift: a declared FK that the database never had, plus a drift guard test
- Tests stopped littering `employee_pwa/public/images`

**Coverage added**
- Gate wristband lifecycle, barrier to exit (10 tests) incl. separation of duties
- Full guest journey across every department (12 tests)
- Responsive sweep across 3 apps × every route × 3 viewports
- Touch targets: 840 sub-44px controls → 6

---

---

## Corrections to this document

Two P1 entries above were WRONG when written, and are corrected here rather than
quietly edited, because the mistake is instructive.

**"Zero ingredients exist"** and **"`GET /equipment` returns `[]`"** — both were
measurement errors, not missing data. There are **33 ingredients and 6
equipment records**. The inventory list was scoped to the actor's own department
for everyone below owner, and it was read as a manager assigned to "Management",
which owns no stock. A permissions artifact was reported as an empty database.
The scoping is now manager-and-above (fixed 2026-08-27), because approving
purchases and chasing variance across departments IS the manager's job.

The real gap was never missing ingredients. It is that **only one purchase has
ever been recorded**, and `cost_per_unit` is derived from purchases as a
weighted average — so 32 of 33 ingredients have no cost, and almost nothing can
show a margin. Record purchases and the whole chain lights up.

Same lesson as the UI sweep earlier in the session: check whether the
measurement is wrong before concluding the system is.

## A note on how to read this

Three findings this session were **my tooling being wrong, not your app** — the
responsive sweep reported ~1,800 false positives across two iterations before the
detector was right. Anything above was verified against running code or live data
before it was written down. Where something is unproven it says so.

---

## Status at end of session, 2026-08-27

**876 backend tests passing, 5 skipped. All three apps `tsc -b` clean and
building. shared_ui 62/62.**

Every P0 is closed. Every backend built this session has a screen: audit trail,
menu profit, VAT, stock tracking, movement ledger, role assignment.

**What is left is not code.**

1. Classify 22 menu items and record some purchases (~1 hour of data entry).
   Until then most of the menu cannot be sold and 27 dishes read "cannot be
   measured" — not because anything is broken, but because the system will not
   invent numbers it does not have. Industry research names menu build errors as
   the single most common cause of POS launch failures, so this is the real risk.

2. Confirm with the accountant: are menu prices VAT-inclusive, and which items
   are exempt or zero-rated? Built inclusive at 16% as the Kenyan norm, but that
   is a tax position this system is not qualified to hold.

3. Run one real service — one department, real staff, old system still running
   in parallel per GO_LIVE_PLAN.md step 12. Nothing here has been tested under
   real load, on real tablets, with real staff. That is the only test that counts
   and it is the one that could not be run from here.

Three gaps in GO_LIVE_PLAN.md worth closing before that service:
  - no "it died mid-service" card for staff (keep a numbered paper ticket, do
    not guess, hand it to the manager at close)
  - no hypercare window — decide who staff phone at 8pm, and tell them
  - reconciliation is strict by design, which punishes untrained staff hardest
    in week one

