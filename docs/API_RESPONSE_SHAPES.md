# API Response Shapes — Kurahia Backend

> **Generated from source.** Every shape in this document was extracted directly from the
> `jsonify(...)` calls and helper dicts in the route files. No guessing.
>
> **Phase D-0.1** · Generated 2026-06-09

---

## How to read this document

- **Key types** are written in plain English: `str`, `int`, `bool`, `null`, `[...]` = array, `{...}` = nested object.
- **Money is always `str`** — all `Decimal` amounts are serialised with `str(...)`. Never floats.
- **Timestamps are ISO 8601 strings** — UTC, server-stamped.
- **Idempotency duplicate response** — most write endpoints return `{"id": str, "duplicate": true}` 200 on a repeated idempotency key. Documented per-endpoint where applicable.
- **Dormant socket pattern** — three payment sockets (M-Pesa Daraja, Bank Transfer API, Card Gateway) return `{"error": str, "fallback": str}` 503 when their env vars are not set. Their `GET /status` endpoints always return `{"configured": bool, "message": str}` 200 regardless.
- **Error responses** always carry `{"error": str}` with a plain-English message. Not documented per-endpoint (every endpoint uses this pattern).
- **Disable / Enable pattern** — disable returns `{"id": str, "is_active": false}`, enable returns `{"id": str, "is_active": true}`. Noted where it applies.

---

## Table of Contents

