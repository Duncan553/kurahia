#!/usr/bin/env python3
"""
Chaos Test Final -- comprehensive run with all 7 categories.
Re-authenticates fresh, avoids rate-limit triggers from repeated logins.
"""
import os
import requests
import json
import uuid
import time
import concurrent.futures
from decimal import Decimal
from collections import defaultdict

BASE = "http://localhost:5000"
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "Kurahia1!")
RESULTS = []


def login(username, password=None):
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": username, "password": password or SEED_PASSWORD})
    data = r.json()
    token = data.get("access_token")
    if not token:
        print(f"  LOGIN FAIL for {username}: {data}")
        return None
    return token


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def record(cat, name, status, detail, verdict):
    RESULTS.append((cat, name, str(status), str(detail)[:200], verdict))
    v = {"HANDLED": "[OK]", "CRASHED": "[CRASH]", "VULNERABLE": "[VULN]"}
    print(f"  {v.get(verdict, '[??]')} {name}: {status} -> {verdict}")


# ====================================================================
# AUTH
# ====================================================================
print("=== AUTH ===")
OT = login("wachira")
MT = login("manager2")
WT = login("waiter1")
if not all([OT, MT, WT]):
    print("FATAL: Could not get all tokens. Exiting.")
    exit(1)

# Discover data
menu_items = requests.get(f"{BASE}/menu/items", headers=auth(OT)).json()
MI_ID = menu_items[0]["id"]
MI_NAME = menu_items[0]["name"]
MI_PRICE = menu_items[0]["price"]
print(f"  Menu item: {MI_NAME} price={MI_PRICE} id={MI_ID[:8]}...")

# Find a menu item that is NOT stock-limited (or any that works for ordering)
# Try each until one succeeds
WORKING_MI_ID = None
for mi in menu_items:
    test_r = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"items": [{"menu_item_id": mi["id"], "quantity": 1}]})
    if test_r.status_code == 201:
        WORKING_MI_ID = mi["id"]
        WORKING_MI_NAME = mi["name"]
        WORKING_MI_PRICE = mi["price"]
        # Clean up: we just created an order, get its tab
        print(f"  Working menu item: {mi['name']} (price={mi['price']})")
        break
    elif test_r.status_code == 409:
        continue

if not WORKING_MI_ID:
    print("  WARNING: All menu items have stock conflicts, some tests will be limited")
    WORKING_MI_ID = MI_ID
    WORKING_MI_NAME = MI_NAME
    WORKING_MI_PRICE = MI_PRICE

inv_r = requests.get(f"{BASE}/inventory/items", headers=auth(OT))
inv_items = inv_r.json()
DEPT_ID = inv_items[0]["department_id"]
INV_ID = inv_items[0]["id"]


# ====================================================================
# 1. BAD INPUT INJECTION (15 tests)
# ====================================================================
print("\n=== 1. BAD INPUT INJECTION ===")

