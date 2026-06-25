#!/usr/bin/env python3
"""
Chaos Test Round 2 -- deep-dive on crashes, vulns, and skipped tests from Round 1.
"""
import os
import requests
import json
import uuid
import time
from decimal import Decimal

BASE = "http://localhost:5000"
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "Kurahia1!")
RESULTS = []


def login(username, password=None):
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": username, "password": password or SEED_PASSWORD})
    data = r.json()
    token = data.get("access_token", "FAIL")
    if token == "FAIL":
        print(f"  LOGIN FAIL for {username}: {data}")
    return token


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def record(cat, name, status, detail, verdict):
    RESULTS.append((cat, name, status, detail, verdict))
    v = {"HANDLED": "[OK]", "CRASHED": "[CRASH]", "VULNERABLE": "[VULN]"}
    print(f"  {v.get(verdict, '[??]')} {name}: {status} -> {verdict}")


print("=== Auth ===")
OT = login("wachira")
MT = login("manager2")
WT = login("waiter1")
assert OT != "FAIL" and MT != "FAIL" and WT != "FAIL", "Login failed"

# Get IDs
menu_items = requests.get(f"{BASE}/menu/items", headers=auth(OT)).json()
MI_ID = menu_items[0]["id"]
MI_PRICE = menu_items[0]["price"]
print(f"  Menu item: {menu_items[0]['name']} price={MI_PRICE}")

inv_r = requests.get(f"{BASE}/inventory/items", headers=auth(OT))
inv = inv_r.json()
DEPT_ID = inv[0]["department_id"]
INV_ID = inv[0]["id"]

# ====================================================================
# DEEP DIVE: Crashes from Round 1
# ====================================================================
print("\n=== CRASH INVESTIGATION ===")

# Crash 1: Negative reorder_level -> 500
r = requests.post(f"{BASE}/inventory/items", headers=auth(MT),
    json={"name": f"crash_neg_{uuid.uuid4().hex[:4]}", "unit": "each",
          "department_id": DEPT_ID, "reorder_level": -50})
