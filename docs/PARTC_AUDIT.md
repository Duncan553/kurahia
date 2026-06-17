# Part C Backend Audit (Stage C0)

> Conducted 2026-06-17. Read-only.

---

## Period Close

**EXISTS.** `POST /finance/close-period` at `app/finance/reports.py:198`.
- Requires: date (YYYY-MM-DD), safe_count (physical cash), optional notes
- Computes: expected_total_cash from CashReconciliations in period
- Records: PeriodClose row (BALANCED/SHORT/OVER), difference = safe_count - expected
- Guards: manager+ can close; only owner can re-close an already-closed period
- Idempotent via idempotency_key
- **What it freezes:** Snapshots expected_total_cash at close time. Does NOT lock further writes to the period. It's an observation record, not a write lock.

## Business Day Concept

**DOES NOT EXIST.** Everything uses calendar midnight UTC.
- `parse_date_bounds("2026-06-17")` → `(2026-06-17 00:00 UTC, 2026-06-18 00:00 UTC)`
- `app/hr/attendance.py:43` — `day_start = datetime(today.year, today.month, today.day)`
- `app/bookings/dashboard.py:30` — same pattern
- `app/finance/reports.py:58` — same pattern
- No Africa/Nairobi timezone awareness — all boundaries are midnight UTC
- No configurable day-start setting exists anywhere

**Needed:** A `business_day_start` setting (default 06:00 Africa/Nairobi), `business_day_for(timestamp)` helper, update all "today" boundaries.

## Reconciliation Status

**PARTIALLY EXISTS.**
- `CashReconciliation` model tracks per-cashier cash handover (expected vs actual)
- `PaymentReconciliation` model tracks M-Pesa/bank/card matching
- `GET /finance/reports/reconciliation-status?date=YYYY-MM-DD` at `app/finance/reports.py:132` returns:
  - cash_recon count, total expected vs actual
  - per-method reconciliation status
  - period_closed boolean
- **Cannot say "is venue X reconciled"** — reconciliation is per-cashier, not per-venue. A venue is implicitly reconciled when all its cashiers have reconciled.
- **"Reconciled" defined as:** all CASH payments for the period have been claimed in a CashReconciliation row.

## Deactivation Fields

| Entity | Field | Model file |
|--------|-------|-----------|
| User | `is_active` | user.py:38 |
| Department | `is_active` | department.py:15 |
| MenuItem | `is_active` | menu_item.py:31 |
| InventoryItem | `is_active` | inventory_item.py |
| Equipment | `is_active` | equipment.py:30 |
| BookableResource | `is_active` | bookable_resource.py:27 |
| Budget | `is_active` | budget.py:20 |
| Role | `is_active` | role.py:21 |
| ConductRule | `is_active` | conduct_rule.py:30 |
| JudgeBaseline | `is_active` | judge_baseline.py:29 |
| Waiver | `is_active` | waiver.py:26 |
| PushSubscription | `is_active` | push_subscription.py:23 |
| Booking | `status` enum (CANCELLED) | booking.py |
| Shift | `status` enum (CANCELLED) | shift.py |

**List endpoints accepting include_disabled:** departments, roles, baselines, wifi, profiles, bookable resources, inventory items, users, menu items (9 endpoints). Pattern: `?include_disabled=true`.

**Missing include_disabled:** equipment list, booking list, budget list, conduct rules list.

## Daily Revenue / "Today"

Uses calendar midnight UTC everywhere. No configurable cutoff. `parse_date_bounds` is the single chokepoint — changing it propagates to all callers.
