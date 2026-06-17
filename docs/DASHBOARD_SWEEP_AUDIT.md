# Dashboard Completion Sweep — Backend Audit (Stage 0)

> Conducted 2026-06-17. Read-only. No code changes.

---

## Summary

| Hub | Status | Backend Work Needed |
|-----|--------|-------------------|
| 1. Kitchen Head Chef | **Mostly ready** | dept filter on attendance, events-by-dept (workaround available) |
| 2. Bar Manager | **Mostly ready** | Same gaps as Kitchen (identical endpoints) |
| 3. Spa & Gym | **Mostly ready** | dept filter on attendance + bookings-by-dept |
| 4. Water Activities | **Partial** | equipment dept filter, safety check list, manager-level equipment dashboard |
| 5. Housekeeping | **Significant gap** | New RoomStatus model + endpoints needed |
| 6. Grounds & Cycling | **Partial** | equipment dept filter, same attendance gap |
| 7. Manager Hub additions | **Mostly ready** | Lower revenue endpoints to manager level |
| 8. Frontline verification | **Done** | Level-1 routes confirmed, OWNER_PRIVATE structurally invisible |

**Build order (easiest first):**
1. Hub 8 — Frontline verification (already done, just confirm)
2. Hub 7 — Manager additions (1-line access change + frontend tiles)
3. Hub 1 — Kitchen (frontend-heavy, most endpoints exist)
4. Hub 2 — Bar (identical to Kitchen, copy + retheme)
5. Hub 3 — Spa & Gym (needs bookings-by-dept filter)
6. Hub 4 — Water Activities (needs safety check endpoint + equipment filter)
7. Hub 6 — Grounds & Cycling (needs equipment filter, otherwise similar to Water)
8. Hub 5 — Housekeeping (needs new model — most work)

---

## Missing Endpoints — Ranked by Effort

### Priority 1: 1-line filter additions

| # | What | Affects | File | Effort |
|---|------|---------|------|--------|
| 1 | `?department_id=` on GET `/hr/attendance/today` | Hubs 1-6 | `app/hr/attendance.py:38` | 1-line filter |
| 2 | `?department_id=` + `?equipment_type=` on GET `/equipment` | Hubs 4, 6 | `app/equipment/core.py:43` | 1-line filter |
| 3 | `?department_id=` on GET `/bookings` (join BookableResource) | Hub 3 | `app/bookings/core.py:195` | 3-line join+filter |

### Priority 2: Access level adjustments (1-line)

| # | What | Affects | File | Effort |
|---|------|---------|------|--------|
| 4 | Lower `/dashboard/overview` to manager level (10→5) | Hub 7 | `app/dashboard/core.py:42` | 1-line |
| 5 | Lower `/dashboard/equipment` to manager level (10→5) | Hub 4 | `app/dashboard/core.py:668` | 1-line |

### Priority 3: New small endpoints (~15-30 lines)

| # | What | Affects | Model | Effort |
|---|------|---------|-------|--------|
| 6 | GET `/equipment/<id>/safety-checks` (list recent) | Hub 4 | SafetyCheck (exists) | ~15 lines |
| 7 | Events filtered by dept involvement (query param) | Hubs 1, 2 | EventAssignment + join | ~20 lines |

### Priority 4: New model + endpoints

| # | What | Affects | Effort |
|---|------|---------|--------|
| 8 | RoomStatus model + CRUD (clean/dirty/occupied/ready) | Hub 5 | New model + migration + 3-4 endpoints |

---

## Hub Details

### Hub 1 — Kitchen Head Chef

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Kitchen stock levels | GET `/inventory/items` (auto-scoped to dept) | **EXISTS** |
| Variance from last count | GET `/inventory/variance?dept=<id>` | **EXISTS** |
| Purchase requests (own dept) | GET `/inventory/purchase-requests` (auto-scoped) | **EXISTS** |
| Team attendance today | GET `/hr/attendance/today` | **EXISTS, NO dept filter** |
| Events needing prep | GET `/events/upcoming` + `/events/<id>/inventory` | **EXISTS** (no dept filter, workaround: client-side) |
| Kitchen budget remaining | GET `/finance/budgets/status` (returns all depts) | **EXISTS** (filter client-side) |
| Kitchen queue | GET `/kitchen/queue` | **EXISTS** |
| Spoilage watch-list | GET `/inventory/items` (is_watch_list=true, auto-scoped) | **EXISTS** |

### Hub 2 — Bar Manager

