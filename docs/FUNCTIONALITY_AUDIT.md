# Functionality Weakness Audit — 2026-06-23

**Auditor:** Automated QA (Claude)
**Backend:** localhost:5000
**Method:** Live API calls (curl) against running dev server

## SUMMARY

| Category          | Count |
|-------------------|-------|
| BROKEN            | 2     |
| WRONGLY-ALLOWED   | 1     |
| MISSING           | 4     |
| WORKING CORRECTLY | 14    |

---

## BROKEN (2)

### B-1: Inventory item created with garbage department_id

**Endpoint:** `POST /inventory/items`
**Severity:** HIGH

```
POST /inventory/items
{"name":"Audit Test Item","unit":"kg","department_id":"NEED_DEPT_ID"}
→ 201 Created (should be 400/404)
```

**Root cause:** `items.py` line 86 only checks `if not dept_id` (truthy check) but never validates that `department_id` references an actual Department record. SQLite dev mode does NOT enforce `PRAGMA foreign_keys=ON`, so the FK constraint on `inventory_items.department_id → departments.id` is silently ignored.

**Result:** Orphaned item exists in DB with `department_id="NEED_DEPT_ID"`. It appears in owner list queries. It won't crash (the code uses `item.department.name if item.department else "unknown"`) but it pollutes the catalog.

**Fix:** Add `dept = db.session.get(Department, dept_id)` + 404 check before creation. Also enable `PRAGMA foreign_keys=ON` for SQLite via a `@listens_for(Engine, "connect")` hook in `extensions.py`.

**File:** `/home/wachira/kurahia/app/inventory/items.py` lines 68-98

---

### B-2: Manager cannot see items they created in another department

**Endpoint:** `GET /inventory/items?include_disabled=true`
**Severity:** MEDIUM

Manager2 (dept: "general management") creates an item in Kitchen department → 201 success. Then `GET /inventory/items?include_disabled=true` as the same manager returns the item as **missing** — the department scope filter on line 178 restricts managers to their own department's items.

```
POST /inventory/items {"name":"AuditSugar77","unit":"kg","department_id":"<kitchen_id>"} → 201
GET /inventory/items?include_disabled=true → item NOT in results
```

**Root cause:** `items.py` line 178: `if actor.role.level < 10 and actor.department_id: query = query.filter_by(department_id=actor.department_id)`. Create has no such filter, but list does. A manager can create cross-department items but then cannot see, edit, or disable them.

**File:** `/home/wachira/kurahia/app/inventory/items.py` lines 176-179

---

## WRONGLY-ALLOWED (1)

### W-1: GET /admin/roles leaks all role IDs/levels to managers

**Endpoint:** `GET /admin/roles`
**Severity:** LOW (informational leak — privilege escalation still blocked)

```
GET /admin/roles (as manager2, level 5)
→ 200: returns ALL roles including owner (level 10) and manager (level 5) with their UUIDs
```

The `/auth/users/meta` endpoint correctly filters roles to only those below the actor's level. But `/admin/roles` uses `level < 5` (manager check), showing a manager the owner role's UUID and level. While the account creation endpoint blocks privilege escalation (`"Cannot create an account at or above your own role level."`), a manager shouldn't see the owner role's internal ID at all.

**File:** `/home/wachira/kurahia/app/admin/roles.py` line 35: `if actor.role.level < 5`

---

## MISSING (4)

### M-1: User "waterlead" does not exist in seed data

The audit spec called for a `waterlead` user. No such user exists in the database. Login returns `"Invalid credentials."` (401). All seeded users:

```
wachira (owner), manager2, headchef, barmgr, spamgr, gate1, waiter1, waiter2, kitchen2, testqastaff
```

No water/pool department lead exists.

---

### M-2: SQLite FK enforcement disabled in dev

`PRAGMA foreign_keys` is never set to ON anywhere in the codebase (`config.py`, `extensions.py`, `__init__.py`). All FK constraints defined in models are silently ignored in SQLite dev mode. This allowed B-1 above.

**Note:** Postgres enforces FKs by default, so production is safe. But dev/test environments are running without this safety net, meaning bugs like B-1 pass all existing tests.

---

### M-3: No application-level department validation on inventory item create

As documented in B-1, the `POST /inventory/items` endpoint trusts the client-supplied `department_id` without verifying it exists. Even with FK enforcement, this is a missing validation that should return a clean 404 error.

---

### M-4: Fake menu_item_id returns 400, not 404

