# Kurahia E2E Test Report

**Date:** 2026-06-19 22:30:18
**Target:** http://localhost:5000
**Summary:** 43 PASS, 0 FAIL, 0 SKIP out of 43 tests

| # | Test | Endpoint | Expected | Actual Status | Actual Response | PASS/FAIL |
|---|------|----------|----------|---------------|-----------------|----------|
| 1.1 | Owner login (wachira) | `POST /auth/login` | 200 + token | 200 | {'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhd | PASS |
| 1.2 | Manager login (manager2) | `POST /auth/login` | 200 + token | 200 | {'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhd | PASS |
| 1.3 | Waiter login (waiter1) | `POST /auth/login` | 200 + token | 200 | {'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhd | PASS |
| 1.4 | Gate staff login (gate1) | `POST /auth/login` | 200 + token | 200 | {'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhd | PASS |
| 1.5 | PIN login (wachira / 1111) | `POST /auth/pin-login` | 200 + token | 200 | {'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhd | PASS |
| 1.6 | Wrong password | `POST /auth/login` | 401 | 401 | {'error': 'Invalid credentials.'} | PASS |
| 1.7 | Deactivated/nonexistent user | `POST /auth/login` | 401 | 401 | {'error': 'Invalid credentials.'} | PASS |
| 2.1 | Dashboard overview | `GET /dashboard/overview` | 200 + revenue/staff/bookings | 200 | {'bookings': {'active': 0, 'arrivals_today': 0, 'departures_today': 0}, 'invento | PASS |
| 2.2 | Judge alerts | `GET /judge/alerts` | 200 + array | 200 | [{'alert_type': 'COST_VARIANCE', 'created_at': '2026-06-17T08:59:54.290742', 'de | PASS |
| 2.3 | Finance budgets status | `GET /finance/budgets/status` | 200 + budgets | 200 | {'budgets': [], 'period': '2026-06'} | PASS |
| 2.4 | Dashboard bookings | `GET /dashboard/bookings` | 200 + bookings data | 200 | {'arrivals_today': [], 'departures_today': [], 'occupancy_by_type': {}, 'pending | PASS |
| 2.5 | Dashboard feedback | `GET /dashboard/feedback` | 200 + feedback data | 200 | {'by_department': [], 'by_staff': [], 'overall_avg': None, 'period': 'month', 'r | PASS |
| 2.6 | Admin settings | `GET /admin/settings` | 200 + business_day_start_hour | 200 | {'business_day_start_hour': '6'} | PASS |
| 3.1 | Inventory items | `GET /inventory/items` | 200 + array | 200 |  | PASS |
| 3.2 | Purchase requests | `GET /inventory/purchase-requests` | 200 + array | 200 | [{'created_at': '2026-06-17T08:59:11.338551', 'department': 'Housekeeping', 'est | PASS |
| 3.3 | Attendance today | `GET /hr/attendance/today` | 200 + array | 200 |  | PASS |
| 3.4 | Finance budgets (manager) | `GET /finance/budgets/status` | 200 + budgets | 200 | {'budgets': [], 'period': '2026-06'} | PASS |
| 3.5 | Staff list | `GET /auth/users` | 200 + user list | 200 | [{'department': 'general management', 'id': '3cfdf474-f268-42f3-87db-38046ca2cc1 | PASS |
| 3.6 | Menu items | `GET /menu/items` | 200 + array | 200 | [{'category': 'Mains', 'department_id': '1fb7866a-50e0-48dc-8d02-2eb5f73a6d3c',  | PASS |
| 4.1 | Issue wristband (CASH) | `POST /gate/issue-band` | 201 + band_number + tab_id | 201 | {'band_number': 2, 'id': '213af1d4-f8a6-4c84-9062-9451a315062d', 'issue_date': ' | PASS |
| 4.2 | Gate today stats | `GET /gate/today-stats` | 200 + issued_today > 0 | 200 | {'inside_now': 2, 'issued_today': 2, 'total_entry_fees': '6000'} | PASS |
| 4.3 | Lookup band by number | `GET /gate/bands/2` | 200 + ACTIVE | 200 | {'band_number': 2, 'id': '213af1d4-f8a6-4c84-9062-9451a315062d', 'issue_date': ' | PASS |
| 4.4 | Active bands list | `GET /gate/active-bands` | 200 + array with band | 200 | [{'band_number': 1, 'id': 'a35410e9-0deb-48bf-bd98-4d8cb4b85840', 'issue_date':  | PASS |
| 5.1 | Open tab | `POST /tabs` | 201 + tab id | 201 | {'id': '0fd8af66-0d9d-4919-813e-4ef79fb8ee9f', 'reference': 'E2E Test Tab', 'sta | PASS |
| 5.2 | Get menu items | `GET /menu/items` | 200 + items array | 200 | 11 items found | PASS |
| 5.3 | Create order (Beef Burger) | `POST /orders` | 201 + order id | 201 | {'id': '32009567-33f1-46b1-9b18-ff5ad8c023bb', 'status': 'DRAFT', 'tab_id': '0fd | PASS |
| 5.4 | Send order to kitchen | `POST /orders/32009567-33f1-46b1-9b18-ff5ad8c023bb/send` | 200 + SENT | 200 | {'id': '32009567-33f1-46b1-9b18-ff5ad8c023bb', 'status': 'SENT'} | PASS |
| 5.5 | Kitchen queue | `GET /kitchen/queue` | 200 + order in queue | 200 | 2 items in queue | PASS |
| 5.6 | Kitchen receives item | `POST /order-items/1fb34a0a-906d-44d5-8644-faeb15b28cbd/receive` | 200 | 200 | {'id': '1fb34a0a-906d-44d5-8644-faeb15b28cbd', 'status': 'RECEIVED'} | PASS |
| 5.7 | Kitchen marks ready | `POST /order-items/1fb34a0a-906d-44d5-8644-faeb15b28cbd/ready` | 200 | 200 | {'id': '1fb34a0a-906d-44d5-8644-faeb15b28cbd', 'status': 'READY'} | PASS |
| 5.8 | Waiter serves item | `POST /order-items/1fb34a0a-906d-44d5-8644-faeb15b28cbd/serve` | 200 | 200 | {'id': '1fb34a0a-906d-44d5-8644-faeb15b28cbd', 'status': 'SERVED'} | PASS |
| 5.9 | Pay tab (CASH) | `POST /tabs/0fd8af66-0d9d-4919-813e-4ef79fb8ee9f/payments` | 201 + payment | 201 | {'amount': '950.00', 'method': 'CASH', 'mpesa_code': None, 'payment_id': 'dbe7b6 | PASS |
| 5.10 | Close tab | `POST /tabs/0fd8af66-0d9d-4919-813e-4ef79fb8ee9f/close` | 200 + CLOSED | 200 | {'id': '0fd8af66-0d9d-4919-813e-4ef79fb8ee9f', 'status': 'CLOSED'} | PASS |
| 6.1 | Order sold-out item (Grilled Tilapia) | `POST /orders` | 409 | 409 | {'error': 'Grilled Tilapia is sold out — Smoke Test Oil stock is too low. Check  | PASS |
| 7.1 | Get receipt | `GET /receipts/0fd8af66-0d9d-4919-813e-4ef79fb8ee9f` | 200 + charges + payments | 200 | {'balance': '0.00', 'charges': [{'amount': '950.00', 'created_at': '2026-06-19T1 | PASS |
| 8.1 | Health check | `GET /health` | 200 + status ok + cron_last_run | 200 | {'cron_last_run': {'auto_close': None, 'auto_draft': '2026-06-17T08:59:11.342157 | PASS |
| 9.1 | Waiter -> /dashboard/overview | `GET /dashboard/overview` | 403 | 403 | {'error': 'Manager or above required.'} | PASS |
| 9.2 | Waiter -> /judge/alerts | `GET /judge/alerts` | 403 | 403 | {'error': 'Owner only.'} | PASS |
| 9.3 | Waiter -> /admin/settings | `GET /admin/settings` | 403 | 403 | {'error': 'Only the owner can view system settings.'} | PASS |
| 9.4 | Gate staff -> /inventory/items | `GET /inventory/items` | 200 (allowed) | 200 |  | PASS |
| 10.1 | Menu search (tilapia) | `GET /menu/items?q=tilapia` | 200 + filtered | 200 | [{'category': 'Mains', 'department_id': '1fb7866a-50e0-48dc-8d02-2eb5f73a6d3c',  | PASS |
| 10.2 | Inventory search (oil) | `GET /inventory/items?q=oil` | 200 + filtered | 200 |  | PASS |
| 10.3 | User search (manager) | `GET /auth/users?q=manager` | 200 + filtered | 200 | [{'department': 'general management', 'id': 'c65b8ea5-39df-471b-82e9-b1936c1ab64 | PASS |
