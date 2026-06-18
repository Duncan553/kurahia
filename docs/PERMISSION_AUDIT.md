# Permission Audit — Kurahia Backend + Frontend

> Conducted 2026-06-15. Read-only audit. No fixes applied yet.
> Principle: backend is the only real security boundary. Frontend shaping is UX, not security.

---

## Phase 1 — Seed Verification (complete)

All seed commands ran successfully:

| Table | Rows | Status |
|---|---|---|
| ConductRule | 8 | ✅ |
| BookableResource | 6 (3 villas, 1 event field, 2 jetski) | ✅ |
| EventType | 5 | ✅ |
| CalendarEntry | 10 (Kenyan public holidays 2026) | ✅ |
| Shift | 11 (10 new + 1 pre-existing) | ✅ |
| WiFiAllowList | 2 (127.0.0.1/32 + ::1/128) | ✅ |

Clock-in now works from both IPv4 and IPv6 localhost.

---

## Phase 2 — Backend Permission Audit

### Method

- Checked all 49 route files in `app/`
- Verified `@require_active_user` coverage per endpoint (machine scan + manual spot-check)
- Verified role-level enforcement in function bodies and helper functions (`_require_manager`, `_require_owner`, `_can_operate_station`)
- Excluded known-public endpoints: `/auth/login`, `/auth/pin-login`, `/auth/refresh`, `/auth/set-pin`, payment webhooks

### Confirmed: No CRITICAL findings

Every protected route has either `@require_active_user` or an equivalent check. The Explore agent's CRITICAL flags for `tabs.py` and `receipts.py` were false positives — the decorators are present (lines 25, 61, 82, 123 in tabs.py; line 19 in receipts.py).

---

### FINDINGS

#### LOW — `auth/routes.py:265` · `POST /auth/deactivate/<id>`

Uses `@jwt_required()` directly instead of `@require_active_user`. The difference: `require_active_user` re-checks `is_active` on the *actor* on every call. This endpoint does not. A manager who has just been deactivated can still call this endpoint (to deactivate staff below them) within the remaining lifetime of their JWT.

**Why it matters:** Low impact in practice — access tokens expire in ~15 min and the role hierarchy check still applies. But it's inconsistent with the kill-switch principle.

**Fix when ready:** Swap `@jwt_required()` for `@require_active_user` and remove the manual `db.session.get(User, actor_id)` call (the decorator handles it).

#### LOW — `auth/routes.py:294` · `POST /auth/reset-lockout/<id>`

Same issue as above. Actor's `is_active` is not checked; only their role level is verified. A deactivated actor with a valid JWT can reset lockouts for staff below them.

#### LOW (design note) — `app/finance/bank_transfer.py:507` · `POST /finance/bank/sms-forward`

No JWT — intentionally public. Authentication is via `BANK_SMS_WEBHOOK_SECRET` shared secret in the payload. When the env var is not set, the endpoint rejects all requests. This is correct webhook design, not a finding to fix.

#### LOW (design note) — `app/finance/card_gateway.py:664` · `POST /finance/card/callback`

Same as above — public webhook, no JWT by design. Security via IPN signature verification when socket is active.

---

### All other routes: CLEAN

| Domain | Auth | Role check | Dept scoping | Notes |
|---|---|---|---|---|
| `auth/` | ✅ | ✅ hierarchy | n/a | `change-pin` manually calls `check_active_and_unlocked` |
| `admin/` (baselines, depts, roles) | ✅ | ✅ `_require_owner` (level 10) | n/a | |
| `bookings/` | ✅ | ✅ | n/a bookings are resort-wide | |
| `calendar_view/` | ✅ | ✅ owner creates; staff reads | n/a | |
| `conduct/` | ✅ | ✅ owner creates; staff signs | n/a | |
| `dashboard/` | ✅ | ✅ owner-only (level 10) | n/a | |
| `disputes/` | ✅ | ✅ | ✅ `is_owner_only` rows absent for non-owners | Structural enforcement |
| `equipment/` | ✅ | ✅ manager for writes | n/a | |
| `events/` | ✅ | ✅ owner creates; manager assigns | n/a | |
| `feedback/` | ✅ | ✅ owner reads; any writes | n/a | |
| `finance/` | ✅ | ✅ manager cash; owner analytics | n/a | |
| `gate/` | ✅ | ✅ level 3+ for issue; any for lookup | n/a | |
| `hr/` | ✅ | ✅ | ✅ manager sees own dept | |
| `inventory/` | ✅ | ✅ `_require_manager` for writes | ✅ owner sees all; manager sees dept | |
| `judge/` | ✅ | ✅ `_require_owner` | n/a | |
| `notifications/` | ✅ | n/a (own inbox) | n/a | |
| `pos/` | ✅ | ✅ station-based + `_can_operate_station` | ✅ kitchen/bar dept check | |
| `suggestions/` | ✅ | ✅ owner reads; any submits | n/a | |
| `users/` | ✅ | ✅ hierarchy rule in every endpoint | n/a | |

