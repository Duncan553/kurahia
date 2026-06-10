# F-11.7 Backend Truth Audit
*Generated: 2026-06-10 | Source of truth: app/ routes read directly*

---

## Role Level Reference

| Level | Role | Can create |
|---|---|---|
| 1 | Staff | (no creation) |
| 3 | Gate Staff | — |
| 5 | Manager / Dept Head | staff accounts, profiles, inventory |
| 10 | Owner | everything above + approve purchases, manage roles/depts |

---

## A. Permission Matrix — Every Endpoint

### Auth (`/auth/*`)

| Method | Path | Min Level | Dept-Scoped | Owner-Private |
|---|---|---|---|---|
| POST | /auth/login | none (public) | — | — |
| POST | /auth/pin-login | none (public) | — | — |
| POST | /auth/refresh | refresh token | — | — |
| POST | /auth/set-pin | any (setup token) | — | — |
| POST | /auth/change-pin | 1 | — | — |
| POST | /auth/deactivate/:id | 1 (hierarchy: must outrank target) | — | — |
| POST | /auth/reset-lockout/:id | 1 (hierarchy: must outrank target) | — | — |
| POST | /auth/users | 1 (hierarchy: only below own level) | — | — |
| GET | /auth/users | 1 | ✓ manager sees own dept only | — |
| PATCH | /auth/users/:id | 1 (hierarchy) | — | — |
| POST | /auth/users/:id/activate | 1 (hierarchy) | — | — |

### Admin (`/admin/*`)

| Method | Path | Min Level | Dept-Scoped | Owner-Private |
|---|---|---|---|---|
| GET | /admin/departments | **5** | — | — |
| POST | /admin/departments | **10** | — | ✓ |
| PATCH | /admin/departments/:id | 10 | — | ✓ |
| POST | /admin/departments/:id/disable | 10 | — | ✓ |
| POST | /admin/departments/:id/enable | 10 | — | ✓ |
| GET | /admin/roles | **5** | — | — |
| POST | /admin/roles | **10** | — | ✓ |
| PATCH | /admin/roles/:id | 10 | — | ✓ |
| POST | /admin/roles/:id/disable | 10 | — | ✓ |
| POST | /admin/roles/:id/enable | 10 | — | ✓ |

### Inventory (`/inventory/*`)

| Method | Path | Min Level | Dept-Scoped | Notes |
|---|---|---|---|---|
| POST | /inventory/items | **5** | — | manager creates in any dept; no self-dept enforcement |
| PATCH | /inventory/items/:id | **5** | — | |
| GET | /inventory/items | **1** | ✓ manager sees own dept; owner sees all or by ?department param | |
| POST | /inventory/items/:id/disable | 5 | — | |
| POST | /inventory/items/:id/enable | 5 | — | |
| POST | /inventory/counts | **5** | — | |
| GET | /inventory/variance | **5** | ✓ manager sees own dept auto | |
| POST | /inventory/movements/spoilage | **5** | — | |
| POST | /inventory/movements/staff-meal | **1** | — | any staff can log staff meals |
| POST | /inventory/movements/sent-back | **5** | — | |
| GET | /inventory/purchase-requests | **5** | ✓ manager sees own dept users only | |
| POST | /inventory/purchase-requests | **5** | — | |
| POST | /inventory/purchase-requests/:id/propose | **5** | — | |
| POST | /inventory/purchase-requests/:id/approve | **10** | — | owner only |
| POST | /inventory/purchases | **5** | — | receipt_photo_path mandatory |

### HR (`/hr/*`)