1. [Auth](#1-auth)
2. [Admin](#2-admin)
3. [POS — Menu](#3-pos--menu)
4. [POS — Tabs](#4-pos--tabs)
5. [POS — Orders & Order Items](#5-pos--orders--order-items)
6. [POS — Queues](#6-pos--queues)
7. [POS — Receipts](#7-pos--receipts)
8. [Inventory — Items](#8-inventory--items)
9. [Inventory — Stock Counts](#9-inventory--stock-counts)
10. [Inventory — Movements](#10-inventory--movements)
11. [Inventory — Purchases](#11-inventory--purchases)
12. [Inventory — Variance Report](#12-inventory--variance-report)
13. [Bookings — Resources](#13-bookings--resources)
14. [Bookings — Core](#14-bookings--core)
15. [Bookings — Deposits](#15-bookings--deposits)
16. [Bookings — Guests](#16-bookings--guests)
17. [Bookings — Waivers](#17-bookings--waivers)
18. [Bookings — Front Desk Dashboard](#18-bookings--front-desk-dashboard)
19. [Gate](#19-gate)
20. [HR — Profiles](#20-hr--profiles)
21. [HR — Shifts](#21-hr--shifts)
22. [HR — Clock Events](#22-hr--clock-events)
23. [HR — Leave Requests](#23-hr--leave-requests)
24. [HR — Attendance](#24-hr--attendance)
25. [HR — Performance & Payroll](#25-hr--performance--payroll)
26. [HR — Absence Notices](#26-hr--absence-notices)
27. [HR — WiFi Allow-list](#27-hr--wifi-allow-list)
28. [Finance — Cash Reconciliation](#28-finance--cash-reconciliation)
29. [Finance — M-Pesa (Manual)](#29-finance--m-pesa-manual)
30. [Finance — M-Pesa Daraja (Socket)](#30-finance--m-pesa-daraja-socket)
31. [Finance — Bank (Manual)](#31-finance--bank-manual)
32. [Finance — Bank Transfer (Socket)](#32-finance--bank-transfer-socket)
33. [Finance — Card Gateway (Socket)](#33-finance--card-gateway-socket)
34. [Finance — Budgets](#34-finance--budgets)
35. [Finance — Anomalies](#35-finance--anomalies)
36. [Finance — Reports & Dashboard](#36-finance--reports--dashboard)
37. [Events](#37-events)
38. [Conduct](#38-conduct)
39. [Disputes](#39-disputes)
40. [Suggestions](#40-suggestions)
41. [Feedback](#41-feedback)
42. [Equipment](#42-equipment)
43. [Judge Alerts](#43-judge-alerts)
44. [Notifications](#44-notifications)
45. [Calendar View](#45-calendar-view)
46. [Owner Dashboard](#46-owner-dashboard)

---

## 1. Auth

### `POST /auth/login`

Normal login:

```json
{
  "access_token":  "str",
  "refresh_token": "str"
}
```

**Status 200.**

PIN setup still required (first login, PIN never set):

```json
{
  "access_token":      "str",
  "requires_pin_setup": true
}
```

**Status 200.** The `access_token` here is a short-lived setup token. A full session token is not issued until `POST /auth/set-pin` completes.

---

### `POST /auth/pin-login`

```json
{
  "access_token":  "str",
  "refresh_token": "str"
}
```

**Status 200.**

---

### `POST /auth/refresh`

```json
{
  "access_token": "str"
}
```

**Status 200.**

---

### `POST /auth/set-pin`

Issues real session tokens after PIN is set for the first time.

```json
{
  "access_token":  "str",
  "refresh_token": "str"
}
```

**Status 200.**

---

### `POST /auth/change-pin`

```json
{
  "message": "PIN updated."
}
```

**Status 200.**

---

### `POST /auth/deactivate/<user_id>`

```json
{
  "message": "<username> deactivated."
}
```

**Status 200.**

---

### `POST /auth/reset-lockout/<user_id>`

```json
{
  "message": "Lockout cleared for <username>."
}
```

**Status 200.**

---

### `POST /auth/users` — Create user

```json
{
  "id":       "str",
  "username": "str",
  "role":     "str",
  "pin_set":  false
}
```

**Status 201.** `pin_set` is always `false` on creation — user must set their PIN on first login.

---

### `PATCH /auth/users/<user_id>` — Edit username / role

```json
{
  "id":       "str",
  "username": "str"
}
```

**Status 200.**

---

### `GET /auth/users` — List users

```json
[
  {
    "id":          "str",
    "username":    "str",
    "role":        "str",
    "department":  "str | null",
    "is_active":   true,
    "pin_set":     true
  }
]
```

**Status 200.**

---

### `POST /auth/users/<user_id>/activate` — Re-activate user

```json
{
  "message": "<username> has been re-activated."
}
```

**Status 200.**

---

## 2. Admin

### `GET /admin/departments`

```json
[
  {
    "id":        "str",
    "name":      "str",
    "is_active": true
  }
]
```

**Status 200.** Query param `?include_disabled=true` to include inactive departments. Requires manager-level or above.

---

### `POST /admin/departments`

```json
{
  "id":   "str",
  "name": "str"
}
```

**Status 201.** Owner only.

---

### `PATCH /admin/departments/<dept_id>`

```json
{
  "id":   "str",
  "name": "str"
}
```

**Status 200.** Owner only.

---

### `POST /admin/departments/<dept_id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.** Owner only.

---

### `POST /admin/departments/<dept_id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.** Owner only.

---

### `GET /admin/roles`

```json
[
  {
    "id":        "str",
    "name":      "str",
    "level":     1,
    "is_active": true
  }
]
```

**Status 200.** Query param `?include_disabled=true`. Requires manager-level or above.

---

### `POST /admin/roles`

```json
{
  "id":    "str",
  "name":  "str",
  "level": 5
}
```

**Status 201.** Owner only.

---

### `PATCH /admin/roles/<role_id>`

```json
{
  "id":    "str",
  "name":  "str",
  "level": 5
}
```

**Status 200.** Owner only.

---

### `POST /admin/roles/<role_id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.** Owner only. Disabling a role does NOT affect users already assigned it.

---

### `POST /admin/roles/<role_id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.** Owner only.

---

### `GET /admin/baselines`

```json
[
  {
    "id":                "str",
    "item_id":           "str",
    "item_name":         "str | null",
    "business_driver":   "str",
    "expected_ratio":    "str",
    "driver_unit":       "str",
    "tolerance_percent": "str",
    "is_active":         true
  }
]
```

**Status 200.** Owner only. `expected_ratio` and `tolerance_percent` are `str` (serialised `Decimal`).

---

### `POST /admin/baselines`

```json
{
  "id": "str"
}
```

**Status 201.** Owner only. Only `id` returned on creation.

---

### `PATCH /admin/baselines/<baseline_id>`

```json
{
  "id":             "str",
  "expected_ratio": "str"
}
```

**Status 200.** Owner only. `expected_ratio` is `str`.

---

### `POST /admin/baselines/<baseline_id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.** Owner only.

---

### `POST /admin/baselines/<baseline_id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.** Owner only.

---

## 3. POS — Menu

### `POST /menu/items`

```json
{
  "id":    "str",
  "name":  "str",
  "price": "str"
}
```

**Status 201.** `price` is `str` (serialised `Decimal`). Manager or above.

---

### `PATCH /menu/items/<item_id>`

```json
{
  "id":    "str",
  "name":  "str",
  "price": "str"
}
```

**Status 200.**

---

### `POST /menu/items/<item_id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /menu/items/<item_id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

### `GET /menu/items`

```json
[
  {
    "id":            "str",
    "name":          "str",
    "price":         "str",
    "category":      "str | null",
    "prep_station":  "KITCHEN | BAR | NONE",
    "department_id": "str",
    "is_active":     true
  }
]
```

**Status 200.** Query params: `?include_disabled=true`, `?department=<dept_id>`. `price` is `str`.

---

## 4. POS — Tabs

### `POST /tabs`

```json
{
  "id":        "str",
  "reference": "str | null",
  "status":    "str"
}
```

**Status 201.**

---

### `GET /tabs/<tab_id>`

```json
{
  "id":          "str",
  "reference":   "str | null",
  "tab_type":    "str",
  "status":      "str",
  "opened_at":   "str",
  "opened_by":   "str",
  "balance":     "str",
  "charges": [
    {
      "id":          "str",
      "description": "str",
      "amount":      "str",
      "created_at":  "str"
    }
  ],
  "payments": [
    {
      "id":          "str",
      "method":      "str",
      "amount":      "str",
      "received_by": "str",
      "created_at":  "str"
    }
  ],
  "orders": [
    {
      "id":     "str",
      "status": "str",
      "items": [
        {
          "id":       "str",
          "name":     "str",
          "quantity": "str",
          "status":   "str"
        }
      ]
    }
  ]
}
```

**Status 200.** `balance`, `amount`, `quantity` are `str` (Decimal). `opened_at` and `created_at` are ISO 8601.

---

### `POST /tabs/<tab_id>/close`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

## 5. POS — Orders & Order Items

### `POST /orders`

```json
{
  "id":     "str",
  "tab_id": "str",
  "status": "str"
}
```

**Status 201.**

Duplicate (repeated idempotency key):

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /orders/<order_id>/send` — Send to kitchen/bar

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /order-items/<oi_id>/receive` — Kitchen/bar acknowledges item

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /order-items/<oi_id>/ready` — Item ready for pickup

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /order-items/<oi_id>/serve` — Item delivered to guest

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /order-items/<oi_id>/cancel`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /order-items/<oi_id>/send-back` — Guest returns item

```json
{
  "id":     "str",
  "status": "str",
  "reason": "sent-back"
}
```

**Status 200.** `reason` is always the literal string `"sent-back"`.

---

### `POST /tabs/<tab_id>/payments` — Record payment

```json
{
  "payment_id":  "str",
  "amount":      "str",
  "method":      "str",
  "tab_balance": "str",
  "mpesa_code":  "str | null"
}
```

**Status 201.** `amount` and `tab_balance` are `str`. `mpesa_code` is `null` for non-M-Pesa payments.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true,
  "amount":    "str"
}
```

**Status 200.**

---

### `GET /reports/staff-cash` — Staff cash totals

```json
{
  "staff_id":   "str",
  "staff_name": "str",
  "cash_total": "str",
  "period_from": "str",
  "period_to":   "str"
}
```

**Status 200.** `cash_total` is `str`. Dates are ISO 8601.

---

## 6. POS — Queues

### `GET /kitchen/queue`

```json
[
  {
    "order_item_id": "str",
    "order_id":      "str",
    "tab_reference": "str | null",
    "menu_item":     "str | null",
    "quantity":      "str",
    "status":        "PENDING | RECEIVED",
    "created_at":    "str",
    "age_seconds":   123
  }
]
```

**Status 200.** Items are oldest-first. `quantity` is `str` (Decimal). `age_seconds` is `int`. Requires Kitchen department membership or manager+.

---

### `GET /bar/queue`

Same shape as `/kitchen/queue`. **Status 200.** Requires Bar department membership or manager+.

---

## 7. POS — Receipts

### `GET /receipts/<tab_id>`

```json
{
  "tab_id":      "str",
  "reference":   "str | null",
  "tab_type":    "str",
  "opened_at":   "str",
  "closed_at":   "str | null",
  "opened_by":   "str",
  "charges": [
    {
      "description": "str",
      "amount":      "str",
      "created_at":  "str"
    }
  ],
  "payments": [
    {
      "method":      "str",
      "amount":      "str",
      "received_by": "str",
      "mpesa_code":  "str | null",
      "card_ref":    "str | null",
      "created_at":  "str"
    }
  ],
  "total_charges":  "str",
  "total_payments": "str",
  "balance":        "str",
  "status":         "str"
}
```

**Status 200.** All money fields are `str`. `closed_at` is `null` if tab is still open.

---

## 8. Inventory — Items

### `POST /inventory/items`

```json
{
  "id":   "str",
  "name": "str",
  "unit": "str"
}
```

**Status 201.** Manager or above.

---

### `PATCH /inventory/items/<item_id>`

```json
{
  "id":        "str",
  "name":      "str",
  "is_active": true
}
```

**Status 200.**

---

### `GET /inventory/items`

```json
[
  {
    "id":            "str",
    "name":          "str",
    "unit":          "str",
    "department_id": "str",
    "is_active":     true,
    "current_stock": "str",
    "reorder_level": "str",
    "below_reorder": false,
    "is_watch_list": false,
    "is_staff_food": false
  }
]
```

**Status 200.** `current_stock` and `reorder_level` are `str` (Decimal). Managers see their own department only; owners see everything.

---

### `POST /inventory/items/<item_id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /inventory/items/<item_id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

## 9. Inventory — Stock Counts

### `POST /inventory/counts`

```json
{
  "id":          "str",
  "item":        "str",
  "counted":     "str",
  "prior_stock": "str",
  "adjustment":  "str"
}
```

**Status 201.** All quantities are `str` (Decimal). `adjustment` is `"0"` if no reconciliation movement was needed. Manager or above.

Duplicate (repeated idempotency key):

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

## 10. Inventory — Movements

### `POST /inventory/movements/spoilage`

```json
{
  "movement_id": "str",
  "item":        "str",
  "quantity":    "str"
}
```

**Status 201.** `quantity` is `str`. Manager or above.

---

### `POST /inventory/movements/staff-meal`

```json
{
  "movement_id": "str",
  "item":        "str",
  "quantity":    "str"
}
```

**Status 201.** Only valid for items where `is_staff_food = true`. Any active user.

---

### `POST /inventory/movements/sent-back`

```json
{
  "movement_id": "str",
  "item":        "str",
  "quantity":    "str"
}
```

**Status 201.** `quantity` is `str`. Manager or above.

---

## 11. Inventory — Purchases

### `POST /inventory/purchase-requests`

```json
{
  "id":     "str",
  "status": "PENDING"
}
```

**Status 201.** Manager or above. `status` is always `"PENDING"` on creation.

---

### `POST /inventory/purchase-requests/<pr_id>/propose` — Attach budget

```json
{
  "id":             "str",
  "status":         "str",
  "estimated_cost": "str"
}
```

**Status 200.** `estimated_cost` is `str` (Decimal). Manager or above.

---

### `POST /inventory/purchase-requests/<pr_id>/approve` — Owner approves or rejects

```json
{
  "id":     "str",
  "status": "APPROVED | REJECTED"
}
```

**Status 200.** Owner only. Send `{"action": "approve"}` or `{"action": "reject"}`.

---

### `POST /inventory/purchases` — Record completed purchase

```json
{
  "purchase_id": "str",
  "movement_id": "str",
  "item":        "str",
  "quantity":    "str",
  "actual_cost": "str"
}
```

**Status 201.** `quantity` and `actual_cost` are `str`. `receipt_photo_path` is mandatory in request body. Manager or above.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

## 12. Inventory — Variance Report

### `GET /inventory/variance?dept=<id>&from=<ISO>&to=<ISO>`

```json
{
  "period_start": "str",
  "period_end":   "str",
  "items": [
    {
      "item_id":          "str",
      "item_name":        "str",
      "unit":             "str",
      "opening":          "str",
      "purchases":        "str",
      "consumption":      "str",
      "expected_closing": "str",
      "actual_closing":   "str",
      "variance":         "str",
      "variance_pct":     "str",
      "flagged":          false,
      "tolerance_pct":    "str"
    }
  ],
  "flagged_count": 0,
  "flagged_items": ["str"]
}
```

**Status 200.** All quantities are `str` (Decimal). Staff-food items are excluded. Items without a closing count in the period appear as `{"item_id": str, "item_name": str, "no_closing_count": true}` instead. Manager or above.

---

## 13. Bookings — Resources

### Helper: `_resource_dict`

Used in all bookable-resource responses:

```json
{
  "id":            "str",
  "name":          "str",
  "resource_type": "str",
  "capacity":      1,
  "base_price":    "str",
  "department_id": "str",
  "is_active":     true
}
```

`base_price` is `str` (Decimal). `capacity` is `int`.

---

### `POST /bookable-resources`

Returns `_resource_dict`. **Status 201.**

---

### `GET /bookable-resources`

Returns `[_resource_dict]`. **Status 200.**

---

### `PATCH /bookable-resources/<id>`

Returns `_resource_dict`. **Status 200.**

---

### `POST /bookable-resources/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /bookable-resources/<id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

## 14. Bookings — Core

### Helper: `_booking_dict`

Base shape (without `tab_balance`):

```json
{
  "id":                 "str",
  "resource_id":        "str",
  "resource_name":      "str",
  "guest_name":         "str",
  "guest_phone":        "str | null",
  "guest_id_number":    "str | null",
  "number_of_guests":   1,
  "check_in_planned":   "str",
  "check_out_planned":  "str",
  "check_in_actual":    "str | null",
  "check_out_actual":   "str | null",
  "base_total":         "str",
  "deposit_required":   "str",
  "deposit_paid":       "str",
  "status":             "str",
  "tab_id":             "str | null",
  "notes":              "str | null",
  "guest_record_id":    "str | null"
}
```

When `include_balance=True`, an extra key is added:

```json
{
  "tab_balance": "str"
}
```

All money fields (`base_total`, `deposit_required`, `deposit_paid`, `tab_balance`) are `str`. Timestamps are ISO 8601.

---

### `POST /bookings`

Returns `_booking_dict`. **Status 201.**

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /bookings/<id>/confirm`

Returns `_booking_dict`. **Status 200.**

---

### `POST /bookings/<id>/check-in`

Returns `_booking_dict` **with** `tab_balance` + explicit `tab_id`. **Status 200.** A new tab is created on check-in.

---

### `POST /bookings/<id>/check-out`

Returns `_booking_dict` (no `tab_balance`). **Status 200.**

---

### `POST /bookings/<id>/cancel`

Returns `_booking_dict`. **Status 200.**

---

### `GET /bookings`

Returns `[_booking_dict]`. **Status 200.**

---

### `GET /bookings/availability`

```json
[
  {
    "id":            "str",
    "name":          "str",
    "resource_type": "str",
    "base_price":    "str",
    "capacity":      1,
    "available":     true
  }
]
```

**Status 200.** `base_price` is `str`.

---

### `GET /bookings/today`

```json
{
  "arrivals": [
    { "_booking_dict": "..." }
  ],
  "departures": [
    { "_booking_dict_with_tab_balance": "..." }
  ],
  "occupancy": [
    { "_booking_dict_with_tab_balance": "..." }
  ]
}
```

`arrivals` uses plain `_booking_dict`. `departures` and `occupancy` include `tab_balance`. **Status 200.**

---

### `POST /bookings/<id>/water-sessions`

Returns a charge response (200) — records a charge on the booking's tab using the resource's `base_price`. Shape matches a tab charge dict.

---

## 15. Bookings — Deposits

### `POST /booking-payments`

```json
{
  "id":         "str",
  "booking_id": "str",
  "payment_id": "str",
  "purpose":    "str",
  "amount":     "str",
  "method":     "str"
}
```

**Status 201.** `amount` is `str`.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /booking-payments`

```json
[
  {
    "id":         "str",
    "purpose":    "str",
    "amount":     "str",
    "method":     "str",
    "created_at": "str"
  }
]
```

**Status 200.** `amount` is `str`.

---

## 16. Bookings — Guests

### Helper: `_guest_dict`

```json
{
  "id":         "str",
  "name":       "str",
  "phone":      "str | null",
  "id_number":  "str | null",
  "notes":      "str | null",
  "last_visit": "str | null",
  "is_active":  true
}
```

`last_visit` is ISO 8601 date string or `null`.

---

### `GET /guest-records`

Returns `[_guest_dict]`. **Status 200.**

---

### `GET /guest-records/<id>`

Returns `_guest_dict`. **Status 200.**

---

### `GET /guest-records/<id>/history`

```json
{
  "guest": { "_guest_dict": "..." },
  "bookings": [
    {
      "id":            "str",
      "resource_name": "str",
      "check_in":      "str",
      "check_out":     "str",
      "status":        "str",
      "base_total":    "str"
    }
  ]
}
```

**Status 200.** `base_total` is `str`. Timestamps are ISO 8601.

---

## 17. Bookings — Waivers

### `POST /waivers`

```json
{
  "id":            "str",
  "booking_id":    "str",
  "activity_type": "str",
  "signed_by":     "str",
  "signed_at":     "str"
}
```

**Status 201.**

---

### `GET /waivers`

```json
[
  {
    "id":            "str",
    "booking_id":    "str",
    "activity_type": "str",
    "signed_by":     "str",
    "signed_at":     "str",
    "is_active":     true
  }
]
```

**Status 200.**

---

### `POST /waivers/<id>/revoke`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

## 18. Bookings — Front Desk Dashboard

### `GET /front-desk/today`

```json
{
  "date": "2026-06-09",
  "arrivals": [
    {
      "booking_id":       "str",
      "guest_name":       "str",
      "resource":         "str | null",
      "status":           "str",
      "deposit_paid":     "str",
      "deposit_required": "str"
    }
  ],
  "departures": [
    {
      "booking_id":  "str",
      "guest_name":  "str",
      "resource":    "str | null",
      "tab_balance": "str"
    }
  ],
  "occupancy": [
    {
      "booking_id":  "str",
      "guest_name":  "str",
      "resource":    "str | null",
      "tab_id":      "str | null",
      "tab_balance": "str"
    }
  ],
  "pending_waivers": [
    {
      "booking_id": "str",
      "guest_name": "str",
      "resource":   "str",
      "check_in":   "str"
    }
  ]
}
```

**Status 200.** Requires staff-level (role.level ≥ 3) or above. Money fields are `str`. `pending_waivers` lists water-activity bookings today that have no active waiver.

---

## 19. Gate

### Helper: `_band_dict`

Base shape:

```json
{
  "id":           "str",
  "band_number":  1,
  "issue_date":   "str",
  "status":       "str",
  "tab_id":       "str | null",
  "notes":        "str | null",
  "issued_by":    "str",
  "issued_at":    "str"
}
```

When `include_balance=True`:

```json
{
  "tab_balance": "str"
}
```

`band_number` is `int`. `tab_balance` is `str` (Decimal). Timestamps are ISO 8601.

---

### `POST /gate/issue-band`

Returns `_band_dict(include_balance=True)`. **Status 201.**

Duplicate:

```json
{
  "...all _band_dict fields...": "...",
  "duplicate": true
}
```

**Status 200.** Full `_band_dict` (with `tab_balance`) plus `"duplicate": true`.

---

### `POST /gate/deactivate-band/<band_number>`

Returns `_band_dict(include_balance=True)`. **Status 200.**

---

### `GET /gate/bands/<band_number>`

Returns `_band_dict(include_balance=True)`. **Status 200.**

---

### `GET /gate/active-bands`

Returns `[_band_dict(include_balance=True)]`. **Status 200.**

---

### `POST /gate/headcount`

```json
{
  "date":    "str",
  "counted": 42
}
```

**Status 200.** `counted` is `int`. `date` is ISO 8601 date string.

---

### `POST /gate/forfeit-day`

```json
{
  "date":                 "str",
  "forfeited":            5,
  "total_unused_credit":  "str",
  "judge_alerts_fired":   2
}
```

**Status 200.** `forfeited` and `judge_alerts_fired` are `int`. `total_unused_credit` is `str` (Decimal).

---

### `GET /gate/reconciliation`

```json
{
  "date":                  "str",
  "bands_issued":          10,
  "gate_revenue":          "str",
  "expected_revenue":      "str",
  "mismatch":              "str",
  "headcount_recorded":    8,
  "headcount_mismatch":    true
}
```

**Status 200.** Money fields are `str`. `bands_issued` and `headcount_recorded` are `int`. `headcount_mismatch` is `bool`.

---

## 20. HR — Profiles

### `POST /hr/profiles`

```json
{
  "id":      "str",
  "user_id": "str",
  "full_name": "str"
}
```

**Status 201.**

---

### `GET /hr/profiles` — List (compact)

```json
[
  {
    "id":          "str",
    "user_id":     "str",
    "full_name":   "str",
    "phone":       "str | null",
    "hire_date":   "str | null",
    "is_active":   true,
    "wage_rate":   "str | null",
    "wage_period": "str | null"
  }
]
```

**Status 200.** `wage_rate` is `str` (Decimal) or `null`.

---

### `GET /hr/profiles/<id>` — Detail

```json
{
  "id":                      "str",
  "user_id":                 "str",
  "full_name":               "str",
  "phone":                   "str | null",
  "national_id":             "str | null",
  "emergency_contact_name":  "str | null",
  "emergency_contact_phone": "str | null",
  "hire_date":               "str | null",
  "wage_rate":               "str | null",
  "wage_period":             "str | null",
  "is_active":               true,
  "photo_path":              "str | null"
}
```

**Status 200.**

---

### `PATCH /hr/profiles/<id>`

```json
{
  "id":        "str",
  "full_name": "str",
  "is_active": true
}
```

**Status 200.**

---

### `POST /hr/profiles/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /hr/profiles/<id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

## 21. HR — Shifts

### `POST /hr/shifts`

```json
{
  "id":                  "str",
  "employee_id":         "str",
  "scheduled_start_utc": "str",
  "scheduled_end_utc":   "str"
}
```

**Status 201.** Timestamps are ISO 8601.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /hr/shifts`

```json
[
  {
    "id":            "str",
    "employee_id":   "str",
    "employee_name": "str",
    "start":         "str",
    "end":           "str",
    "role":          "str",
    "status":        "str"
  }
]
```

**Status 200.**

---

### `PATCH /hr/shifts/<id>`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /hr/shifts/<id>/cancel`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

## 22. HR — Clock Events

### `POST /hr/clock-in`

```json
{
  "id":         "str",
  "event_type": "CLOCK_IN",
  "occurred_at": "str",
  "shift_id":   "str | null",
  "no_shift":   false
}
```

**Status 201.** `no_shift` is `true` when the employee has no scheduled shift for the current slot.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /hr/clock-out`

```json
{
  "id":          "str",
  "event_type":  "CLOCK_OUT",
  "occurred_at": "str",
  "shift_id":    "str | null"
}
```

**Status 201.**

Duplicate: same as clock-in.

---

### `POST /hr/clock-events/manual` — Manual override

```json
{
  "id":                 "str",
  "event_type":         "str",
  "occurred_at":        "str",
  "is_manual_override": true,
  "override_reason":    "str"
}
```

**Status 201.** Manager or above.

Duplicate: same pattern.

---

### `GET /hr/clock-events`

```json
[
  {
    "id":                 "str",
    "employee_id":        "str",
    "event_type":         "str",
    "occurred_at":        "str",
    "shift_id":           "str | null",
    "is_manual_override": false,
    "source_ip":          "str | null"
  }
]
```

**Status 200.**

---

## 23. HR — Leave Requests

### `POST /hr/leave-requests`

```json
{
  "id":         "str",
  "status":     "PENDING",
  "leave_type": "str"
}
```

**Status 201.**

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /hr/leave-requests/<id>/approve`

```json
{
  "id":     "str",
  "status": "APPROVED"
}
```

**Status 200.**

---

### `POST /hr/leave-requests/<id>/reject`

```json
{
  "id":     "str",
  "status": "REJECTED"
}
```

**Status 200.**

---

### `POST /hr/leave-requests/<id>/cancel`

```json
{
  "id":     "str",
  "status": "CANCELLED"
}
```

**Status 200.**

---

### `GET /hr/leave-requests`

```json
[
  {
    "id":         "str",
    "employee":   "str",
    "leave_type": "str",
    "start_date": "str",
    "end_date":   "str",
    "status":     "str",
    "reason":     "str | null"
  }
]
```

**Status 200.**

---

## 24. HR — Attendance

### `GET /hr/attendance/today`

```json
[
  {
    "employee_id":   "str",
    "employee_name": "str",
    "shift_id":      "str",
    "shift_start":   "str",
    "shift_end":     "str",
    "status":        "clocked_in | approved_leave | absent_with_notice | absent_no_notice",
    "late":          false
  }
]
```

**Status 200.** One entry per scheduled shift for today.

---

### `GET /hr/attendance/employee/<profile_id>`

```json
{
  "employee_id":   "str",
  "employee_name": "str",
  "date":          "str",
  "hours_worked":  "str",
  "events": [
    {
      "id":                 "str",
      "event_type":         "str",
      "occurred_at":        "str",
      "shift_id":           "str | null",
      "is_manual_override": false
    }
  ]
}
```

**Status 200.** `hours_worked` is `str` (Decimal hours).

---

### `GET /hr/attendance/summary`

```json
[
  {
    "employee_id":       "str",
    "employee_name":     "str",
    "shifts_scheduled":  5,
    "shifts_attended":   4,
    "absent_with_notice": 1,
    "absent_no_notice":  0,
    "hours_worked":      "str"
  }
]
```

**Status 200.** Counts are `int`. `hours_worked` is `str`.

---

## 25. HR — Performance & Payroll

### `GET /hr/performance/<profile_id>`

```json
{
  "employee_id":       "str",
  "employee_name":     "str",
  "period_start":      "str",
  "period_end":        "str",
  "punctuality_score": "str",
  "attendance_score":  "str",
  "cash_health_score": "str",
  "void_health_score": "str",
  "composite_score":   "str",
  "detail": {
    "shifts_scheduled":  5,
    "shifts_attended":   4,
    "on_time_clock_ins": 3,
    "cash_shortfalls":   1,
    "void_rate_pct":     "str"
  }
}
```

**Status 200.** All scores are `str` (Decimal, 0–100 scale). `void_rate_pct` is `str`. Counts in `detail` are `int`.

---

### `GET /hr/payroll-draft`

```json
{
  "period_start": "str",
  "period_end":   "str",
  "employees": [
    {
      "employee_id":   "str",
      "employee_name": "str",
      "wage_rate":     "str",
      "wage_period":   "str",
      "hours_worked":  "str"
    }
  ]
}
```

**Status 200.** `wage_rate` and `hours_worked` are `str`.

---

## 26. HR — Absence Notices

### `POST /hr/absence-notices`

```json
{
  "id":          "str",
  "notice_type": "str",
  "sent_at":     "str"
}
```

**Status 201.**

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /hr/absence-notices`

```json
[
  {
    "id":                    "str",
    "employee_id":           "str",
    "employee_name":         "str",
    "notice_type":           "str",
    "expected_shift_id":     "str | null",
    "expected_late_minutes": "int | null",
    "reason":                "str | null",
    "sent_at":               "str"
  }
]
```

**Status 200.**

---

## 27. HR — WiFi Allow-list

### `POST /hr/wifi`

```json
{
  "id":      "str",
  "ssid":    "str",
  "ip_cidr": "str"
}
```

**Status 201.**

---

### `GET /hr/wifi`

```json
[
  {
    "id":        "str",
    "ssid":      "str",
    "ip_cidr":   "str",
    "label":     "str | null",
    "is_active": true
  }
]
```

**Status 200.**

---

### `PATCH /hr/wifi/<id>`

```json
{
  "id":        "str",
  "ssid":      "str",
  "ip_cidr":   "str",
  "is_active": true
}
```

**Status 200.**

---

### `POST /hr/wifi/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /hr/wifi/<id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

## 28. Finance — Cash Reconciliation

### `GET /finance/cash/pending`

```json
{
  "staff_id":      "str",
  "staff_name":    "str",
  "expected_total": "str",
  "payment_count": 3,
  "payments": [
    {
      "payment_id": "str",
      "amount":     "str",
      "tab_id":     "str",
      "created_at": "str"
    }
  ]
}
```

**Status 200.** `expected_total` and `amount` are `str`. `payment_count` is `int`.

---

### `POST /finance/cash/reconcile`

```json
{
  "id":              "str",
  "staff_id":        "str",
  "expected_amount": "str",
  "actual_amount":   "str",
  "difference":      "str",
  "status":          "BALANCED | SHORT | OVER",
  "payments_swept":  3
}
```

**Status 201.** Money fields are `str`. `payments_swept` is `int`.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

## 29. Finance — M-Pesa (Manual)

### `GET /finance/mpesa/pending`

```json
{
  "date":  "str",
  "count": 4,
  "payments": [
    {
      "payment_id": "str",
      "amount":     "str",
      "mpesa_code": "str",
      "received_by": "str",
      "created_at": "str"
    }
  ]
}
```

**Status 200.** `amount` is `str`.

---

### `POST /finance/mpesa/reconcile`

```json
{
  "reconciled": 3,
  "flagged":    1,
  "results": [
    {
      "payment_id": "str",
      "status":     "str"
    }
  ]
}
```

**Status 200.** `reconciled` and `flagged` are `int`.

---

### `GET /finance/card/summary`

```json
{
  "date":       "str",
  "card_total": "str",
  "card_count": 5,
  "note":       "str"
}
```

**Status 200.** `card_total` is `str`. `card_count` is `int`.

---

## 30. Finance — M-Pesa Daraja (Socket)

> **Dormant until `MPESA_CONSUMER_KEY` and four other env vars are set.**

### `POST /finance/mpesa/charge`

Active (env vars set):

```json
{
  "status":               "pending",
  "checkout_request_id":  "str",
  "customer_message":     "str"
}
```

**Status 200.**

Dormant (env vars not set):

```json
{
  "error":    "str",
  "fallback": "str"
}
```

**Status 503.**

---

### `POST /finance/mpesa/callback`

Always returns 200 — public endpoint, no JWT required:

```json
{
  "ResultCode": 0,
  "ResultDesc": "Accepted"
}
```

---

### `GET /finance/mpesa/status`

```json
{
  "configured": false,
  "message":    "str"
}
```

**Status 200.** Always responds. `message` explains what's missing if not configured.

---

## 31. Finance — Bank (Manual)

### `GET /finance/bank/pending`

```json
{
  "date":  "str",
  "count": 3,
  "payments": [
    {
      "payment_id":  "str",
      "amount":      "str",
      "bank_ref":    "str | null",
      "description": "str | null",
      "received_by": "str",
      "created_at":  "str"
    }
  ]
}
```

**Status 200.** `amount` is `str`.

---

### `POST /finance/bank/reconcile`

```json
{
  "reconciled": 2,
  "flagged":    1,
  "results": [
    {
      "payment_id": "str",
      "status":     "str"
    }
  ]
}
```

**Status 200.**

---

## 32. Finance — Bank Transfer (Socket)

> **SMS webhook is dormant until `BANK_SMS_WEBHOOK_SECRET` is set.
> Bank API is dormant until `BANK_PROVIDER` + `BANK_API_KEY` are set.**

### `POST /finance/bank/sms-forward`

Always returns 200 — public endpoint, no JWT required:

```json
{
  "status": "accepted"
}
```

---

### `POST /finance/bank/verify`

Active:

```json
{
  "provider":    "str",
  "verified_at": "str",
  "details": {
    "bank_ref":          "str",
    "confirmed_amount":  "str",
    "transaction_date":  "str"
  }
}
```

**Status 200.** `confirmed_amount` is `str`.

Dormant:

```json
{
  "error":    "str",
  "fallback": "str"
}
```

**Status 503.**

---

### `GET /finance/bank/status`

```json
{
  "sms_configured": false,
  "api_configured": false,
  "provider":       "str | null",
  "message":        "str"
}
```

**Status 200.** Always responds.

---

## 33. Finance — Card Gateway (Socket)

> **Dormant until `CARD_PROVIDER` + `CARD_API_KEY` + two other env vars are set.**

### `POST /finance/card/initiate`

Active:

```json
{
  "status":          "pending",
  "payment_url":     "str",
  "transaction_ref": "str",
  "provider":        "str"
}
```

**Status 200.**

Dormant:

```json
{
  "error":    "str",
  "fallback": "str"
}
```

**Status 503.**

---

### `POST /finance/card/callback`

Always returns 200 — public endpoint, no JWT required:

```json
{
  "status": "accepted"
}
```

---

### `GET /finance/card/status`

```json
{
  "configured": false,
  "provider":   "str | null",
  "message":    "str"
}
```

**Status 200.** Always responds.

---

## 34. Finance — Budgets

### `POST /finance/budgets`

```json
{
  "id":         "str",
  "department": "str",
  "period":     "str",
  "amount":     "str"
}
```

**Status 201.** `amount` is `str`.

---

### `PATCH /finance/budgets/<id>`

```json
{
  "id":        "str",
  "amount":    "str",
  "is_active": true
}
```

**Status 200.**

---

### `POST /finance/budgets/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /finance/budgets/<id>/enable`

```json
{
  "id":        "str",
  "is_active": true
}
```

**Status 200.**

---

### `GET /finance/budgets/status`

```json
{
  "period": "str",
  "budgets": [
    {
      "budget_id":   "str",
      "department":  "str",
      "period":      "str",
      "budget":      "str",
      "spent":       "str",
      "remaining":   "str",
      "pct_used":    "str",
      "over_budget": false
    }
  ]
}
```

**Status 200.** All money and percentage fields are `str`.

---

## 35. Finance — Anomalies

### `GET /finance/anomalies/voids`

```json
{
  "period_from":   "str",
  "period_to":     "str",
  "staff_rates": [
    {
      "...": "fields from get_void_rates() service"
    }
  ],
  "flagged_count": 0
}
```

**Status 200.** `staff_rates` items come from `get_void_rates()` in `app/services/hr.py`. Fields include per-staff void rate calculations.

---

### `GET /finance/anomalies/discounts`

```json
{
  "note":         "str",
  "staff_rates":  [],
  "flagged_count": 0
}
```

**Status 200.** Placeholder endpoint — always returns empty `staff_rates` and `flagged_count: 0` with a note explaining it's not yet implemented.

---

## 36. Finance — Reports & Dashboard

### `GET /finance/reconciliation`

```json
{
  "date": "str",
  "receipts": {
    "cash":  "str",
    "card":  "str",
    "mpesa": "str",
    "total": "str"
  },
  "cash_reconciliation": {
    "total_collected":  "str",
    "total_expected":   "str",
    "total_handed_in":  "str",
    "difference":       "str",
    "shortfalls": ["str"],
    "pending_staff": ["str"]
  },
  "stock": {
    "open_alerts_count": 0,
    "alerts": [
      {
        "type":        "str",
        "severity":    "str",
        "description": "str"
      }
    ]
  },
  "period_closed": false,
  "balanced":      true,
  "gaps":          ["str"]
}
```

**Status 200.** All money fields are `str`. `open_alerts_count` is `int`. `gaps` is an array of plain-English strings describing reconciliation gaps. `shortfalls` lists staff names with shortfalls.

---

### `POST /finance/close-period`

```json
{
  "id":                   "str",
  "date":                 "str",
  "safe_count":           "str",
  "expected_total_cash":  "str",
  "difference":           "str",
  "status":               "str"
}
```

**Status 201.** Money fields are `str`.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /finance/dashboard`

```json
{
  "period": "str",
  "revenue": {
    "today": "str",
    "week":  "str",
    "month": "str"
  },
  "budgets": [
    {
      "department":  "str",
      "budget":      "str",
      "spent":       "str",
      "remaining":   "str",
      "pct_used":    "str",
      "over_budget": false
    }
  ],
  "open_shortfalls":       0,
  "no_receipt_purchases":  0,
  "judge_alerts_open":     0
}
```

**Status 200.** Money fields are `str`. Counts are `int`.

---

## 37. Events

### Helper: `_event_dict`

```json
{
  "id":              "str",
  "title":           "str",
  "event_type":      "str",
  "booking_id":      "str | null",
  "starts_at":       "str",
  "ends_at":         "str",
  "expected_guests": 50,
  "location":        "str | null",
  "notes":           "str | null",
  "status":          "str"
}
```

`expected_guests` is `int`. Timestamps are ISO 8601.

---

### Helper: `_assignment_dict`

```json
{
  "id":             "str",
  "event_id":       "str",
  "employee_id":    "str",
  "employee_name":  "str",
  "role_on_event":  "str",
  "status":         "str"
}
```

---

### Helper: `_alloc_dict`

```json
{
  "id":                  "str",
  "event_id":            "str",
  "inventory_item_id":   "str",
  "item_name":           "str",
  "allocated_quantity":  "str",
  "notes":               "str | null",
  "status":              "str"
}
```

`allocated_quantity` is `str` (Decimal).

---

### `GET /event-types`

```json
[
  {
    "id":   "str",
    "name": "str"
  }
]
```

**Status 200.**

---

### `POST /event-types`

```json
{
  "id":   "str",
  "name": "str"
}
```

**Status 201.**

---

### `POST /event-types/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /events`

Returns `_event_dict`. **Status 201.**

Duplicate:

```json
{
  "...all _event_dict fields...": "...",
  "duplicate": true
}
```

**Status 200.** Full `_event_dict` plus `"duplicate": true`.

---

### `PATCH /events/<id>`

Returns `_event_dict`. **Status 200.**

---

### `POST /events/<id>/confirm`

Returns `_event_dict`, optionally with:

```json
{
  "notifications_scheduled": 3
}
```

**Status 200.** `notifications_scheduled` is `int`, present only when notifications were queued.

---

### `POST /events/<id>/start`

Returns `_event_dict`. **Status 200.**

---

### `POST /events/<id>/complete`

Returns `_event_dict`. **Status 200.**

---

### `POST /events/<id>/cancel`

```json
{
  "...all _event_dict fields...": "...",
  "notifications_cancelled": 2
}
```

**Status 200.** Full `_event_dict` plus `"notifications_cancelled"` (int).

---

### `GET /events`

Returns `[_event_dict]`. **Status 200.**

---

### `GET /events/upcoming`

Returns `[_event_dict]`. **Status 200.**

---

### `GET /events/<id>`

Returns `_event_dict`. **Status 200.**

---

### `POST /events/<id>/assignments`

Returns `_assignment_dict`, optionally with:

```json
{
  "notifications_scheduled": 1
}
```

**Status 201.**

---

### `POST /events/<id>/assignments/<assignment_id>/acknowledge`

Returns `_assignment_dict`. **Status 200.**

---

### `POST /events/<id>/assignments/<assignment_id>/cancel`

Returns `_assignment_dict`. **Status 200.**

---

### `GET /events/<id>/assignments`

Returns `[_assignment_dict]`. **Status 200.**

---

### `POST /events/<id>/inventory/allocate`

Returns `_alloc_dict`. **Status 201.**

Duplicate:

```json
{
  "...all _alloc_dict fields...": "...",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /events/<id>/inventory/<alloc_id>/issue`

```json
{
  "...all _alloc_dict fields...": "...",
  "movement_id": "str"
}
```

**Status 200.** Full `_alloc_dict` plus `movement_id`.

---

### `POST /events/<id>/inventory/<alloc_id>/return`

```json
{
  "...all _alloc_dict fields...": "...",
  "return_movement_id": "str"
}
```

**Status 200.** Full `_alloc_dict` plus `return_movement_id`.

---

### `POST /events/<id>/inventory/<alloc_id>/consume`

Returns `_alloc_dict`. **Status 200.**

---

### `GET /events/<id>/inventory`

```json
{
  "allocations":    [{ "_alloc_dict": "..." }],
  "reconciliation": { "...": "..." }
}
```

**Status 200.** `reconciliation` is a dict of inventory reconciliation summary for the event.

---

## 38. Conduct

### Helper: `_rule_dict`

```json
{
  "id":         "str",
  "rule_key":   "str",
  "version":    1,
  "title":      "str",
  "body":       "str",
  "category":   "str",
  "is_active":  true,
  "created_at": "str"
}
```

`version` is `int`.

---

### `POST /conduct/rules`

Returns `_rule_dict`. **Status 201.**

---

### `GET /conduct/rules`

Returns `[_rule_dict]`. **Status 200.**

---

### `GET /conduct/rules/<id>/versions`

Returns `[_rule_dict]`. **Status 200.** All versions of the given rule key.

---

### `POST /conduct/sign`

```json
{
  "id":        "str",
  "rule_key":  "str",
  "version":   1,
  "signed_at": "str"
}
```

**Status 201.** `version` is `int`.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /conduct/signatures/<employee_id>`

```json
[
  {
    "id":        "str",
    "rule_key":  "str",
    "version":   1,
    "title":     "str",
    "signed_at": "str"
  }
]
```

**Status 200.**

---

### `GET /conduct/compliance`

```json
[
  {
    "rule_id":            "str",
    "rule_key":           "str",
    "title":              "str",
    "version":            1,
    "unsigned_count":     3,
    "unsigned_employees": ["str"],
    "message":            "str"
  }
]
```

**Status 200.** Manager or above. `unsigned_count` is `int`. `unsigned_employees` is an array of employee names who have not signed the current version.

---

## 39. Disputes

### Helper: `_dispute_dict`

```json
{
  "id":               "str",
  "category":         "str",
  "status":           "str",
  "priority":         "str",
  "is_owner_only":    false,
  "description":      "str",
  "reporter":         "str",
  "subjects":         ["str"],
  "assigned_to":      "str | null",
  "resolution_notes": "str | null",
  "created_at":       "str"
}
```

`subjects` is an array of employee name strings.

---

### `POST /disputes`

Returns `_dispute_dict`. **Status 201.**

Duplicate:

```json
{
  "...all _dispute_dict fields...": "...",
  "duplicate": true
}
```

**Status 200.**

---

### `POST /disputes/<id>/claim`

Returns `_dispute_dict`. **Status 200.**

---

### `POST /disputes/<id>/resolve`

Returns `_dispute_dict`. **Status 200.**

---

### `POST /disputes/<id>/dismiss`

Returns `_dispute_dict`. **Status 200.**

---

### `GET /disputes`

Returns `[_dispute_dict]`. **Status 200.**

> **Authorization note:** Owner sees all disputes (including `is_owner_only: true`). Managers see only non-owner-only disputes — `OWNER_PRIVATE` rows are structurally absent from the query, not filtered from a list. Staff see only disputes they reported.

---

## 40. Suggestions

### Helper: `_suggestion_dict`

```json
{
  "id":           "str",
  "category":     "MANAGEMENT | OWNER_PRIVATE",
  "subject":      "str",
  "body":         "str",
  "status":       "str",
  "submitted_by": "str",
  "reviewed_by":  "str | null",
  "reviewed_at":  "str | null",
  "response":     "str | null",
  "created_at":   "str"
}
```

---

### `POST /suggestions`

Returns `_suggestion_dict`. **Status 201.**

Duplicate:

```json
{
  "...all _suggestion_dict fields...": "...",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /suggestions`

Returns `[_suggestion_dict]`. **Status 200.**

> **Authorization note:** Managers see only `MANAGEMENT` category. Owner sees both. `OWNER_PRIVATE` rows are structurally absent from manager queries.

---

### `GET /suggestions/<id>`

Returns `_suggestion_dict`. **Status 200.** Returns 404 for managers attempting to access an `OWNER_PRIVATE` suggestion.

---

### `POST /suggestions/<id>/review`

Returns `_suggestion_dict`. **Status 200.**

---

## 41. Feedback

### `POST /feedback`

```json
{
  "id":         "str",
  "score":      5,
  "guest_name": "str | null",
  "created_at": "str"
}
```

**Status 201.** `score` is `int`.

Duplicate:

```json
{
  "id":        "str",
  "duplicate": true
}
```

**Status 200.**

---

### `GET /feedback`

```json
{
  "count":         10,
  "average_score": "str",
  "recent": [
    {
      "id":         "str",
      "score":      5,
      "guest_name": "str | null",
      "comments":   "str | null",
      "created_at": "str"
    }
  ]
}
```

**Status 200.** `count` is `int`. `average_score` is `str` (Decimal). `score` in items is `int`.

---

### `GET /feedback/staff/<employee_id>`

```json
{
  "employee_id":      "str",
  "employee_name":    "str",
  "count":            5,
  "average_score":    "str",
  "recent_comments":  ["str"]
}
```

**Status 200.** `count` is `int`. `average_score` is `str`. `recent_comments` is an array of comment strings.

---

## 42. Equipment

### Helper: `_eq_dict`

```json
{
  "id":                    "str",
  "name":                  "str",
  "equipment_type":        "str",
  "department_id":         "str",
  "status":                "str",
  "last_service_utc":      "str | null",
  "service_interval_days": 30,
  "is_due_service":        false,
  "notes":                 "str | null",
  "is_active":             true
}
```

`service_interval_days` is `int`. `is_due_service` is a derived `@property` (bool).

---

### `POST /equipment`

Returns `_eq_dict`. **Status 201.**

---

### `GET /equipment`

Returns `[_eq_dict]`. **Status 200.**

---

### `PATCH /equipment/<id>`

Returns `_eq_dict`. **Status 200.**

---

### `POST /equipment/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

### `POST /equipment/<id>/maintenance`

```json
{
  "id":           "str",
  "equipment_id": "str",
  "performed_at": "str"
}
```

**Status 201.** `performed_at` is ISO 8601.

---

### `POST /equipment/<id>/safety-check`

```json
{
  "id":               "str",
  "passed":           true,
  "equipment_status": "str"
}
```

**Status 201.** `passed` is `bool`. `equipment_status` reflects the equipment's new status after the check.

---

### `GET /equipment/checklist-templates/<type>`

```json
{
  "equipment_type": "str",
  "items":          ["str"],
  "count":          7
}
```

**Status 200.** `count` is `int`. Known types: `jetski`, `motorboat`, `paddle_boat`, `bicycle`.

---

## 43. Judge Alerts

### `GET /judge/alerts`

```json
[
  {
    "id":          "str",
    "item_id":     "str",
    "item_name":   "str",
    "alert_type":  "str",
    "severity":    "str",
    "description": "str",
    "status":      "str",
    "created_at":  "str"
  }
]
```

**Status 200.**

---

### `POST /judge/alerts/<id>/acknowledge`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

## 44. Notifications

### Helper: `_notif_dict`

```json
{
  "id":              "str",
  "reference_type":  "str",
  "reference_id":    "str",
  "subject":         "str",
  "body":            "str",
  "status":          "str",
  "channel":         "str",
  "scheduled_for":   "str | null",
  "sent_at":         "str | null",
  "read_at":         "str | null"
}
```

---

### `GET /notifications/inbox`

Returns `[_notif_dict]`. **Status 200.** Current user's unread DELIVERED notifications.

---

### `POST /notifications/<id>/mark-read`

Returns `_notif_dict`. **Status 200.**

---

### `GET /notifications/whatsapp/status`

```json
{
  "configured": false,
  "message":    "str"
}
```

**Status 200.**

---

### `GET /notifications`

Returns `[_notif_dict]`. **Status 200.** Admin view, limit 100. Manager or above.

---

## 45. Calendar View

### Helper: `_entry_dict`

```json
{
  "id":                          "str",
  "title":                       "str",
  "entry_type":                  "str",
  "date_start":                  "str",
  "date_end":                    "str",
  "is_peak":                     false,
  "description":                 "str | null",
  "planning_trigger_offset_days": 7,
  "is_active":                   true
}
```

`planning_trigger_offset_days` is `int`.

---

### `POST /calendar`

Returns `_entry_dict`. **Status 201.**

---

### `GET /calendar`

Returns `[_entry_dict]`. **Status 200.**

---

### `POST /calendar/<id>/disable`

```json
{
  "id":        "str",
  "is_active": false
}
```

**Status 200.**

---

## 46. Owner Dashboard

> All dashboard endpoints are owner-only (role.level = 10).

---

### `GET /dashboard/overview`

```json
{
  "period": "str",
  "revenue": {
    "total":       "str",
    "by_tab_type": { "str": "str" },
    "by_method":   { "str": "str" }
  },
  "staff": {
    "on_duty":       5,
    "on_duty_names": ["str"]
  },
  "bookings": {
    "active":            3,
    "arrivals_today":    2,
    "departures_today":  1
  },
  "inventory_alerts": 2,
  "top_alerts": [
    {
      "id":          "str",
      "type":        "str",
      "severity":    "str",
      "description": "str"
    }
  ],
  "week_calendar": [
    {
      "title":   "str",
      "date":    "str",
      "is_peak": false,
      "type":    "str"
    }
  ]
}
```

**Status 200.** Revenue values are `str`. Counts are `int`.

---

### `GET /dashboard/inventory`

```json
{
  "total_skus":     42,
  "low_stock_count": 3,
  "items": [
    {
      "id":            "str",
      "name":          "str",
      "unit":          "str",
      "current_stock": "str",
      "reorder_level": "str",
      "is_low":        true
    }
  ],
  "recent_movements": [
    {
      "item":   "str",
      "reason": "str",
      "amount": "str",
      "at":     "str"
    }
  ],
  "alerts": [
    {
      "id":          "str",
      "type":        "str",
      "severity":    "str",
      "description": "str"
    }
  ]
}
```

**Status 200.** Counts are `int`. Stock values are `str`.

---

### `GET /dashboard/finance`

```json
{
  "period":               "str",
  "total_revenue":        "str",
  "reconciliation_status": "str",
  "open_shortfalls":      2,
  "unmatched_mpesa":      1,
  "pending_approvals":    3,
  "department_budgets": [
    {
      "department": "str",
      "budgeted":   "str"
    }
  ]
}
```

**Status 200.** Money is `str`. Counts are `int`.

---

### `GET /dashboard/bookings`

```json
{
  "occupancy_by_type": { "str": "int" },
  "arrivals_today": [
    {
      "id":    "str",
      "guest": "str"
    }
  ],
  "departures_today": [
    {
      "id":    "str",
      "guest": "str"
    }
  ],
  "pending_deposits": [
    {
      "id":               "str",
      "guest":            "str",
      "resource":         "str",
      "deposit_required": "str",
      "deposit_paid":     "str"
    }
  ],
  "pending_waivers_tomorrow": [
    {
      "booking_id": "str",
      "guest":      "str"
    }
  ],
  "villa_revenue": "str"
}
```

**Status 200.** Money is `str`.

---

### `GET /dashboard/staff`

```json
{
  "active_employees": 12,
  "on_duty":          5,
  "absent_today":     2,
  "open_disputes": {
    "management":    3,
    "owner_private": 1
  },
  "new_suggestions": {
    "management":    2,
    "owner_private": 0
  },
  "top_performers": [
    {
      "name":  "str",
      "score": "str"
    }
  ],
  "bottom_performers": [
    {
      "name":  "str",
      "score": "str"
    }
  ]
}
```

**Status 200.** Counts are `int`. `score` is `str`.

---

### `GET /dashboard/conduct`

```json
{
  "active_rules":            5,
  "compliance": [
    {
      "rule_key":    "str",
      "title":       "str",
      "version":     1,
      "signed_pct":  "str",
      "unsigned_count": 2
    }
  ],
  "overall_compliance_pct": "str",
  "open_disputes":          1,
  "recent_disputes": [
    {
      "id":       "str",
      "category": "str",
      "priority": "str"
    }
  ]
}
```

**Status 200.** Counts are `int`. Percentages are `str`.

---

### `GET /dashboard/suggestions`

```json
{
  "management": [
    {
      "id":           "str",
      "subject":      "str",
      "status":       "str",
      "submitted_by": "str",
      "created_at":   "str"
    }
  ],
  "owner_private": [
    {
      "id":           "str",
      "subject":      "str",
      "status":       "str",
      "submitted_by": "str",
      "created_at":   "str"
    }
  ]
}
```

**Status 200.** Both arrays have the same item shape.

---

### `GET /dashboard/calendar`

```json
{
  "calendar_entries": [
    {
      "id":      "str",
      "title":   "str",
      "type":    "str",
      "date":    "str",
      "is_peak": false
    }
  ],
  "events": [
    {
      "id":        "str",
      "title":     "str",
      "status":    "str",
      "starts_at": "str"
    }
  ]
}
```

**Status 200.**

---

### `GET /dashboard/feedback`

```json
{
  "period":      "str",
  "overall_avg": "str",
  "by_department": [
    {
      "department": "str",
      "avg_score":  "str",
      "count":      5
    }
  ],
  "by_staff": [
    {
      "employee":  "str",
      "avg_score": "str",
      "count":     3
    }
  ],
  "recent_comments": [
    {
      "score":   5,
      "comment": "str",
      "guest":   "str | null"
    }
  ]
}
```

**Status 200.** Averages are `str`. `count` and `score` are `int`.

---

### `GET /dashboard/equipment`

```json
{
  "total": 8,
  "due_service": [
    {
      "id":            "str",
      "name":          "str",
      "type":          "str",
      "last_service":  "str | null",
      "interval_days": 30
    }
  ],
  "in_maintenance": [
    {
      "id":   "str",
      "name": "str"
    }
  ]
}
```

**Status 200.** `total` and `interval_days` are `int`.

---

### `GET /dashboard/alerts`

```json
[
  {
    "id":                  "str",
    "type":                "str",
    "severity":            "str",
    "description":         "str",
    "recommended_action":  "str",
    "status":              "str",
    "created_at":          "str"
  }
]
```

**Status 200.**

---

### `POST /dashboard/alerts/<id>/acknowledge`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

### `POST /dashboard/alerts/<id>/action-taken`

```json
{
  "id":     "str",
  "status": "str"
}
```

**Status 200.**

---

*End of API Response Shapes.*