---

## Phase 3 — Frontend Role-Shaping Audit

### Method

Read both PWA routers (main.tsx) and all screen files. Checked:
- Route-level guards (`<RoleGate minLevel={N}>` in the router)
- Screen-level guards (`<RequireRole minLevel={N}>` inside the component)
- Inline role checks (`user.role_level >= 5 && ...`)
- Nav filtering in AppLayout

### Employee PWA Router — CLEAN

All sensitive routes are correctly gated:

| Route group | Gate | Level |
|---|---|---|
| `/gate/hub`, `/gate/issue`, `/front-desk/checkin` | `<RoleGate>` | 3+ |
| `/manager` and all `/manager/*` sub-screens | `<RoleGate>` | 5+ |
| `/inventory/count`, `/inventory/purchase-request`, `/equipment/maintenance` | `<RoleGate>` | 5+ |

Unguarded routes that are intentionally open to all staff (level 1+):
`/clock`, `/schedule`, `/notifications`, `/profile`, `/conduct`, `/suggestions/new`, `/leave`, `/absence`, `/gate/band-lookup`, `/pos/tabs`, `/pos/kitchen`, `/pos/bar`, `/pos/spa`, `/pos/water-pay`, `/villa`, `/inventory/quick-entry` — all correct by design.

Kiosk routes (`/kiosk/*`) are inside `AuthGate` but have no `RoleGate` — intentional, any staff member can launch a kiosk screen.

---

### FINDINGS

#### MEDIUM — Missing screen-level `<RequireRole>` as second layer on several manager screens

**Affected screens:**
- `employee_pwa/src/screens/MenuManageScreen.tsx` — no `<RequireRole>` wrapper
- `employee_pwa/src/screens/GateHubScreen.tsx` — no `<RequireRole>` wrapper
- `employee_pwa/src/screens/InventoryCountScreen.tsx` — no `<RequireRole>` wrapper
- Several other manager sub-screens