| Method | Path | Min Level | Dept-Scoped | Notes |
|---|---|---|---|---|
| POST | /hr/clock-in | **1** | — | requires employee profile + WiFi CIDR |
| POST | /hr/clock-out | **1** | — | requires employee profile + WiFi CIDR |
| POST | /hr/clock-events/manual | **5** | — | cannot override own clock |
| GET | /hr/clock-status | **1** | — | own status only |
| GET | /hr/clock-events | **5** | — | optional employee_id + date filter |
| GET | /hr/attendance/today | **5** | — | all employees scheduled today |
| GET | /hr/attendance/employee/:id | **5** | — | |
| GET | /hr/attendance/summary | **5** | — | |
| POST | /hr/shifts | **5** | — | |
| GET | /hr/shifts | **5** | — | optional employee_id + date filter |
| PATCH | /hr/shifts/:id | **5** | — | |
| POST | /hr/shifts/:id/cancel | **5** | — | |
| POST | /hr/leave-requests | **1** | — | requires employee profile |
| POST | /hr/leave-requests/:id/approve | **5** | — | cannot approve own |
| POST | /hr/leave-requests/:id/reject | **5** | — | |
| POST | /hr/leave-requests/:id/cancel | 1 (own) / 5 (others) | — | |
| GET | /hr/leave-requests | **1** | — | manager sees all; staff sees own |
| POST | /hr/profiles | **5** | — | |
| GET | /hr/profiles | **5** | — | |
| GET | /hr/profiles/:id | **5** | — | |
| PATCH | /hr/profiles/:id | **5** | — | |
| POST | /hr/profiles/:id/disable | **10** | — | owner only |
| POST | /hr/profiles/:id/enable | **10** | — | owner only |

### Gate (`/gate/*`)

| Method | Path | Min Level | Notes |
|---|---|---|---|
| POST | /gate/issue-band | **3** | |
| POST | /gate/deactivate-band/:number | **3** | |
| GET | /gate/bands/:number | **1** | any staff |
| GET | /gate/active-bands | **3** | |
| POST | /gate/headcount | **5** | |
| POST | /gate/forfeit-day | **5** | |
| GET | /gate/reconciliation | **5** | |

### Notifications (`/notifications/*`)

| Method | Path | Min Level |
|---|---|---|
| GET | /notifications/inbox | 1 |
| POST | /notifications/:id/mark-read | 1 |
| GET | /notifications/whatsapp/status | 5 |
| GET | /notifications | 5 |

### Conduct (`/conduct/*`)

| Method | Path | Min Level | Notes |
|---|---|---|---|
| POST | /conduct/rules | **10** | owner only |
| GET | /conduct/rules | **1** | all staff |
| GET | /conduct/rules/:id/versions | **5** | |
| POST | /conduct/sign | **1** | requires employee profile |
| GET | /conduct/signatures/:id | 1 (own) / 5 (others) | |
| GET | /conduct/compliance | **5** | |

### Suggestions (`/suggestions/*`)

| Method | Path | Min Level | Notes |
|---|---|---|---|
| POST | /suggestions | **1** | any authenticated |
| GET | /suggestions | **5** | managers see MANAGEMENT only (query-layer) |
| GET | /suggestions/:id | **5** | OWNER_PRIVATE returns 404 to managers |
| POST | /suggestions/:id/review | **5** | OWNER_PRIVATE returns 404 to managers |

### Finance (`/finance/*`)