print(f"  Negative reorder_level: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
record("CRASH DIVE", "Negative reorder_level", r.status_code, r.text[:200],
       "CRASHED" if r.status_code == 500 else "HANDLED" if r.status_code == 400 else "VULNERABLE")

# Crash 2: Negative price via PATCH -> 500
r = requests.patch(f"{BASE}/menu/items/{MI_ID}", headers=auth(MT),
    json={"price": "-10"})
print(f"  Negative price PATCH: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
record("CRASH DIVE", "Negative price PATCH", r.status_code, r.text[:200],
       "CRASHED" if r.status_code == 500 else "HANDLED" if r.status_code == 400 else "VULNERABLE")
# Restore if it worked
if r.status_code == 200:
    requests.patch(f"{BASE}/menu/items/{MI_ID}", headers=auth(MT), json={"price": MI_PRICE})

# ====================================================================
# DEEP DIVE: Vulnerabilities from Round 1
# ====================================================================
print("\n=== VULNERABILITY INVESTIGATION ===")

# Vuln 1: Negative quantity order accepted (409 = stock check, not input validation)
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": MI_ID, "quantity": -5}]})
print(f"  Negative qty order: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
# If 409 = stock conflict, it means negative qty passed validation but hit stock check
record("VULN DIVE", "Negative quantity (-5)", r.status_code, r.text[:200],
       "VULNERABLE" if r.status_code != 400 else "HANDLED")

# Vuln 2: Zero quantity order
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": MI_ID, "quantity": 0}]})
print(f"  Zero qty order: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
record("VULN DIVE", "Zero quantity (0)", r.status_code, r.text[:200],
       "VULNERABLE" if r.status_code != 400 else "HANDLED")

# Vuln 3: NaN payment -> 500
tab_r = requests.post(f"{BASE}/tabs", headers=auth(WT), json={"tab_type": "WALK_IN"})
tab_id = tab_r.json()["id"]
r = requests.post(f"{BASE}/tabs/{tab_id}/payments", headers=auth(WT),
    json={"amount": "NaN", "method": "CASH"})
print(f"  NaN payment: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
record("VULN DIVE", "NaN payment amount", r.status_code, r.text[:200],
       "CRASHED" if r.status_code == 500 else "VULNERABLE" if r.status_code == 201 else "HANDLED")

# Vuln 4: Infinity payment
r = requests.post(f"{BASE}/tabs/{tab_id}/payments", headers=auth(WT),
    json={"amount": "Infinity", "method": "CASH"})
print(f"  Infinity payment: HTTP {r.status_code}")
print(f"  Response: {r.text[:300]}")
record("VULN DIVE", "Infinity payment amount", r.status_code, r.text[:200],
       "VULNERABLE" if r.status_code == 201 else "HANDLED")

# Vuln 5: 10,000 char reference
long_ref = "A" * 10000
r = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": long_ref})
print(f"  10K char reference: HTTP {r.status_code}")
if r.status_code == 201:
    stored_ref = r.json().get("reference", "")
    print(f"  Stored length: {len(stored_ref) if stored_ref else 0}")
    record("VULN DIVE", "10K char reference stored", r.status_code,
           f"stored_len={len(stored_ref) if stored_ref else 0}",
           "VULNERABLE" if stored_ref and len(stored_ref) > 500 else "HANDLED")
else:
    record("VULN DIVE", "10K char reference", r.status_code, r.text[:200],
           "HANDLED" if r.status_code == 400 else "CRASHED")

# Vuln 6: 50K suggestion body
r = requests.post(f"{BASE}/suggestions", headers=auth(WT),
    json={"category": "MANAGEMENT", "subject": "Chaos",
          "body": "X" * 50000, "idempotency_key": str(uuid.uuid4())})
print(f"  50K suggestion body: HTTP {r.status_code}")
record("VULN DIVE", "50K suggestion body", r.status_code, r.text[:200],
       "VULNERABLE" if r.status_code in (201, 200) else "HANDLED")

# Vuln 7: Tab open has no idempotency
idem = str(uuid.uuid4())
r1 = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "idempotency_key": idem})
r2 = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "idempotency_key": idem})
print(f"  Tab double-create: {r1.json().get('id')[:8]} vs {r2.json().get('id')[:8]}")
record("VULN DIVE", "Tab open no idempotency", f"{r1.status_code}/{r2.status_code}",
       f"different IDs: {r1.json()['id'] != r2.json()['id']}",
       "VULNERABLE" if r1.json()["id"] != r2.json()["id"] else "HANDLED")


# ====================================================================
# SKIPPED TESTS: State machine + order lifecycle (full walk-through)
# ====================================================================
print("\n=== STATE MACHINE DEEP TEST ===")

# Find a menu item with prep_station != NONE (kitchen/bar item)
kitchen_item = None
for mi in menu_items:
    if mi.get("prep_station") not in (None, "NONE"):
        kitchen_item = mi
        break

if kitchen_item:
    print(f"  Found kitchen/bar item: {kitchen_item['name']} (prep={kitchen_item.get('prep_station')})")
    ki_id = kitchen_item["id"]

    # Create tab + order + send (with kitchen item)
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "state-machine-deep"})
    sm_tab_id = tab_r.json()["id"]
    ord_r = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": sm_tab_id, "items": [{"menu_item_id": ki_id, "quantity": 1}]})
    if ord_r.status_code == 201:
        ord_id = ord_r.json()["id"]
        send_r = requests.post(f"{BASE}/orders/{ord_id}/send", headers=auth(WT))
        print(f"  Order sent: {send_r.status_code}")

        # Get order items
        tab_d = requests.get(f"{BASE}/tabs/{sm_tab_id}", headers=auth(WT)).json()
        oi = tab_d["orders"][0]["items"][0]
        oi_id = oi["id"]
        print(f"  Order item status: {oi['status']}")

        if oi["status"] == "PENDING":
            # PENDING -> RECEIVED
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "PENDING -> RECEIVED", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 200 else "CRASHED")

            # RECEIVED -> RECEIVED (duplicate)
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "RECEIVED -> RECEIVED (reject)", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

            # RECEIVED -> READY
            r = requests.post(f"{BASE}/order-items/{oi_id}/ready", headers=auth(MT))
            record("STATE MACHINE", "RECEIVED -> READY", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 200 else "CRASHED")

            # READY -> READY (duplicate)
            r = requests.post(f"{BASE}/order-items/{oi_id}/ready", headers=auth(MT))
            record("STATE MACHINE", "READY -> READY (reject)", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

            # READY -> SERVED
            r = requests.post(f"{BASE}/order-items/{oi_id}/serve", headers=auth(WT))
            record("STATE MACHINE", "READY -> SERVED", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 200 else "CRASHED")

            # SERVED -> READY (reject backward)
            r = requests.post(f"{BASE}/order-items/{oi_id}/ready", headers=auth(MT))
            record("STATE MACHINE", "SERVED -> READY (reject backward)", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

            # SERVED -> RECEIVED (reject backward)
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "SERVED -> RECEIVED (reject backward)", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

            # SERVED -> SERVED (reject)
            r = requests.post(f"{BASE}/order-items/{oi_id}/serve", headers=auth(WT))
            record("STATE MACHINE", "SERVED -> SERVED (reject)", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

        # Send already-sent order
        r = requests.post(f"{BASE}/orders/{ord_id}/send", headers=auth(WT))
        record("STATE MACHINE", "Send already-sent order", r.status_code, r.text[:100],
               "HANDLED" if r.status_code == 400 else "VULNERABLE")
    elif ord_r.status_code == 409:
        print(f"  Order failed (stock conflict): {ord_r.text[:200]}")
        # Try with a non-kitchen item instead
else:
    print("  No kitchen/bar menu item found -- testing with auto-served item")
    # Auto-served items (prep_station=NONE) go straight to SERVED
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "auto-serve-test"})
    sm_tab_id = tab_r.json()["id"]
    ord_r = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": sm_tab_id, "items": [{"menu_item_id": MI_ID, "quantity": 1}]})
    if ord_r.status_code == 201:
        ord_id = ord_r.json()["id"]
        requests.post(f"{BASE}/orders/{ord_id}/send", headers=auth(WT))
        tab_d = requests.get(f"{BASE}/tabs/{sm_tab_id}", headers=auth(WT)).json()
        oi = tab_d["orders"][0]["items"][0]
        oi_id = oi["id"]
        print(f"  Auto-served item status: {oi['status']}")
        if oi["status"] == "SERVED":
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "Receive auto-served item", r.status_code, r.text[:100],
                   "HANDLED" if r.status_code == 400 else "VULNERABLE")