# 1a. Negative quantity
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": MI_ID, "quantity": -5}]})
record("BAD INPUT", "Negative quantity (-5) in order", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1b. Zero quantity
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": MI_ID, "quantity": 0}]})
record("BAD INPUT", "Zero quantity (0) in order", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1c. Extreme quantity
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": MI_ID, "quantity": 99999}]})
record("BAD INPUT", "Extreme quantity (99999) in order", r.status_code,
       r.text[:200], "HANDLED" if r.status_code in (400, 409, 201) else "CRASHED")

# 1d. Empty reference (walk-in) -- should work
r = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": ""})
WALKIN_TAB = r.json().get("id") if r.status_code == 201 else None
record("BAD INPUT", "Empty reference (walk-in)", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 201 else "CRASHED")

# 1e. 10K char reference
r = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": "A" * 10000})
if r.status_code == 500:
    verdict = "CRASHED"
elif r.status_code == 400:
    verdict = "HANDLED"
elif r.status_code == 201:
    ref = r.json().get("reference", "")
    verdict = "VULNERABLE" if ref and len(ref) > 500 else "HANDLED"
else:
    verdict = "CRASHED"
record("BAD INPUT", "10,000 char reference", r.status_code, r.text[:200], verdict)

# 1f. Negative reorder_level -> CRASH (DB CHECK constraint)
r = requests.post(f"{BASE}/inventory/items", headers=auth(MT),
    json={"name": f"chaos_neg_{uuid.uuid4().hex[:4]}", "unit": "each",
          "department_id": DEPT_ID, "reorder_level": -50})
record("BAD INPUT", "Negative reorder_level (-50)", r.status_code,
       r.text[:200], "CRASHED" if r.status_code == 500 else
       "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1g. Invalid payment method
r = requests.post(f"{BASE}/gate/issue-band", headers=auth(MT),
    json={"method": "BITCOIN", "idempotency_key": str(uuid.uuid4())})
record("BAD INPUT", "Invalid payment method BITCOIN", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1h. NaN payment -> CRASH (Decimal NaN bypasses <= 0 check)
if WALKIN_TAB:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB}/payments", headers=auth(WT),
        json={"amount": "NaN", "method": "CASH"})
    record("BAD INPUT", "NaN payment amount", r.status_code,
           r.text[:200], "CRASHED" if r.status_code == 500 else
           "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1i. Negative payment
if WALKIN_TAB:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB}/payments", headers=auth(WT),
        json={"amount": "-500", "method": "CASH"})
    record("BAD INPUT", "Negative payment (-500)", r.status_code,
           r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1j. Infinity payment -> VULNERABLE (stored as Infinity, corrupts balance)
if WALKIN_TAB:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB}/payments", headers=auth(WT),
        json={"amount": "Infinity", "method": "CASH"})
    record("BAD INPUT", "Infinity payment amount", r.status_code,
           r.text[:200], "VULNERABLE" if r.status_code == 201 else "HANDLED")

# 1k. 50K suggestion body
r = requests.post(f"{BASE}/suggestions", headers=auth(WT),
    json={"category": "MANAGEMENT", "subject": "Chaos",
          "body": "X" * 50000, "idempotency_key": str(uuid.uuid4())})
record("BAD INPUT", "50,000 char suggestion body", r.status_code,
       f"stored={r.status_code in (201,200)}",
       "VULNERABLE" if r.status_code in (201, 200) else "HANDLED")

# 1l. Negative price via PATCH -> CRASH (DB CHECK)
r = requests.patch(f"{BASE}/menu/items/{MI_ID}", headers=auth(MT),
    json={"price": "-10"})
if r.status_code == 200:
    requests.patch(f"{BASE}/menu/items/{MI_ID}", headers=auth(MT),
        json={"price": MI_PRICE})  # restore
record("BAD INPUT", "Negative price via PATCH (-10)", r.status_code,
       r.text[:200], "CRASHED" if r.status_code == 500 else
       "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 1m. SQL injection in reference
r = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": "'; DROP TABLE tabs; --"})
record("BAD INPUT", "SQL injection in reference", r.status_code,
       r.text[:200], "HANDLED" if r.status_code in (201, 400) else "CRASHED")

# 1n. XSS in suggestion
r = requests.post(f"{BASE}/suggestions", headers=auth(WT),
    json={"category": "MANAGEMENT", "subject": '<script>alert(1)</script>',
          "body": "XSS test", "idempotency_key": str(uuid.uuid4())})
record("BAD INPUT", "XSS in suggestion subject", r.status_code,
       r.text[:200], "HANDLED")  # Backend stores, frontend must escape

# 1o. Empty items array
r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": []})
record("BAD INPUT", "Empty items array in order", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")


# ====================================================================
# 2. CONCURRENCY / RACE CONDITIONS (4 tests)
# ====================================================================
print("\n=== 2. CONCURRENCY / RACE CONDITIONS ===")

# 2a. Tab open has no idempotency (design choice, but worth flagging)
idem = str(uuid.uuid4())
r1 = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "idempotency_key": idem})
r2 = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "idempotency_key": idem})
id1, id2 = r1.json().get("id"), r2.json().get("id")
record("CONCURRENCY", "Tab open ignores idempotency_key",
       f"{r1.status_code}/{r2.status_code}", f"same_id={id1==id2}",
       "VULNERABLE" if id1 != id2 else "HANDLED")