| Method | Path | Min Level |
|---|---|---|
| GET | /finance/cash/pending | **5** |
| POST | /finance/cash/reconcile | **5** |
| (payment sockets) | /finance/mpesa/*, /finance/bank/*, /finance/card/* | various |

### Equipment (`/equipment/*`)

| Method | Path | Min Level | Notes |
|---|---|---|---|
| POST | /equipment | **5** | |
| GET | /equipment | **1** | any staff can list |
| GET | /equipment/safety-checks/template | **1** | any staff |
| POST | /equipment/safety-checks | **1** | any staff can submit |
| POST | /equipment/maintenance | **5** | |
| GET | /equipment/maintenance | **5** | |

---

## B. Frontend Nav vs Backend Permission — Mismatch Report

### employee_pwa NAV_ITEMS (AppLayout.tsx)

| Nav Item | Path | Frontend Shows To | Backend Allows | Mismatch |
|---|---|---|---|---|
| Clock | /clock | all (level 1+) | level 1+ (clock-in/out) | ✓ OK |
| Schedule | /schedule | all (level 1+) | **level 5+** (GET /hr/shifts) | ❌ TOO PERMISSIVE — staff see nav + 403 error on load |
| Alerts | /notifications | all (level 1+) | level 1+ (inbox) | ✓ OK |
| Profile | /profile | level 1–4 | JWT claims, no endpoint | ✓ OK (reads JWT only) |
| Waiver | /gate/waiver | water dept only | need to check waiver backend | ⚠️ unverified |
| Safety | /equipment/safety-check | water dept only | level 1+ (any staff) | ✓ OK (dept filter correct) |
| Issue (Band) | /gate/issue | level 3–4 | level 3+ | ✓ OK |
| Check-In | /front-desk/checkin | level 3–4 | level 3+ (check-in endpoint) | ✓ OK |
| Band Lookup | /gate/band-lookup | level 1+ | level 1+ | ✓ OK |
| Inventory | /inventory/count | **level 5+** | level 1+ (GET) / 5+ (write) | ⚠️ RESTRICTIVE — staff can read own dept's inventory but can't see it |
| Restock | /inventory/purchase-request | level 5+ | level 5+ | ✓ OK |
| Meals | /inventory/quick-entry | **level 5+** | **level 1+** (staff-meal endpoint) | ❌ TOO RESTRICTIVE — any staff can log own staff meal, nav hides from them |
| Maintenance | /equipment/maintenance | level 5+ | level 5+ | ✓ OK |
| Manager | /manager | level 5+ | level 5+ | ✓ OK |

### Routes in main.tsx (route-level guards)

| Route | RoleGate | Backend min | Mismatch |
|---|---|---|---|
| /conduct | none (all staff) | level 1+ | ✓ OK |
| /suggestions/new | none (all staff) | level 1+ | ✓ OK |
| /leave | none (all staff) | level 1+ | ✓ OK |
| /absence | none (all staff) | level 1+ | ✓ OK |
| /gate/waiver | none (all staff, nav filters) | need verify | ⚠️ |
| /equipment/safety-check | none (all staff, nav filters) | level 1+ | ✓ OK |
| /gate/issue | RoleGate(3) | level 3+ | ✓ OK |
| /front-desk/checkin | RoleGate(3) | level 3+ | ✓ OK |
| /manager | RoleGate(5) | level 5+ | ✓ OK |
| /inventory/count | RoleGate(5) | level 5+ (write), 1+ (read) | ✓ OK (conservative, defensible) |
| /inventory/quick-entry | RoleGate(5) | staff-meal=1+, others=5+ | ❌ blocks staff from staff-meal |
| /manager/leave | RoleGate(5) | level 5+ | ✓ OK |
| /manager/shifts | RoleGate(5) | level 5+ | ✓ OK |
| /manager/attendance | RoleGate(5) | level 5+ | ✓ OK |
| /manager/cash | RoleGate(5) | level 5+ | ✓ OK |
| /manager/purchases | RoleGate(5) | level 5+ approve=10 | ✓ OK (manager lists, owner approves) |
| /manager/front-desk | RoleGate(5) | level 5+ | ✓ OK |

### Confirmed mismatches — priority list

| # | Mismatch | Direction | Impact |
|---|---|---|---|
| M-1 | Schedule nav visible to level 1–4 but GET /hr/shifts requires 5+ | Too permissive | Staff see Schedule in nav, get 403/empty on load |
| M-2 | Meals nav hidden from level 1–4 but POST /inventory/movements/staff-meal allows level 1+ | Too restrictive | Staff cannot log their own staff meals |
| M-3 | Inventory is flat list — no department picker | UX mismatch | Manager sees all items mixed, violates dept-scoped spec |
| M-4 | /admin proxy missing from Vite config | Config bug | GET /admin/departments crashes with HTML response (FIXED in prior session) |
| M-5 | owner_pwa has no /admin proxy either | Config bug | Same crash in owner PWA when hitting admin endpoints |

---

## C. Inventory Model — InventoryItem

**File:** `app/models/inventory_item.py`

| Field | Type | Nullable | Notes |
|---|---|---|---|
| id | String(36) | PK, UUID | |
| name | String(150) | NOT NULL | Unique per (name, department_id) |
| unit | **String(30)** | NOT NULL | **Free text — no enum constraint.** "kg", "litre", "crate", etc. |
| department_id | String(36) | NOT NULL | FK → departments.id |
| reorder_level | Numeric(12,4) | NOT NULL | Default 0; CHECK ≥ 0 |
| is_watch_list | Boolean | NOT NULL | Default False |
| tolerance_percent | Numeric(5,2) | nullable | Per-item override; None → system default 5% |
| is_staff_food | Boolean | NOT NULL | Default False |
| is_active | Boolean | NOT NULL | Default True |

**No pack_size field exists.** Fix G (quantity intelligence) will need a migration if pack_size is implemented.

**unit field verdict:** Free text String(30). No migration needed for Fix C — the frontend just needs better UX (combobox). The 30-char limit is plenty for "300ml bottle", "70cl bottle", "half-crate of 12", etc.

**GET /inventory/items response includes:**
`id, name, unit, department_id, is_active, current_stock, reorder_level, below_reorder, is_watch_list, is_staff_food`

Department scoping: if actor.role.level < 10 and actor has a department_id → auto-filtered. Owner: sees all or filters by `?department=<id>`.

---

## D. Tested-Broken List

Problems found by tracing every screen against backend:

| # | Screen | Role | Problem |
|---|---|---|---|
| B-1 | ScheduleScreen | Staff (level 1) | Calls GET /hr/shifts → 403. Shows error UI instead of "not your tool" |
| B-2 | ScheduleScreen | Gate staff (level 3) | Same — GET /hr/shifts requires 5+ |
| B-3 | QuickEntryScreen (Meals) | Staff (level 1) | Nav hides it, but staff-meal endpoint allows level 1+. Staff cannot log own meals. |
| B-4 | InventoryCountScreen | Manager | Flat list — no department picker. Manager in Kitchen sees Bar items if owner. |
| B-5 | InventoryCountScreen | Manager | Was crashing on /admin/departments because /admin proxy missing (fixed). |
| B-6 | PurchaseReqScreen | Manager | purchase-requests shows flat list — no department grouping visible for owner. |
| B-7 | CashReconScreen | Manager | Approval button for purchase requests shown to manager, but backend requires level 10. Manager gets 403 on approve. |
| B-8 | ConductScreen | Staff (level 1) | GET /conduct/signatures/:userId — backend allows own, but frontend sends actual user_id. Works if profile exists; 400 if no profile. |
| B-9 | ProfileScreen | Manager (level 5) | Profile nav item hidden (correct). But the screen is still accessible via direct URL /profile — no RoleGate on that route. Low impact. |
| B-10 | owner_pwa | Owner | No /admin proxy in owner_pwa's vite.config.ts — any admin endpoint call would crash |
| B-11 | InventoryCountScreen | All | Unit input is a plain text field — no suggestions. No combobox. |
| B-12 | InventoryCountScreen | All | Item name input is a plain text field — no combobox. |
| B-13 | WaiverScreen | Any staff (URL hack) | No RoleGate — any staff can visit /gate/waiver via direct URL even if not water dept |
| B-14 | QuickEntryScreen | Manager | "Staff meal" section exists but items aren't filtered by is_staff_food on the frontend |

---

## E. Fix Plan (ordered)

```
Fix A — Schedule nav/route: hide from level < 5, add "Your schedule will show here when shifts are assigned" for staff
Fix B — Meals nav: show to level 1+, route accessible without RoleGate(5)
Fix C — unit field: no backend change needed (free text confirmed)
Fix D — Combobox component: build in shared_ui, use in Add Item drawer
Fix E — Inventory department picker: department first, then filtered list
Fix F — Seed real Kurahia data (CLI command)
Fix G — pack_size field: SKIP for now (requires migration + model change — not in scope unless approved)
Fix H — /admin proxy: add to owner_pwa/vite.config.ts
```

---

## F. Final Verification Gate

After fixes, each test account should see exactly this nav:

| Account | Level | Nav items |
|---|---|---|
| teststaff | 1 | Clock, Alerts, Profile, Band |
| testgate | 3 | Clock, Alerts, Profile, Issue, Check-In, Band |
| testmanager | 5 | Clock, Schedule, Alerts, Inventory, Restock, Meals, Maintenance, Manager |
| wachira (owner) | 10 | Clock, Schedule, Alerts, Inventory, Restock, Meals, Maintenance, Manager |

*Note: Waiver + Safety appear for any level if dept contains "water"/"activit"/"aqua".*
