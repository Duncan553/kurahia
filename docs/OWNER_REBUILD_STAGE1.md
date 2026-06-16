# Owner PWA Rebuild — Stage 1: Backend Reality Audit

> Produced: 2026-06-16. Read-only audit of all API endpoints needed for the six owner screens.
> Source files cited by line number. One backend gap identified — minimal fix proposed.

---

## 1. Dashboard Endpoints (Screen 1 — O-1)

All 10 tile endpoints exist and are owner-gated (`_require_owner` = level 10).

| Tile | Method + Path | Source | Min Role | Key Response Fields |
|---|---|---|---|---|
| Revenue Today | `GET /dashboard/overview` | `app/dashboard/core.py:42` | 10 | `revenue.total`, `revenue.by_method`, `revenue.by_tab_type`, `staff.on_duty_names`, `top_alerts`, `week_calendar` |
| Active Guests | `GET /dashboard/bookings` | `app/dashboard/core.py:279` | 10 | `arrivals_today`, `departures_today`, `occupancy_by_type` |
| Staff On Duty | `GET /dashboard/staff` | `app/dashboard/core.py:372` | 10 | `on_duty`, `active_employees`, `absent_today`, `top_performers`, `open_disputes`, `new_suggestions` |
| Judge Alerts | `GET /dashboard/alerts?status=active` | `app/dashboard/core.py:695` | 10 | `[{id, type, severity, description, recommended_action, status, created_at}]` |
| Low Stock | `GET /dashboard/inventory` | `app/dashboard/core.py:160` | 10 | `low_stock_count`, `total_skus`, `items[{name, current_stock, is_low}]` |
| Financial Health | `GET /dashboard/finance` | `app/dashboard/core.py:213` | 10 | `total_revenue`, `reconciliation_status`, `open_shortfalls`, `pending_approvals` |
| Budget Burn | `GET /finance/budgets/status?period=YYYY-MM` | `app/finance/budgets.py:142` | 5 | `[{department, budget, spent, remaining, pct_used, over_budget}]` |
| Feedback Score | `GET /dashboard/feedback` | `app/dashboard/core.py:589` | 10 | `overall_avg`, `by_department`, `recent_comments` |
| Suggestions | `GET /dashboard/suggestions` | `app/dashboard/core.py:506` | 10 | `management: [{id, subject, status, submitted_by}]`, `owner_private: [...]` |
| Equipment | `GET /dashboard/equipment` | `app/dashboard/core.py:668` | 10 | `total`, `due_service[{id, name, type}]`, `in_maintenance` |
| Pending Approvals strip | `GET /inventory/purchase-requests` | `app/inventory/purchases.py:39` | 5 | `[{id, item_name, quantity, status, department, requested_by, estimated_cost, notes}]` |

**⚠ GAP 1 — 7-day daily revenue history (needed for hero bar chart):**
`/finance/dashboard` returns `revenue.today`, `revenue.week`, `revenue.month` totals only.
No per-day breakdown exists. The bar chart in the brief needs daily data.

**Proposed fix:** Add `GET /finance/revenue-history?days=7` — 8-line query, follows existing Payment aggregate pattern. See §7 below.

---

## 2. Purchase Approval (Screen 2 — /purchase-approvals)

### List endpoint
```
GET /inventory/purchase-requests
Source: app/inventory/purchases.py:39
Role:   level 5+ (manager sees own dept; owner sees all)
Filter: Last 30 days, no status query param — filter client-side by status === 'PENDING'
```

Response shape:
```json
[{
  "id": "uuid",
  "item_id": "uuid|null",
  "item_name": "string",
  "quantity": "decimal string",
  "status": "PENDING|APPROVED|REJECTED|FULFILLED",
  "created_at": "ISO 8601",
  "requested_by": "username",
  "department": "string",
  "notes": "string|null",
  "estimated_cost": "decimal string|null"
}]
```

### Approval/rejection endpoint
```
POST /inventory/purchase-requests/<pr_id>/approve
Source: app/inventory/purchases.py:147
Role:   level 10 ONLY ("Only the owner can approve purchase requests.")
Body:   { "action": "approve"|"reject", "notes": "optional string" }
```

> **Important:** There is NO separate `/reject` endpoint. Rejection uses the same `/approve`
> endpoint with `{ "action": "reject" }`. The brief's proposed "POST .../reject" does not exist —
> use `/approve` with `action=reject`.

### Status flow
`PENDING` → (manager adds estimated_cost via `POST .../propose`) → still `PENDING`
→ owner calls `/approve` → `APPROVED` or `REJECTED` → fulfilled via `POST /inventory/purchases`

"Pending owner approval" = `status === 'PENDING'` AND `estimated_cost !== null` (manager proposed).
Pure-PENDING (no cost yet) = staff submitted, manager hasn't proposed yet.

**The approval drawer historical context:** No "last 30 days spend on this item" endpoint exists.
Closest: `GET /inventory/variance` returns variance data. No spend-per-item-history endpoint.
**Proposed**: Show `estimated_cost` from manager proposal. Skip "historical spend" or say "No history" — do not fake.

---