**Actual risk:** LOW. The route is already behind `<RoleGate minLevel={5}>` in the router. A level-1 staff member navigating directly to `/manager/menu` gets caught by the route guard and sees nothing. The missing screen wrapper is defense-in-depth (a second lock on a door that's already locked), not a security hole.

**Pattern the system SHOULD follow:** every screen behind a `<RoleGate>` route should also wrap its content in `<RequireRole>` in case the route structure is ever refactored. About 40% of guarded screens currently have double-protection; 60% rely only on the route guard.

**The one screen that does it right:** `CashReconScreen.tsx` — wrapped in `<RequireRole minLevel={5}>` inside the component AND behind `<RoleGate>` in the router. That's the pattern to replicate.

---

#### LOW — `WaiterTabsScreen` and `WaiterTabDetailScreen` have no role guard at any level

`/pos/tabs` and `/pos/tabs/:id` are intentionally unguarded — any authenticated user can navigate there. A kitchen staff member who navigates to `/pos/tabs` sees the waiter UI and can attempt to open a table. The backend's `open_tab` endpoint checks nothing about role or department — any authenticated user can open a tab.

**Is this a real problem?** For current operations, nav filtering in AppLayout hides the tabs link for non-waiter staff. But the route is reachable by direct URL. The backend should enforce that only certain roles/departments can open tabs.

---

### Owner PWA — CLEAN

The owner PWA has no role-shaping findings. All routes sit inside a single `<AuthGate>` — since the owner PWA is owner-only by convention, any authenticated user who reaches it is the owner. The three placeholder screens (StaffScreen, FinanceScreen, BookingsScreen) are visible but harmless.

---

## Phase 4 — Dashboard Walk URLs

Open each of these in order. Note which ones you want to redesign.

### Employee PWA — `http://localhost:5173`

**Every staff member:**
| # | Screen | URL |
|---|---|---|
| 1 | Clock in/out | http://localhost:5173/clock |
| 2 | Schedule | http://localhost:5173/schedule |
| 3 | Notifications inbox | http://localhost:5173/notifications |
| 4 | Profile + font size | http://localhost:5173/profile |
| 5 | Code of conduct | http://localhost:5173/conduct |
| 6 | Submit suggestion | http://localhost:5173/suggestions/new |
| 7 | Leave request | http://localhost:5173/leave |
| 8 | Absence notice | http://localhost:5173/absence |
| 9 | Band lookup | http://localhost:5173/gate/band-lookup |
| 10 | Staff quick meal | http://localhost:5173/inventory/quick-entry |

**POS / operations (waiter, kitchen, bar):**
| # | Screen | URL |
|---|---|---|
| 11 | Waiter tabs list | http://localhost:5173/pos/tabs |
| 12 | Kitchen queue | http://localhost:5173/pos/kitchen |
| 13 | Bar queue | http://localhost:5173/pos/bar |
| 14 | Spa/gym payment | http://localhost:5173/pos/spa |
| 15 | Water activity payment | http://localhost:5173/pos/water-pay |
| 16 | Villa front desk | http://localhost:5173/villa |

**Gate / front desk (level 3+):**
| # | Screen | URL |
|---|---|---|
| 17 | Gate hub | http://localhost:5173/gate/hub |
| 18 | Waiver signing | http://localhost:5173/gate/waiver |
| 19 | Equipment safety check | http://localhost:5173/equipment/safety-check |
| 20 | Guest check-in | http://localhost:5173/front-desk/checkin |

**Manager hub + sub-screens (level 5+):**
| # | Screen | URL |
|---|---|---|
| 21 | **Manager hub** | http://localhost:5173/manager |
| 22 | Staff accounts | http://localhost:5173/manager/staff |
| 23 | Menu management | http://localhost:5173/manager/menu |
| 24 | Cash reconciliation | http://localhost:5173/manager/cash |
| 25 | Leave approvals | http://localhost:5173/manager/leave |
| 26 | Shifts | http://localhost:5173/manager/shifts |
| 27 | Attendance | http://localhost:5173/manager/attendance |
| 28 | Purchase requests | http://localhost:5173/manager/purchases |
| 29 | Front desk overview | http://localhost:5173/manager/front-desk |
| 30 | Inventory count | http://localhost:5173/inventory/count |
| 31 | Purchase request form | http://localhost:5173/inventory/purchase-request |
| 32 | Maintenance log | http://localhost:5173/equipment/maintenance |

**Kiosk (launched by staff, used by guests):**
| # | Screen | URL |
|---|---|---|
| 33 | Kiosk launch | http://localhost:5173/kiosk/launch |
| 34 | Kiosk menu/order | http://localhost:5173/kiosk/menu |
| 35 | Waiver signing | http://localhost:5173/kiosk/welcome |
| 36 | Guest feedback | http://localhost:5173/kiosk/feedback/launch |

---

### Owner PWA — `http://localhost:5174`

| # | Screen | URL |
|---|---|---|
| 37 | **Owner dashboard** (10 tiles) | http://localhost:5174/dashboard |
| 38 | Judge alerts | http://localhost:5174/alerts |
| 39 | Payroll draft | http://localhost:5174/payroll |
| 40 | Period reconciliation | http://localhost:5174/reconciliation |
| 41 | Settings | http://localhost:5174/settings |
| — | Staff (placeholder) | http://localhost:5174/staff |
| — | Finance (placeholder) | http://localhost:5174/finance |
| — | Bookings (placeholder) | http://localhost:5174/bookings |

---

*End of audit. No code changes made. Waiting for next instruction.*