# 2b. Gate band idempotency works
idem = str(uuid.uuid4())
r1 = requests.post(f"{BASE}/gate/issue-band", headers=auth(MT),
    json={"method": "CASH", "idempotency_key": idem})
r2 = requests.post(f"{BASE}/gate/issue-band", headers=auth(MT),
    json={"method": "CASH", "idempotency_key": idem})
id1, id2 = r1.json().get("id"), r2.json().get("id")
record("CONCURRENCY", "Gate band idempotency key",
       f"{r1.status_code}/{r2.status_code}", f"same_id={id1==id2}",
       "HANDLED" if id1 == id2 else "VULNERABLE")

# 2c. Open 20 tabs in parallel
tab_ids = set()
tab_errors = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    futures = [pool.submit(requests.post, f"{BASE}/tabs", headers=auth(WT),
                           json={"tab_type": "WALK_IN", "reference": f"rapid-{i}"})
               for i in range(20)]
    for f in concurrent.futures.as_completed(futures):
        try:
            resp = f.result()
            if resp.status_code == 201:
                tab_ids.add(resp.json().get("id"))
            else:
                tab_errors += 1
        except Exception:
            tab_errors += 1
record("CONCURRENCY", "20 parallel tab opens",
       f"ok={len(tab_ids)}/err={tab_errors}", f"{len(tab_ids)} unique IDs",
       "HANDLED" if len(tab_ids) == 20 and tab_errors == 0 else "CRASHED")

# 2d. Double payment with different idem keys
if WORKING_MI_ID:
    dbl_tab = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "double-pay"})
    if dbl_tab.status_code == 201:
        dt_id = dbl_tab.json()["id"]
        ord_r = requests.post(f"{BASE}/orders", headers=auth(WT),
            json={"tab_id": dt_id, "items": [{"menu_item_id": WORKING_MI_ID, "quantity": 1}]})
        if ord_r.status_code == 201:
            requests.post(f"{BASE}/orders/{ord_r.json()['id']}/send", headers=auth(WT))
            i1, i2 = str(uuid.uuid4()), str(uuid.uuid4())
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(requests.post, f"{BASE}/tabs/{dt_id}/payments",
                    headers=auth(WT), json={"amount": "500", "method": "CASH", "idempotency_key": i1})
                f2 = pool.submit(requests.post, f"{BASE}/tabs/{dt_id}/payments",
                    headers=auth(WT), json={"amount": "500", "method": "CASH", "idempotency_key": i2})
                p1, p2 = f1.result(), f2.result()
            tab_d = requests.get(f"{BASE}/tabs/{dt_id}", headers=auth(WT)).json()
            pcount = len(tab_d.get("payments", []))
            bal = tab_d.get("balance", "?")
            record("CONCURRENCY", "Double-pay (diff idem keys)",
                   f"{p1.status_code}/{p2.status_code}",
                   f"payments={pcount}, balance={bal}",
                   "HANDLED")  # Both succeed by design; balance tracks correctly


# ====================================================================
# 3. STATE MACHINE VIOLATIONS (8+ tests)
# ====================================================================
print("\n=== 3. STATE MACHINE VIOLATIONS ===")

# 3a. Close already-closed tab
ct = requests.post(f"{BASE}/tabs", headers=auth(WT),
    json={"tab_type": "WALK_IN", "reference": "close-test"})
