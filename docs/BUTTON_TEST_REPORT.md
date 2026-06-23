# Button & Endpoint Test Report

**Date:** 2026-06-23
**Backend:** localhost:5000
**Method:** Manual curl testing of every button/link endpoint per role

## Summary

- **Total tests:** 46
- **WORKS:** 44
- **BROKEN:** 1 (wrong endpoint path in frontend)
- **WORKS (needs correct params):** 1

---

## Results

| # | Role | Action | Endpoint | Status | Verdict |
|---|------|--------|----------|--------|---------|
| 1 | Owner | Dashboard overview | GET /dashboard/overview | 200 | WORKS |
| 2 | Owner | Dashboard bookings | GET /dashboard/bookings | 200 | WORKS |
| 3 | Owner | Dashboard feedback | GET /dashboard/feedback | 200 | WORKS |
| 4 | Owner | Dashboard equipment | GET /dashboard/equipment | 200 | WORKS |
| 5 | Owner | Judge alerts | GET /judge/alerts | 200 | WORKS |
| 6 | Owner | Finance budgets status | GET /finance/budgets/status | 200 | WORKS |
| 7 | Owner | Admin settings | GET /admin/settings | 200 | WORKS |
| 8 | Owner | Admin departments | GET /admin/departments | 200 | WORKS |
| 9 | Owner | Admin roles | GET /admin/roles | 200 | WORKS |
| 10 | Owner | Staff list | GET /auth/users | 200 | WORKS |
| 11 | Owner | Suggestions (all) | GET /suggestions | 200 | WORKS |
| 12 | Owner | Finance reconciliation | GET /finance/reconciliation/status | 404 | BROKEN |
| 12a | Owner | Finance reconciliation (correct) | GET /finance/reconciliation?date=YYYY-MM-DD | 200 | WORKS |
| 13 | Manager | Inventory items list | GET /inventory/items | 200 | WORKS |
| 14 | Manager | Create inventory item | POST /inventory/items | 201 | WORKS |
| 15 | Manager | Edit inventory item | PATCH /inventory/items/{id} | 200 | WORKS |
| 16 | Manager | Disable inventory item | POST /inventory/items/{id}/disable | 200 | WORKS |
| 17 | Manager | Enable inventory item | POST /inventory/items/{id}/enable | 200 | WORKS |
| 18 | Manager | Menu items list | GET /menu/items | 200 | WORKS |
| 19 | Manager | Create menu item | POST /menu/items | 201 | WORKS |
| 20 | Manager | Edit menu item | PATCH /menu/items/{id} | 200 | WORKS |
| 21 | Manager | Purchase requests list | GET /inventory/purchase-requests | 200 | WORKS |
| 22 | Manager | Attendance today | GET /hr/attendance/today | 200 | WORKS |
| 23 | Manager | Shifts list | GET /hr/shifts | 200 | WORKS |
| 24 | Manager | Create shift | POST /hr/shifts | 201 | WORKS |
| 25 | Manager | Staff list | GET /auth/users | 200 | WORKS |
| 26 | Manager | Create staff account | POST /auth/users | 201 | WORKS |
| 27 | Manager | Finance budgets status | GET /finance/budgets/status | 200 | WORKS |
| 28 | Waiter | Open table tab | POST /tabs | 201 | WORKS |
| 29 | Waiter | My open tabs | GET /tabs?mine=true&status=OPEN | 200 | WORKS |
| 30 | Waiter | Menu items | GET /menu/items | 200 | WORKS |
| 31 | Waiter | Create order | POST /orders | 201 | WORKS |
| 32 | Waiter | Send order to kitchen | POST /orders/{id}/send | 200 | WORKS |
| 33 | Waiter | Add payment to tab | POST /tabs/{id}/payments | 201 | WORKS |
| 34 | Waiter | Close tab | POST /tabs/{id}/close | 200 | WORKS |
| 35 | Waiter | Get receipt | GET /receipts/{tab_id} | 200 | WORKS |
| 36 | Waiter | Clock status | GET /hr/clock-status | 200 | WORKS |
| 37 | Waiter | Submit suggestion | POST /suggestions | 201 | WORKS |
| 38 | Gate | Issue band | POST /gate/issue-band | 201 | WORKS |
| 39 | Gate | Today stats | GET /gate/today-stats | 200 | WORKS |
| 40 | Gate | Lookup band | GET /gate/bands/{number} | 200 | WORKS |
| 41 | Gate | Active bands | GET /gate/active-bands | 200 | WORKS |
| 42 | Kitchen | Kitchen queue | GET /kitchen/queue | 200 | WORKS |
| 43 | Kitchen | Receive order item | POST /order-items/{id}/receive | 200 | WORKS |
| 44 | Kitchen | Ready order item | POST /order-items/{id}/ready | 200 | WORKS |
| 45 | Owner | Upload menu image | POST /uploads/menu | 201 | WORKS |
| 46 | Owner | Upload profile image | POST /uploads/profile | 201 | WORKS |

---

## Issues Found

### 1. BROKEN: Finance Reconciliation endpoint path mismatch (Row 12)

- **Expected by frontend:** `GET /finance/reconciliation/status`
- **Actual backend route:** `GET /finance/reconciliation?date=YYYY-MM-DD`
- **Result:** 404 Not Found
- **Fix needed:** Either update the frontend to call `/finance/reconciliation?date=...` or add a `/finance/reconciliation/status` alias route.

### 2. Notes on required fields (not bugs, but important for frontend devs)

| Endpoint | Required Fields |
|----------|----------------|
| POST /inventory/items | `name`, `unit`, `department_id` |
| POST /menu/items | `name`, `price`, `department_id`, `category` |
| POST /hr/shifts | `employee_id`, `scheduled_start_utc`, `scheduled_end_utc` |
| POST /auth/users | `username`, `role_id` (UUID from /admin/roles), optional `department_id` |
| POST /suggestions | `subject`, `body`, `category` (MANAGEMENT or OWNER_PRIVATE) |
| POST /gate/issue-band | `method` (CASH, CARD, MPESA, or BANK_TRANSFER) |
| POST /tabs/{id}/close | All order items must be SERVED first (PENDING/READY/RECEIVED blocks close) |
| GET /receipts/{id} | Takes `tab_id`, not `payment_id` |

### 3. Tab close requires full order lifecycle

The flow is: `DRAFT -> SENT -> RECEIVED -> READY -> SERVED -> (close tab)`

A waiter cannot close a tab until all order items reach SERVED status. This is correct behavior but worth noting for UI/UX.