# Check out without check-in
r = requests.get(f"{BASE}/bookings/resources", headers=auth(OT))
resources = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
if resources:
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    res_id = resources[0]["id"]
    bk_r = requests.post(f"{BASE}/bookings", headers=auth(MT), json={
        "resource_id": res_id, "guest_name": "Chaos2", "guest_phone": "0712345678",
        "check_in_planned": (now + timedelta(hours=2)).isoformat(),
        "check_out_planned": (now + timedelta(days=2)).isoformat(),
        "number_of_guests": 1,
    })
    if bk_r.status_code == 201:
        bk_id = bk_r.json()["id"]
        requests.post(f"{BASE}/bookings/{bk_id}/confirm", headers=auth(MT))
        r = requests.post(f"{BASE}/bookings/{bk_id}/check-out", headers=auth(MT))
        record("STATE MACHINE", "Check out without check-in", r.status_code, r.text[:150],
               "HANDLED" if r.status_code == 400 else "VULNERABLE")
    else:
        print(f"  Booking create failed: {bk_r.status_code} {bk_r.text[:200]}")
else:
    print("  No bookable resources found")

# Approve already-approved PR
mgr_inv_r = requests.get(f"{BASE}/inventory/items", headers=auth(MT))
mgr_inv = mgr_inv_r.json() if mgr_inv_r.status_code == 200 and isinstance(mgr_inv_r.json(), list) else []
if mgr_inv:
    pr_r = requests.post(f"{BASE}/inventory/purchase-requests", headers=auth(MT), json={
        "items": [{"inventory_item_id": mgr_inv[0]["id"], "quantity": 5}],
        "justification": "Chaos deep test", "urgency": "LOW",
    })
    if pr_r.status_code == 201:
        pr_id = pr_r.json()["id"]
        r1 = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                           headers=auth(OT), json={"action": "approve"})
        r2 = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                           headers=auth(OT), json={"action": "approve"})
        record("STATE MACHINE", "Approve already-approved PR", r2.status_code, r2.text[:150],
               "HANDLED" if r2.status_code == 400 else "VULNERABLE")


# ====================================================================
# DATA INTEGRITY: Full financial cycle
# ====================================================================
print("\n=== DATA INTEGRITY DEEP TEST ===")