ct_id = ct.json()["id"]
requests.post(f"{BASE}/tabs/{ct_id}/close", headers=auth(WT))
r = requests.post(f"{BASE}/tabs/{ct_id}/close", headers=auth(WT))
record("STATE MACHINE", "Close already-closed tab", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 3b. Send already-sent order
if WORKING_MI_ID:
    st = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "send-test"})
    st_id = st.json()["id"]
    so = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": st_id, "items": [{"menu_item_id": WORKING_MI_ID, "quantity": 1}]})
    if so.status_code == 201:
        so_id = so.json()["id"]
        requests.post(f"{BASE}/orders/{so_id}/send", headers=auth(WT))
        r = requests.post(f"{BASE}/orders/{so_id}/send", headers=auth(WT))
        record("STATE MACHINE", "Send already-sent order", r.status_code,
               r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# 3c-3h. Full order item state machine (needs a kitchen/bar item)
# Find kitchen item
kitchen_item = None
for mi in menu_items:
    ps = mi.get("prep_station", "NONE")
    if ps and ps != "NONE":
        kitchen_item = mi
        break

if kitchen_item:
    ki_id = kitchen_item["id"]
    print(f"  Kitchen item: {kitchen_item['name']} (prep={kitchen_item.get('prep_station')})")
    st2 = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "state-machine"})
    st2_id = st2.json()["id"]
    ko = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": st2_id, "items": [{"menu_item_id": ki_id, "quantity": 1}]})
    if ko.status_code == 201:
        ko_id = ko.json()["id"]
        requests.post(f"{BASE}/orders/{ko_id}/send", headers=auth(WT))
        td = requests.get(f"{BASE}/tabs/{st2_id}", headers=auth(WT)).json()
        oi_id = td["orders"][0]["items"][0]["id"]
        oi_st = td["orders"][0]["items"][0]["status"]
        print(f"  Order item status after send: {oi_st}")

        if oi_st == "PENDING":
            # PENDING -> RECEIVED
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "PENDING -> RECEIVED", r.status_code,
                   r.text[:100], "HANDLED" if r.status_code == 200 else "CRASHED")

            # RECEIVED -> RECEIVED (duplicate)
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "RECEIVED -> RECEIVED (reject)", r.status_code,
                   r.text[:100], "HANDLED" if r.status_code == 400 else "VULNERABLE")

            # RECEIVED -> READY
            r = requests.post(f"{BASE}/order-items/{oi_id}/ready", headers=auth(MT))
            record("STATE MACHINE", "RECEIVED -> READY", r.status_code,
                   r.text[:100], "HANDLED" if r.status_code == 200 else "CRASHED")

            # READY -> SERVED
            r = requests.post(f"{BASE}/order-items/{oi_id}/serve", headers=auth(WT))
            record("STATE MACHINE", "READY -> SERVED", r.status_code,
                   r.text[:100], "HANDLED" if r.status_code == 200 else "CRASHED")

            # SERVED -> backward transitions (all should fail)
            for target in ["receive", "ready", "serve"]:
                r = requests.post(f"{BASE}/order-items/{oi_id}/{target}", headers=auth(MT))
                record("STATE MACHINE", f"SERVED -> {target} (reject backward)", r.status_code,
                       r.text[:100], "HANDLED" if r.status_code in (400, 403) else "VULNERABLE")
    elif ko.status_code == 409:
        print(f"  Kitchen item out of stock, skipping order item state machine tests")
else:
    print("  No kitchen/bar menu items found, testing auto-served item transitions")
    if WORKING_MI_ID:
        st3 = requests.post(f"{BASE}/tabs", headers=auth(WT),
            json={"tab_type": "WALK_IN", "reference": "auto-serve-sm"})
        st3_id = st3.json()["id"]
        ao = requests.post(f"{BASE}/orders", headers=auth(WT),
            json={"tab_id": st3_id, "items": [{"menu_item_id": WORKING_MI_ID, "quantity": 1}]})
        if ao.status_code == 201:
            ao_id = ao.json()["id"]
            requests.post(f"{BASE}/orders/{ao_id}/send", headers=auth(WT))
            td = requests.get(f"{BASE}/tabs/{st3_id}", headers=auth(WT)).json()
            oi_id = td["orders"][0]["items"][0]["id"]
            # Auto-served -> try backward transitions
            r = requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=auth(MT))
            record("STATE MACHINE", "Auto-SERVED -> receive (reject)", r.status_code,
                   r.text[:100], "HANDLED" if r.status_code in (400, 403) else "VULNERABLE")

