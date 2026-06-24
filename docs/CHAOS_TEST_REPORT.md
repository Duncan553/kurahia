# Kurahia Resort API -- Chaos Test Report

**Date:** 2026-06-23 22:43:43 UTC

**Target:** `http://localhost:5000`

**Roles tested:** owner (wachira), manager (manager2), waiter (waiter1)


## Summary

| Verdict | Count |
|---------|-------|
| HANDLED | 26 |
| CRASHED | 2 |
| VULNERABLE | 7 |
| **Total** | **35** |


## BAD INPUT

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Negative quantity in order | `POST /orders` | 409 | **VULNERABLE** | {"error": "Grilled Tilapia is sold out \u2014 Smoke Test Oil stock is too low. Check with the kitchen before ordering."} |
| 2 | Extreme quantity (99999) in order | `POST /orders` | 409 | HANDLED | {"error": "Grilled Tilapia is sold out \u2014 Smoke Test Oil stock is too low. Check with the kitchen before ordering."} |
| 3 | Empty reference (walk-in tab) | `POST /tabs` | 201 | HANDLED | {"id": "349776c5-4843-4cbe-9ca8-7daea99b25ee", "reference": null, "status": "OPEN"} |
| 4 | 10,000 char reference | `POST /tabs` | 201 | **VULNERABLE** | {"id":"30df5657-1439-4bc5-ab30-6778b2a558dc","reference":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA |
| 5 | Negative reorder_level | `POST /inventory/items` | 500 | **CRASHED** | {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."} |
| 6 | Invalid payment method (BITCOIN) | `POST /gate/issue-band` | 400 | HANDLED | {"error": "method must be one of ['CASH', 'CARD', 'MPESA', 'BANK_TRANSFER']."} |
| 7 | NaN payment amount | `POST /tabs/<id>/payments` | 500 | **VULNERABLE** | {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."} |
| 8 | Negative payment amount (-500) | `POST /tabs/<id>/payments` | 400 | HANDLED | {"error": "Payment amount must be greater than zero."} |
| 9 | 50,000 char suggestion body | `POST /suggestions` | 201 | **VULNERABLE** | {"body":"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX |
| 10 | Negative menu item price (-10) | `PATCH /menu/items/<id>` | 500 | **CRASHED** | {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."} |
| 11 | Zero quantity in order | `POST /orders` | 409 | **VULNERABLE** | {"error": "Grilled Tilapia is sold out \u2014 Smoke Test Oil stock is too low. Check with the kitchen before ordering."} |
| 12 | SQL injection in reference | `POST /tabs` | 201 | HANDLED | {"id": "e6227f0c-6974-4ce1-aca3-b83535b00f7c", "reference": "'; DROP TABLE tabs; --", "status": "OPEN"} |
| 13 | XSS in suggestion subject | `POST /suggestions` | 201 | HANDLED | {"body":"Test XSS injection","category":"MANAGEMENT","created_at":"2026-06-23T22:43:40.205723","id":"8b3fbf9e-0aaf-474e- |
| 14 | Infinity payment amount | `POST /tabs/<id>/payments` | 201 | **VULNERABLE** | {"amount": "Infinity", "method": "CASH", "mpesa_code": null, "payment_id": "99c2e6b8-d15d-4a40-a28c-8f29dc4f6cfa", "tab_ |
| 15 | Unicode in item name | `POST /inventory/items` | 201 | HANDLED | {"id":"fffa8e10-4d51-4ce9-9bac-a1f6b12bc77f","name":"chaos_emoji_745f","unit":"each"}  |

## CONCURRENCY

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Double-submit tab open (no idem support) | `POST /tabs` | 201/201 | **VULNERABLE** | ids: 6ffcfe10/342ec1f3 |
| 2 | Double-submit same idem key on /gate/issue-band | `POST /gate/issue-band` | 201/200 | HANDLED | ids match: True |
| 3 | Open 20 tabs rapidly (parallel) | `POST /tabs x20` | unique=20/errors=0 | HANDLED | 20 unique IDs |

## STATE MACHINE

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Close already-closed tab | `POST /tabs/<id>/close` | 400 | HANDLED | {"error": "This tab is already closed."} |

## MISSING REF

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Order with nonexistent tab_id | `POST /orders` | 404 | HANDLED | {"error": "Tab not found."} |
| 2 | Payment with nonexistent tab_id | `POST /tabs/<fake>/payments` | 404 | HANDLED | {"error": "Tab not found."} |
| 3 | Edit nonexistent menu item | `PATCH /menu/items/<fake>` | 404 | HANDLED | {"error": "Menu item not found."} |
| 4 | Get nonexistent band | `GET /gate/bands/99999` | 404 | HANDLED | {"error":"Band #99999 not found for today."}  |
| 5 | Order with nonexistent menu_item_id | `POST /orders` | 404 | HANDLED | {"error": "Menu item '00000000-0000-0000-0000-000000000000' not found."} |
| 6 | Close nonexistent tab | `POST /tabs/<fake>/close` | 404 | HANDLED | {"error": "Tab not found."} |

## AUTH

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Garbage JWT token | `GET /tabs` | 401 | HANDLED | {"error":"Invalid token."}  |
| 2 | Missing Authorization header | `GET /tabs` | 401 | HANDLED | {"error":"Authorization token required."}  |
| 3 | Empty bearer token | `GET /tabs` | 401 | HANDLED | {"error":"Invalid token."}  |
| 4 | Bearer 'null' | `GET /tabs` | 401 | HANDLED | {"error":"Invalid token."}  |
| 5 | Waiter tries to create menu item | `POST /menu/items` | 403 | HANDLED | {"error": "Only a manager or above can manage menu items."} |
| 6 | Waiter tries to issue wristband | `POST /gate/issue-band` | 403 | HANDLED | {"error": "Gate staff or above required to issue wristbands."} |

## EXHAUSTION

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Create 100 tabs rapidly (1.5s) | `POST /tabs x100` | success=100/fail=0 | HANDLED | 1.5s elapsed |
| 2 | Create 50 inventory items sequentially | `POST /inventory/items x50` | success=50/fail=0 | HANDLED | 50 created |

## INTEGRITY

| # | Test | Endpoint | Status | Verdict | Detail |
|---|------|----------|--------|---------|--------|
| 1 | Add order to closed tab | `POST /orders` | 400 | HANDLED | {"error": "This tab is already closed. Open a new tab."} |
| 2 | Add payment to closed tab | `POST /tabs/<id>/payments` | 400 | HANDLED | {"error": "This tab is already closed. No further payments can be recorded."} |

## Key Findings

### Vulnerabilities Found

- **Negative quantity in order** (`POST /orders`): Status 409 -- {"error": "Grilled Tilapia is sold out \u2014 Smoke Test Oil stock is too low. Check with the kitchen before ordering."}
- **10,000 char reference** (`POST /tabs`): Status 201 -- {"id":"30df5657-1439-4bc5-ab30-6778b2a558dc","reference":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
- **NaN payment amount** (`POST /tabs/<id>/payments`): Status 500 -- {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."}
- **50,000 char suggestion body** (`POST /suggestions`): Status 201 -- {"body":"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- **Zero quantity in order** (`POST /orders`): Status 409 -- {"error": "Grilled Tilapia is sold out \u2014 Smoke Test Oil stock is too low. Check with the kitchen before ordering."}
- **Infinity payment amount** (`POST /tabs/<id>/payments`): Status 201 -- {"amount": "Infinity", "method": "CASH", "mpesa_code": null, "payment_id": "99c2e6b8-d15d-4a40-a28c-8f29dc4f6cfa", "tab_balance": "-Infinity"}
- **Double-submit tab open (no idem support)** (`POST /tabs`): Status 201/201 -- ids: 6ffcfe10/342ec1f3

### Crashes Found

- **Negative reorder_level** (`POST /inventory/items`): Status 500 -- {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."}
- **Negative menu item price (-10)** (`PATCH /menu/items/<id>`): Status 500 -- {"error": "internal_server_error", "message": "An unexpected error occurred. Please try again or contact your manager."}


---

*Generated by chaos_test.py*