## 3. Settings / Admin Panel (Screen 3 — /settings)

All four admin tabs have real endpoints:

### Tab 1 — Departments
```
GET  /admin/departments                  → app/admin/departments.py:30  (level 5+)
POST /admin/departments                  → app/admin/departments.py:46  (level 10 only)
PATCH /admin/departments/<dept_id>       → app/admin/departments.py:66  (level 10 only)
POST /admin/departments/<dept_id>/disable → app/admin/departments.py:84 (level 10 only)
POST /admin/departments/<dept_id>/enable  → app/admin/departments.py:100 (level 10 only)
```
GET response: `[{id, name, is_active}]`

### Tab 2 — Roles
```
GET  /admin/roles                → app/admin/roles.py:33  (level 5+ — read only in v1)
POST /admin/roles                → app/admin/roles.py:49  (level 10 only)
PATCH /admin/roles/<role_id>     → app/admin/roles.py:76  (level 10 only)
```
GET response: `[{id, name, level, is_active}]`
> Brief says roles are "read-only in v1" — correct, POST exists but UI will be read-only list.

### Tab 3 — Judge Baselines
```
GET  /admin/baselines                         → app/admin/baselines.py:30  (level 10 only)
POST /admin/baselines                         → app/admin/baselines.py:55  (level 10 only)
PATCH /admin/baselines/<baseline_id>          → app/admin/baselines.py:93  (level 10 only)
POST /admin/baselines/<baseline_id>/disable   → level 10 only
POST /admin/baselines/<baseline_id>/enable    → level 10 only
```
GET response: `[{id, item_id, item_name, business_driver, expected_ratio, tolerance_percent, is_active}]`

> The baseline fields are per-item ratios (consumption vs revenue), not system-wide thresholds.
> There are no global "void rate threshold" or "spoilage spike threshold" fields in the model.
> The Settings tab 3 form will show: item, business_driver, expected_ratio, tolerance_percent.

### Tab 4 — Socket Status (read-only diagnostics)
```
GET /finance/mpesa/status            → app/finance/mpesa_daraja.py — {configured: bool, message: str}
GET /finance/bank/status             → app/finance/bank_transfer.py — {configured: bool, message: str}
GET /finance/card/status             → app/finance/card_gateway.py  — {configured: bool, message: str}
GET /notifications/whatsapp/status   → app/notifications/core.py:66 — {configured: bool, message: str}
GET /notifications/push-config       → app/notifications/core.py:94 — {configured: bool, public_key?}
```

### Tab 5 — Personal (font size)
No backend endpoint — localStorage only. Lives in client state.

---

## 4. Staff Screen (Screen 4 — /staff)

### List users
```
GET /auth/users?include_disabled=false  → app/auth/users.py:129
Role: level 5+ (owner sees ALL users; manager sees own dept only)
```
Response: `[{id, username, role, department, is_active, pin_set}]`

> **Missing from user list response:** `last_login` (not stored), `full_name` (in EmployeeProfile, not User).
> For the name column: `GET /hr/profiles` returns `{employee_id, full_name, phone, ...}` — join client-side by `employee_id = user.id`.

### Create user
```
POST /auth/users          → app/auth/users.py:27
Role: strictly-below hierarchy — owner (10) can create manager (5) and staff (1) ✓
Body: { username, role_id, department_id?, password? }
```

### Meta (roles + depts for dropdowns)
```
GET /auth/users/meta      → app/auth/users.py:155
Role: level 5+
```
Response: `{roles: [{id, name, level}], departments: [{id, name}]}` — roles filtered to strictly below caller's level.

### Employee profile (step 2)
```
POST /hr/profiles         → app/hr/profiles.py  (create profile for new user)
Body: { employee_id, full_name, phone, ... }
```

### Management actions
```
POST /auth/users/<id>/activate  → app/auth/users.py:171   (re-activate deactivated user)
POST /auth/deactivate/<id>      → app/auth/routes.py:264  (deactivate — strict hierarchy)
POST /auth/reset-lockout/<id>   → app/auth/routes.py:294  (reset lockout)
```

> Note: deactivate and reset-lockout use `@jwt_required()` not `@require_active_user` — documented
> LOW finding in `docs/PERMISSION_AUDIT.md`. They still work; the kill-switch gap is a future fix.

---

## 5. Finance Screen (Screen 5 — /finance)

### Primary owner finance dashboard
```
GET /finance/dashboard?period=YYYY-MM   → app/finance/reports.py:277
Role: level 10 ONLY
```
Response:
```json
{
  "period": "2026-06",
  "revenue": { "today": "3700.00", "week": "3700.00", "month": "3700.00" },
  "budgets": [{"department": "Kitchen", "budget": "50000", "spent": "12000",
               "remaining": "38000", "pct_used": 24.0, "over_budget": false}],
  "open_shortfalls": 0,
  "no_receipt_purchases": 0,
  "judge_alerts_open": 0
}
```

### Budget burn (department bars)
```
GET /finance/budgets/status?period=YYYY-MM  → app/finance/budgets.py:142
Role: level 5+
```