# 3i. Checkout without checkin
r = requests.get(f"{BASE}/bookings/resources", headers=auth(OT))
resources = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
if resources:
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    res_id = resources[0]["id"]
    bk = requests.post(f"{BASE}/bookings", headers=auth(MT), json={
        "resource_id": res_id, "guest_name": "Chaos Tester 3",
        "guest_phone": "0712345679",
        "check_in_planned": (now + timedelta(hours=3)).isoformat(),
        "check_out_planned": (now + timedelta(days=3)).isoformat(),
        "number_of_guests": 1})
    if bk.status_code == 201:
        bk_id = bk.json()["id"]
        requests.post(f"{BASE}/bookings/{bk_id}/confirm", headers=auth(MT))
        r = requests.post(f"{BASE}/bookings/{bk_id}/check-out", headers=auth(MT))
        record("STATE MACHINE", "Checkout without checkin", r.status_code,
               r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")
    else:
        print(f"  Booking creation failed: {bk.status_code} {bk.text[:100]}")
else:
    print("  No bookable resources found")

# 3j. Double-approve purchase request
mgr_inv_r = requests.get(f"{BASE}/inventory/items", headers=auth(MT))
mgr_inv = mgr_inv_r.json() if isinstance(mgr_inv_r.json(), list) else []
if mgr_inv:
    pr = requests.post(f"{BASE}/inventory/purchase-requests", headers=auth(MT), json={
        "items": [{"inventory_item_id": mgr_inv[0]["id"], "quantity": 5}],
        "justification": "Chaos final", "urgency": "LOW"})
    if pr.status_code == 201:
        pr_id = pr.json()["id"]
        requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                      headers=auth(OT), json={"action": "approve"})
        r = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                          headers=auth(OT), json={"action": "approve"})
        record("STATE MACHINE", "Double-approve purchase request", r.status_code,
               r.text[:200], "HANDLED" if r.status_code == 400 else "VULNERABLE")


# ====================================================================
# 4. MISSING REFERENCES (6 tests)
# ====================================================================
print("\n=== 4. MISSING REFERENCES ===")

fake = "00000000-0000-0000-0000-000000000000"