Identical endpoint set to Kitchen, department=BAR. Same gaps. Same workarounds.

### Hub 3 — Spa & Gym

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Today's spa appointments | GET `/bookings?resource_id=<spa_id>&date=today` | **EXISTS** (by resource_id, not dept) |
| Spa product stock | GET `/inventory/items` (auto-scoped) | **EXISTS** |
| Guest feedback this week | GET `/feedback?department_id=<id>&from=<date>` | **EXISTS** |
| Team attendance | GET `/hr/attendance/today` | **NO dept filter** |
| Spa budget | GET `/finance/budgets/status` | **EXISTS** (all depts) |

### Hub 4 — Water Activities

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Today's water bookings | GET `/bookings?resource_id=<id>` or `/bookings/availability?resource_type=WATER_ACTIVITY` | **EXISTS** |
| Equipment status | GET `/equipment` | **EXISTS, NO dept/type filter** |
| Maintenance overdue | GET `/dashboard/equipment` (is_due_service) | **EXISTS, OWNER-ONLY** |
| Safety check status | POST `/equipment/<id>/safety-check` (submit only) | **MISSING read endpoint** |
| Fuel/oil/jacket stock | GET `/inventory/items` (auto-scoped) | **EXISTS** |
| Pending waivers today | GET `/front-desk/today` (includes pending_waivers) | **EXISTS** (level 3+) |

### Hub 5 — Housekeeping

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Room status grid | None | **MISSING — needs new model** |
| Today's departures | GET `/bookings/today` (departures array) | **EXISTS** |
| Linen/toiletry stock | GET `/inventory/items` (auto-scoped) | **EXISTS** |
| Team attendance | GET `/hr/attendance/today` | **NO dept filter** |
| Budget | GET `/finance/budgets/status` | **EXISTS** |

### Hub 6 — Grounds & Cycling

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Bike status | GET `/equipment` | **EXISTS, NO dept/type filter** |
| Today's bookings | GET `/bookings?resource_id=<field_id>` | **EXISTS** |
| Team + budget | Same gaps as all hubs | **Partial** |

### Hub 7 — Manager Additions

| Needed Data | Endpoint | Status |
|-------------|----------|--------|
| Today's revenue | GET `/dashboard/overview?period=today` | **EXISTS, OWNER-ONLY** |
| Open disputes | GET `/disputes?status=OPEN` | **EXISTS** (manager sees non-owner-only) |
| Tier 1 suggestions | GET `/suggestions?status=NEW` | **EXISTS** (manager sees MANAGEMENT category) |
| Budget burn | GET `/finance/budgets/status` | **EXISTS** (manager+) |
| Daily revenue entry | None (revenue flows through POS payments) | **MISSING if manual entry needed** |

### Hub 8 — Frontline Staff (Level 1)

**Confirmed accessible at level 1:**
- Clock in/out + status
- Schedule (shifts via events)
- Notifications inbox
- Conduct rules + signing
- Suggestions (including OWNER_PRIVATE anonymous)
- Leave requests (own)
- Equipment safety checks
- Staff meal recording
- Guest feedback submission

**Confirmed NOT accessible at level 1:**
- Inventory management (level 5+)
- Purchase requests (level 5+)
- Menu management (level 5+)
- Staff accounts (level 5+)
- Finance/budgets (level 5+)
- Judge alerts (level 10)
- Dashboard overview (level 10)

**OWNER_PRIVATE:** Fully implemented. Structural authorization — OWNER_PRIVATE suggestions are invisible to managers (level < 10) via WHERE clause exclusion, not permission check. Cannot be bypassed by direct ID access (returns 404).

---

## Recommended Build Order

1. **Hub 8** — Verify frontline (no build needed, already confirmed above)
2. **Hub 7** — Manager additions (1-line access change on overview endpoint + 4-5 new tiles)
3. **Hubs 1+2** — Kitchen + Bar (same component, different station filter, most endpoints exist)
4. **Hub 3** — Spa & Gym (similar pattern, add bookings dept filter)
5. **Hub 4** — Water Activities (needs safety check read endpoint + equipment filter)
6. **Hub 6** — Grounds & Cycling (needs equipment filter, otherwise lightweight)
7. **Hub 5** — Housekeeping (needs RoomStatus model — defer or build last)

**Shared backend work (do once, unlocks multiple hubs):**
- Department filter on `/hr/attendance/today` — unlocks attendance tile for ALL hubs
- Department/type filter on `/equipment` — unlocks Hubs 4 + 6