### Cash pending (for reconciliation cards)
```
GET /finance/cash/pending   → app/finance/cash.py  (manager+ pending cash reconciliations)
```

### M-Pesa / Bank / Card pending
```
GET /finance/mpesa/pending  → app/finance/mpesa.py
GET /finance/bank/pending   → app/finance/bank_transfer.py
```

### Three-way reconciliation (date picker)
```
GET /finance/reconciliation?date=YYYY-MM-DD  → app/finance/reports.py:39
```

### ⚠ GAP 1 (same as dashboard): No daily revenue breakdown
For the 30-day daily bar chart, there's no endpoint. `/finance/dashboard` gives period totals only.
Same fix: add `GET /finance/revenue-history?days=30`. See §7.

---

## 6. Bookings Screen (Screen 6 — /bookings)

### List bookings
```
GET /bookings?status=&date=YYYY-MM-DD   → app/bookings/core.py:305
Role: level 1+ (any staff)
Filters: resource_id, status, date (check_in_planned_utc on that date)
```
Response: `[{id, status, guest_name, guest_phone, resource_id, resource_name,
             check_in_planned_utc, check_out_planned_utc, base_total, number_of_guests}]`

### Today's dashboard data
```
GET /bookings/today    → app/bookings/dashboard.py:24
Role: level 1+
```
Returns: `{arrivals: [...], departures: [...], occupancy: [...], water_bookings: [...]}`

### Cancel booking (owner override)
```
POST /bookings/<id>/cancel   → app/bookings/core.py:280
Role: level 1+
Body: { idempotency_key, reason? }
```

> There is no booking detail endpoint `GET /bookings/<id>`. Detail is embedded in the list response.
> The detail drawer will use the already-fetched list row data — no extra request needed.

---

## 7. The One Backend Addition Needed

**What:** `GET /finance/revenue-history?days=7` (or `?days=30`)
**Why:** Dashboard hero bar chart and Finance daily chart both need per-day revenue.
**Where to add:** `app/finance/reports.py` — follows existing `_rev()` pattern exactly.

```python
@reports_bp.get("/revenue-history")
@require_active_user
def revenue_history():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can view revenue history."}), 403
    days = min(int(request.args.get("days", 7)), 90)
    now  = datetime.now(timezone.utc)
    result = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        raw = db.session.query(func.sum(Payment.amount)).filter(
            Payment.created_at_utc >= day_start,
            Payment.created_at_utc < day_end,
        ).scalar()
        result.append({
            "date":    day_start.strftime("%Y-%m-%d"),
            "revenue": str(Decimal(str(raw)) if raw else Decimal("0")),
        })
    return jsonify(result), 200
```

This is 15 lines, no new model, no migration, follows the existing `_rev()` helper pattern.
URL: `GET /finance/revenue-history?days=7` or `?days=30`.

---

## 8. Confirmed Non-Issues

| Concern from brief | Reality |
|---|---|
| "POST .../reject endpoint" | Doesn't exist — use `POST .../approve` with `{"action":"reject"}` |
| Owner creates managers from owner PWA | `POST /auth/users` with `role_id=manager_role_id` — hierarchy check allows it ✓ |
| Budget endpoints owner-gated | POST/PATCH on budgets require level 10 ✓ |
| Baselines CRUD owner-gated | All baseline mutations require level 10 ✓ |
| Socket status endpoints | All 5 exist, all return `{configured: bool, message: str}` ✓ |
| Judge alerts status filter | `GET /judge/alerts?status=OPEN|ACKNOWLEDGED|ALL` ✓ |
| Dashboard alerts | `GET /dashboard/alerts?status=active` — default "active" = OPEN only ✓ |

---

## 9. Tailwind Token Additions Needed

The brief adds one cool-tone data-viz accent: `accent-cool = teal-blue #3C7A8C`.
Add to `shared_ui/src/tokens.css` and `shared_ui/tailwind.config.js`.

No other color tokens are needed. The 5-hue constraint (cream-card, cream-alt, primary-main,
accent-cool, one status) is satisfied by existing tokens + this one addition.

---

## 10. Summary: Backend Ready / Not Ready

| Screen | Backend ready? | Gap |
|---|---|---|
| 1. Dashboard | ✅ Mostly — 10 tiles all backed | ⚠ Hero bar chart needs `GET /finance/revenue-history` |
| 2. Purchase Approvals | ✅ Ready | Rejection uses `/approve` with `action=reject`, not separate route |
| 3. Settings / Admin | ✅ Ready | All 4 tabs backed by real endpoints |
| 4. Staff | ✅ Ready | Full name from `GET /hr/profiles`, join client-side |
| 5. Finance | ✅ Mostly ready | ⚠ Daily chart needs `GET /finance/revenue-history` |
| 6. Bookings | ✅ Ready | No `/bookings/<id>` detail endpoint — use list row data in drawer |

**One backend addition required before Stage 2:** Add `GET /finance/revenue-history` to `app/finance/reports.py`.
Everything else is wired. Backend is production-ready for 5 of 6 screens today.

---

*End of Stage 1. Commit this document. Await "PROCEED TO STAGE 2".*