# Full cycle: tab -> order -> send -> partial pay -> full pay -> close
tab_r = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": "integrity-deep"})
if tab_r.status_code == 201:
    it_id = tab_r.json()["id"]
    ord_r = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": it_id, "items": [{"menu_item_id": MI_ID, "quantity": 3}]})
    if ord_r.status_code == 201:
        oid = ord_r.json()["id"]
        send_r = requests.post(f"{BASE}/orders/{oid}/send", headers=auth(WT))
        tab_d = requests.get(f"{BASE}/tabs/{it_id}", headers=auth(WT)).json()
        charges = tab_d["charges"]
        total = sum(Decimal(c["amount"]) for c in charges)
        print(f"  Total charges: {total}")

        # Pay 1/3
        third = total / 3
        p1 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(third), "method": "CASH"})
        bal1 = Decimal(p1.json()["tab_balance"])
        expected1 = total - third
        print(f"  After 1/3 payment: balance={bal1}, expected={expected1}")
        record("INTEGRITY", "Balance after 1/3 payment", p1.status_code,
               f"exp={expected1} got={bal1}", "HANDLED" if bal1 == expected1 else "VULNERABLE")

        # Pay another 1/3
        p2 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(third), "method": "MPESA", "mpesa_code": "ABC123"})
        bal2 = Decimal(p2.json()["tab_balance"])
        expected2 = total - (third * 2)
        print(f"  After 2/3 payment: balance={bal2}, expected={expected2}")
        record("INTEGRITY", "Balance after 2/3 payment", p2.status_code,
               f"exp={expected2} got={bal2}", "HANDLED" if bal2 == expected2 else "VULNERABLE")

        # Pay final third
        remaining = bal2
        p3 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(remaining), "method": "CASH"})
        bal3 = Decimal(p3.json()["tab_balance"])
        print(f"  After full payment: balance={bal3}")
        record("INTEGRITY", "Balance reaches zero after full payment", p3.status_code,
               f"got={bal3}", "HANDLED" if bal3 == 0 else "VULNERABLE")

        # Now close
        close_r = requests.post(f"{BASE}/tabs/{it_id}/close", headers=auth(WT))
        record("INTEGRITY", "Close fully-paid tab", close_r.status_code,
               close_r.text[:100], "HANDLED" if close_r.status_code == 200 else "CRASHED")

        # Verify closed tab rejects orders
        r = requests.post(f"{BASE}/orders", headers=auth(WT),
            json={"tab_id": it_id, "items": [{"menu_item_id": MI_ID, "quantity": 1}]})
        record("INTEGRITY", "Order on closed tab rejected", r.status_code,
               r.text[:100], "HANDLED" if r.status_code == 400 else "VULNERABLE")

        # Verify closed tab rejects payments
        r = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": "100", "method": "CASH"})
        record("INTEGRITY", "Payment on closed tab rejected", r.status_code,
               r.text[:100], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# Stock integrity test
unique = f"stock_integ_{uuid.uuid4().hex[:4]}"
item_r = requests.post(f"{BASE}/inventory/items", headers=auth(MT),
    json={"name": unique, "unit": "liters", "department_id": DEPT_ID})
if item_r.status_code == 201:
    sid = item_r.json()["id"]
    # Add 100
    requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
        json={"inventory_item_id": sid, "change_amount": "100", "reason": "DELIVERY"})
    # Remove 30
    requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
        json={"inventory_item_id": sid, "change_amount": "-30", "reason": "USAGE"})
    # Add 15
    requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
        json={"inventory_item_id": sid, "change_amount": "15", "reason": "DELIVERY"})
    # Expected: 100 - 30 + 15 = 85

    all_items = requests.get(f"{BASE}/inventory/items", headers=auth(MT)).json()
    if isinstance(all_items, dict):
        all_items = all_items.get("items", [])
    found = [i for i in all_items if i["id"] == sid]
    if found:
        stock = Decimal(found[0]["current_stock"])
        print(f"  Stock integrity: expected=85, got={stock}")
        record("INTEGRITY", "Stock level after +100 -30 +15", 200,
               f"exp=85 got={stock}", "HANDLED" if stock == 85 else "VULNERABLE")


# ====================================================================
# REPORT
# ====================================================================
print("\n" + "=" * 60)
print("ROUND 2 RESULTS")
print("=" * 60)
handled = sum(1 for r in RESULTS if r[4] == "HANDLED")
crashed = sum(1 for r in RESULTS if r[4] == "CRASHED")
vuln = sum(1 for r in RESULTS if r[4] == "VULNERABLE")
print(f"  HANDLED:    {handled}")
print(f"  CRASHED:    {crashed}")
print(f"  VULNERABLE: {vuln}")
print(f"  Total:      {len(RESULTS)}")
print()

for cat, name, status, detail, verdict in RESULTS:
    if verdict != "HANDLED":
        print(f"  !! [{verdict}] {cat} / {name}: {status} -- {detail[:100]}")