```
POST /orders {"items":[{"menu_item_id":"fake-item-id-nonexistent"}]}
→ 400: "Menu item 'fake-item-id-nonexistent' is disabled or does not exist."
```

The error message conflates "doesn't exist" with "disabled." A non-existent item should return 404; a disabled item should return a 400 or 409 with a distinct message. Minor UX issue.

**File:** `/home/wachira/kurahia/app/pos/orders.py` line 97

---

## WORKING CORRECTLY (14)

### Manager Tests

| Test | Result | Detail |
|------|--------|--------|
| POST /inventory/items (valid dept) | PASS (201) | Item created successfully |
| PATCH /inventory/items/:id | PASS (200) | reorder_level updated |
| POST /inventory/items/:id/disable | PASS (200) | is_active=false |
| Manager creates MANAGER-level account | PASS (403) | "Cannot create an account at or above your own role level." |
| Manager creates OWNER-level account | PASS (403) | Same hierarchy enforcement |

### Waiter Tests

| Test | Result | Detail |
|------|--------|--------|
| Order sold-out item | PASS (409) | "Grilled Tilapia is sold out" — correct stock pre-check |
| Order fake menu item | PARTIAL (400) | Rejects cleanly but wrong HTTP code (see M-4) |
| Double-submit idempotency_key | PASS (200) | Returns `{"duplicate":true}`, no second order created |

### Gate Tests

| Test | Result | Detail |
|------|--------|--------|
| Issue band (CASH) | PASS (201) | Band #1 issued, tab created with -3000 balance (credit) |
| Double-tap same idempotency_key | PASS (200) | Returns same band with `"duplicate":true` |
| Lookup band #1 | PASS (200) | Band details returned correctly |

### Cross-Role Security

| Test | Result | Detail |
|------|--------|--------|
| waiter1 → /dashboard/overview | PASS (403) | "Manager or above required." |
| waiter1 → /judge/alerts | PASS (403) | "Owner only." |
| waiter1 → /admin/settings | PASS (403) | "Only the owner can view system settings." |
| waiter1 → POST /inventory/items | PASS (403) | "Manager or above required." |
| manager2 → /judge/alerts | PASS (403) | "Owner only." |
| gate1 → /dashboard/overview | PASS (403) | "Manager or above required." (level 3 < 5) |
| waiter1 → GET /suggestions | PASS (403) | "Manager or above required." |

### OWNER_PRIVATE Suggestion Flow

| Test | Result | Detail |
|------|--------|--------|
| Waiter submits OWNER_PRIVATE | PASS (201) | Anonymous submission accepted |
| Manager GET /suggestions | PASS | 0 OWNER_PRIVATE visible (query-layer filter) |
| Owner GET /suggestions | PASS | 2 OWNER_PRIVATE visible |

---

## Judge Alert Types — Code Audit

All 8 specified alert types exist in the codebase:

| Alert Type | File | Status |
|------------|------|--------|
| BUDGET_EXCEEDED | `app/judge/engine.py:179` | IMPLEMENTED |
| COST_VARIANCE | `app/judge/engine.py:144` | IMPLEMENTED |
| RATIO | `app/judge/engine.py:228` | IMPLEMENTED |
| SPOILAGE_SPIKE | `app/judge/engine.py:270` | IMPLEMENTED |
| CASH_SHORTFALL_PATTERN | `app/finance/cash.py:143` | IMPLEMENTED |
| MPESA_FLAGGED | `app/finance/mpesa.py:157` | IMPLEMENTED |
| BANK_FLAGGED | `app/finance/bank.py:155` | IMPLEMENTED |
| VOID_ABUSE | `app/finance/analytics.py:57` | IMPLEMENTED |

Note: CASH_SHORTFALL_PATTERN, MPESA_FLAGGED, BANK_FLAGGED, and VOID_ABUSE are implemented outside the judge engine proper — they live in their respective finance modules but fire JudgeAlerts through the same `fire_alert_if_absent` service.

---

## Design Notes (Not Bugs)

1. **dashboard/overview is manager-accessible (level 5)** while all other dashboard endpoints require owner (level 10). This appears intentional — managers need a summary view. However, it exposes total revenue, staff on-duty counts, booking counts, and top 3 judge alerts to all managers.

2. **dashboard/alerts/acknowledge and action-taken at manager level** — managers can acknowledge and resolve alerts shown in the overview, which makes operational sense.

3. **Band tab_balance of -3000.00** — this is correct. Negative balance means 3000 credit from entry fee. The tab balance formula is `SUM(charges) - SUM(payments)`, and the entry fee payment creates available credit.