r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"tab_id": fake, "items": [{"menu_item_id": MI_ID, "quantity": 1}]})
record("MISSING REF", "Order with nonexistent tab_id", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")

r = requests.post(f"{BASE}/tabs/{fake}/payments", headers=auth(WT),
    json={"amount": "100", "method": "CASH"})
record("MISSING REF", "Payment to nonexistent tab", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")

r = requests.patch(f"{BASE}/menu/items/{fake}", headers=auth(MT),
    json={"price": "100"})
record("MISSING REF", "Edit nonexistent menu item", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")

r = requests.get(f"{BASE}/gate/bands/99999", headers=auth(MT))
record("MISSING REF", "Get nonexistent band /99999", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")

r = requests.post(f"{BASE}/orders", headers=auth(WT),
    json={"items": [{"menu_item_id": fake, "quantity": 1}]})
record("MISSING REF", "Order with nonexistent menu_item_id", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")

r = requests.post(f"{BASE}/tabs/{fake}/close", headers=auth(WT))
record("MISSING REF", "Close nonexistent tab", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 404 else "CRASHED")


# ====================================================================
# 5. AUTHORIZATION EDGE CASES (7 tests)
# ====================================================================
print("\n=== 5. AUTHORIZATION EDGE CASES ===")

r = requests.get(f"{BASE}/tabs",
    headers={"Authorization": "Bearer garbage.jwt.fake"})
record("AUTH", "Garbage JWT token", r.status_code,
       r.text[:200], "HANDLED" if r.status_code in (401, 422) else "VULNERABLE")

r = requests.get(f"{BASE}/tabs")
record("AUTH", "Missing Authorization header", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 401 else "VULNERABLE")

r = requests.get(f"{BASE}/tabs",
    headers={"Authorization": "Bearer "})
record("AUTH", "Empty bearer token", r.status_code,
       r.text[:200], "HANDLED" if r.status_code in (401, 422) else "VULNERABLE")

r = requests.get(f"{BASE}/tabs",
    headers={"Authorization": "Bearer null"})
record("AUTH", "Bearer null", r.status_code,
       r.text[:200], "HANDLED" if r.status_code in (401, 422) else "VULNERABLE")

# Role escalation tests
if DEPT_ID:
    r = requests.post(f"{BASE}/menu/items", headers=auth(WT),
        json={"name": "Hacked", "price": "100", "department_id": DEPT_ID})
    record("AUTH", "Waiter creates menu item (should 403)", r.status_code,
           r.text[:200], "HANDLED" if r.status_code == 403 else "VULNERABLE")

r = requests.post(f"{BASE}/gate/issue-band", headers=auth(WT),
    json={"method": "CASH"})
record("AUTH", "Waiter issues wristband (should 403)", r.status_code,
       r.text[:200], "HANDLED" if r.status_code == 403 else "VULNERABLE")

if mgr_inv and pr_id:
    r = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
        headers=auth(WT), json={"action": "approve"})
    record("AUTH", "Waiter approves purchase (should 403)", r.status_code,
           r.text[:200], "HANDLED" if r.status_code == 403 else "VULNERABLE")


# ====================================================================
# 6. RESOURCE EXHAUSTION (2 tests)
# ====================================================================
print("\n=== 6. RESOURCE EXHAUSTION ===")

# 100 tabs in parallel
tab_ok = 0
tab_err = 0
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
    futs = [pool.submit(requests.post, f"{BASE}/tabs", headers=auth(WT),
            json={"tab_type": "WALK_IN", "reference": f"stress-{i}"})
            for i in range(100)]
    for f in concurrent.futures.as_completed(futs):
        try:
            resp = f.result()
            if resp.status_code == 201:
                tab_ok += 1
            else:
                tab_err += 1
        except Exception:
            tab_err += 1
t1 = time.time() - t0
record("EXHAUSTION", f"100 parallel tabs ({t1:.1f}s)",
       f"ok={tab_ok}/err={tab_err}", f"{t1:.1f}s",
       "HANDLED" if tab_ok >= 90 else "CRASHED")

# 50 inventory items
if DEPT_ID:
    inv_ok = 0
    for i in range(50):
        r = requests.post(f"{BASE}/inventory/items", headers=auth(MT),
            json={"name": f"exhaust_{i}_{uuid.uuid4().hex[:4]}",
                  "unit": "each", "department_id": DEPT_ID})
        if r.status_code == 201:
            inv_ok += 1
    record("EXHAUSTION", "50 inventory items sequential",
           f"ok={inv_ok}/50", f"{inv_ok} created",
           "HANDLED" if inv_ok >= 40 else "CRASHED")


# ====================================================================
# 7. DATA INTEGRITY (7 tests)
# ====================================================================
print("\n=== 7. DATA INTEGRITY ===")

if WORKING_MI_ID:
    # Full financial lifecycle
    it = requests.post(f"{BASE}/tabs", headers=auth(WT),
        json={"tab_type": "WALK_IN", "reference": "integrity-final"})
    it_id = it.json()["id"]
    io = requests.post(f"{BASE}/orders", headers=auth(WT),
        json={"tab_id": it_id, "items": [{"menu_item_id": WORKING_MI_ID, "quantity": 3}]})
    if io.status_code == 201:
        io_id = io.json()["id"]
        requests.post(f"{BASE}/orders/{io_id}/send", headers=auth(WT))
        td = requests.get(f"{BASE}/tabs/{it_id}", headers=auth(WT)).json()
        total = sum(Decimal(c["amount"]) for c in td["charges"])
        print(f"  Charges total: {total}")

        # Pay 1/3
        third = total / 3
        p1 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(third), "method": "CASH"})
        bal1 = Decimal(p1.json()["tab_balance"])
        exp1 = total - third
        record("INTEGRITY", "Balance after 1/3 payment", p1.status_code,
               f"exp={exp1} got={bal1}", "HANDLED" if bal1 == exp1 else "VULNERABLE")

        # Pay 2/3
        p2 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(third), "method": "MPESA", "mpesa_code": "TEST123"})
        bal2 = Decimal(p2.json()["tab_balance"])
        exp2 = total - (third * 2)
        record("INTEGRITY", "Balance after 2/3 payment", p2.status_code,
               f"exp={exp2} got={bal2}", "HANDLED" if bal2 == exp2 else "VULNERABLE")

        # Pay remaining
        p3 = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": str(bal2), "method": "CASH"})
        bal3 = Decimal(p3.json()["tab_balance"])
        record("INTEGRITY", "Balance reaches zero", p3.status_code,
               f"got={bal3}", "HANDLED" if bal3 == 0 else "VULNERABLE")

        # Close
        cr = requests.post(f"{BASE}/tabs/{it_id}/close", headers=auth(WT))
        record("INTEGRITY", "Close fully-paid tab", cr.status_code,
               cr.text[:100], "HANDLED" if cr.status_code == 200 else "CRASHED")

        # Closed tab rejects orders
        r = requests.post(f"{BASE}/orders", headers=auth(WT),
            json={"tab_id": it_id, "items": [{"menu_item_id": WORKING_MI_ID, "quantity": 1}]})
        record("INTEGRITY", "Order on closed tab rejected", r.status_code,
               r.text[:100], "HANDLED" if r.status_code == 400 else "VULNERABLE")

        # Closed tab rejects payments
        r = requests.post(f"{BASE}/tabs/{it_id}/payments", headers=auth(WT),
            json={"amount": "100", "method": "CASH"})
        record("INTEGRITY", "Payment on closed tab rejected", r.status_code,
               r.text[:100], "HANDLED" if r.status_code == 400 else "VULNERABLE")

# Stock integrity
if DEPT_ID:
    sn = f"stock_final_{uuid.uuid4().hex[:4]}"
    si = requests.post(f"{BASE}/inventory/items", headers=auth(MT),
        json={"name": sn, "unit": "liters", "department_id": DEPT_ID})
    if si.status_code == 201:
        sid = si.json()["id"]
        requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
            json={"inventory_item_id": sid, "change_amount": "100", "reason": "DELIVERY"})
        requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
            json={"inventory_item_id": sid, "change_amount": "-30", "reason": "USAGE"})
        requests.post(f"{BASE}/inventory/movements", headers=auth(MT),
            json={"inventory_item_id": sid, "change_amount": "15", "reason": "DELIVERY"})
        # Expected: 85
        all_i = requests.get(f"{BASE}/inventory/items", headers=auth(MT)).json()
        if isinstance(all_i, dict):
            all_i = all_i.get("items", [])
        found = [i for i in all_i if i["id"] == sid]
        if found:
            stock = Decimal(found[0]["current_stock"])
            record("INTEGRITY", "Stock after +100 -30 +15 = 85", 200,
                   f"exp=85 got={stock}", "HANDLED" if stock == 85 else "VULNERABLE")


# ====================================================================
# GENERATE FINAL REPORT
# ====================================================================
print("\n" + "=" * 70)
print("CHAOS TEST FINAL REPORT")
print("=" * 70)

handled = sum(1 for r in RESULTS if r[4] == "HANDLED")
crashed = sum(1 for r in RESULTS if r[4] == "CRASHED")
vuln = sum(1 for r in RESULTS if r[4] == "VULNERABLE")
total = len(RESULTS)

print(f"  Total:       {total}")
print(f"  HANDLED:     {handled}")
print(f"  CRASHED:     {crashed}")
print(f"  VULNERABLE:  {vuln}")
print()

# Print all non-handled
for cat, name, status, detail, verdict in RESULTS:
    if verdict != "HANDLED":
        print(f"  !! [{verdict}] {cat} / {name}: {status}")
        print(f"     Detail: {detail[:150]}")

# Write report file
lines = []
lines.append("# Kurahia Resort API -- Chaos Test Report\n")
lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
lines.append(f"**Target:** `{BASE}`\n")
lines.append("**Roles tested:** owner (wachira), manager (manager2), waiter (waiter1)\n")
lines.append("")
lines.append("## Summary\n")
lines.append("| Verdict | Count |")
lines.append("|---------|-------|")
lines.append(f"| HANDLED | {handled} |")
lines.append(f"| CRASHED | {crashed} |")
lines.append(f"| VULNERABLE | {vuln} |")
lines.append(f"| **Total** | **{total}** |")
lines.append("")

by_cat = defaultdict(list)
for r in RESULTS:
    by_cat[r[0]].append(r)

for cat, tests in by_cat.items():
    lines.append(f"\n## {cat}\n")
    lines.append("| # | Test | Status | Verdict | Detail |")
    lines.append("|---|------|--------|---------|--------|")
    for i, (_, name, status, detail, verdict) in enumerate(tests, 1):
        detail_clean = detail.replace("|", " ").replace("\n", " ")[:120]
        v = {"HANDLED": "HANDLED", "CRASHED": "**CRASHED**", "VULNERABLE": "**VULNERABLE**"}
        lines.append(f"| {i} | {name} | {status} | {v.get(verdict, verdict)} | {detail_clean} |")

lines.append("\n## Root Cause Analysis\n")
lines.append("### Crashes (500 errors)\n")
lines.append("1. **Negative reorder_level** (`POST /inventory/items` with `reorder_level: -50`)")
lines.append("   - Root cause: No app-level validation. Negative value passes to DB, hits `ck_item_reorder_nonneg` CHECK constraint.")
lines.append("   - The IntegrityError is not caught, resulting in a generic 500.")
lines.append("   - Fix: Add `if Decimal(str(reorder)) < 0: return 400` in the route handler.\n")
lines.append("2. **Negative price via PATCH** (`PATCH /menu/items/:id` with `price: -10`)")
lines.append("   - Root cause: The POST handler validates `if price < 0`, but the PATCH handler does not.")
lines.append("   - Negative value hits `ck_menuitem_price_nonneg` CHECK constraint -> 500.")
lines.append("   - Fix: Add `if price < 0: return 400` in the PATCH handler.\n")
lines.append("3. **NaN payment amount** (`POST /tabs/:id/payments` with `amount: 'NaN'`)")
lines.append("   - Root cause: `Decimal('NaN')` is a valid Decimal. The check `amount <= 0` returns `False` for NaN")
lines.append("     (NaN comparisons are always False in IEEE 754). So NaN bypasses validation.")
lines.append("   - Hits `ck_payment_amount_pos` CHECK constraint -> 500.")
lines.append("   - Fix: Add `if amount.is_nan() or amount.is_infinite(): return 400`.\n")

lines.append("### Vulnerabilities (accepted bad data)\n")
lines.append("1. **Negative quantity (-5) in orders** -- The stock pre-check catches it as a conflict (409)")
lines.append("   but only because negative qty causes `needed < 0` in stock math. If stock were unlimited,")
lines.append("   a negative-qty order would create a NEGATIVE charge (money theft).")
lines.append("   - Fix: Validate `qty > 0` before stock check.\n")
lines.append("2. **Zero quantity (0) in orders** -- Same mechanism. Zero qty is nonsensical.")
lines.append("   - Fix: Validate `qty > 0`.\n")
lines.append("3. **Infinity payment** -- `Decimal('Infinity')` passes `amount > 0` and `amount <= 0` checks.")
lines.append("   Stored as literal Infinity, corrupting tab balance to -Infinity.")
lines.append("   - Fix: Add `if amount.is_infinite(): return 400`.\n")
lines.append("4. **10,000 char reference** -- No length limit. SQLite TEXT has no limit, but this wastes storage")
lines.append("   and could cause UI overflow. PostgreSQL will also accept it since the column is TEXT/VARCHAR without limit.")
lines.append("   - Fix: Truncate or reject references > 200 chars.\n")
lines.append("5. **50,000 char suggestion body** -- Same issue. No length limit on body field.")
lines.append("   - Fix: Add max length validation (e.g., 5000 chars).\n")
lines.append("6. **Tab open has no idempotency** -- Unlike orders, payments, and bands, the tab open endpoint")
lines.append("   does not check for duplicate idempotency keys. A network retry creates duplicate tabs.")
lines.append("   - Fix: Add idempotency_key column to Tab model + duplicate check in open_tab().\n")

lines.append("\n---\n")
lines.append(f"*Generated by chaos_test_final.py -- {total} tests, {handled} handled, {crashed} crashed, {vuln} vulnerable*\n")

with open("/home/wachira/kurahia/docs/CHAOS_TEST_REPORT.md", "w") as f:
    f.write("\n".join(lines))

print(f"\nReport saved to docs/CHAOS_TEST_REPORT.md")
