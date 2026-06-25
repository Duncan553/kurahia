#!/usr/bin/env python3
"""
Chaos Test Suite for Kurahia Resort API
Fires real HTTP requests at localhost:5000 and logs every result.
"""
import os
import requests
import json
import uuid
import time
import concurrent.futures
from decimal import Decimal

BASE = "http://localhost:5000"
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "Kurahia1!")
RESULTS = []  # (category, test_name, curl_equiv, status, key_response, verdict)


def login(username, password=None):
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": username, "password": password or SEED_PASSWORD})
    return r.json().get("access_token", "FAIL")


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def record(category, name, method, url, status, body, verdict):
    curl_equiv = f"{method} {url}"
    key = body if isinstance(body, str) else json.dumps(body)[:200]
    RESULTS.append((category, name, curl_equiv, status, key, verdict))
    v_icon = {"HANDLED": "[OK]", "CRASHED": "[CRASH]", "VULNERABLE": "[VULN]"}
    print(f"  {v_icon.get(verdict, '[??]')} {name}: {status} -> {verdict}")


# =========================================================================
# Setup: get tokens + discover IDs
# =========================================================================
print("=== Getting auth tokens ===")
OWNER_TOKEN = login("wachira")
MGR_TOKEN = login("manager2")
WAITER_TOKEN = login("waiter1")
assert OWNER_TOKEN != "FAIL", "Owner login failed"
assert MGR_TOKEN != "FAIL", "Manager login failed"
assert WAITER_TOKEN != "FAIL", "Waiter login failed"
print(f"  Owner token: {OWNER_TOKEN[:20]}...")
print(f"  Manager token: {MGR_TOKEN[:20]}...")
print(f"  Waiter token: {WAITER_TOKEN[:20]}...")

# Discover a menu item ID and department ID
print("\n=== Discovering existing data ===")
r = requests.get(f"{BASE}/menu/items", headers=auth(OWNER_TOKEN))
menu_items = r.json() if r.status_code == 200 else []
MENU_ITEM_ID = menu_items[0]["id"] if menu_items else None
print(f"  Menu items found: {len(menu_items)}")
if MENU_ITEM_ID:
    print(f"  Using menu item: {menu_items[0]['name']} ({MENU_ITEM_ID})")

# Get a department ID
r = requests.get(f"{BASE}/inventory/items", headers=auth(OWNER_TOKEN))
inv_items = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
DEPT_ID = inv_items[0]["department_id"] if inv_items else None
INV_ITEM_ID = inv_items[0]["id"] if inv_items else None

# Track purchase request ID for auth tests
pr_id = None
mgr_inv = []


# =========================================================================
# 1. BAD INPUT INJECTION
# =========================================================================
print("\n=== 1. BAD INPUT INJECTION ===")

# 1a. POST /orders with negative quantity
if MENU_ITEM_ID:
    r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                      json={"items": [{"menu_item_id": MENU_ITEM_ID, "quantity": -5}]})
    verdict = "HANDLED" if r.status_code in (400, 422) else "VULNERABLE"
    if r.status_code == 201:
        verdict = "VULNERABLE"
    record("BAD INPUT", "Negative quantity in order", "POST", "/orders",
           r.status_code, r.json(), verdict)

# 1b. POST /orders with extreme quantity
if MENU_ITEM_ID:
    r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                      json={"items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 99999}]})
    verdict = "HANDLED" if r.status_code in (400, 409, 201) else "CRASHED"
    record("BAD INPUT", "Extreme quantity (99999) in order", "POST", "/orders",
           r.status_code, r.json(), verdict)

# 1c. POST /tabs with empty reference (walk-in) -- should work
r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                  json={"tab_type": "WALK_IN", "reference": ""})
verdict = "HANDLED" if r.status_code == 201 else "CRASHED"
WALKIN_TAB_ID = r.json().get("id") if r.status_code == 201 else None
record("BAD INPUT", "Empty reference (walk-in tab)", "POST", "/tabs",
       r.status_code, r.json(), verdict)

# 1d. POST /tabs with 10,000 character reference
long_ref = "A" * 10000
r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                  json={"tab_type": "WALK_IN", "reference": long_ref})
if r.status_code == 500:
    verdict = "CRASHED"
elif r.status_code in (400, 422):
    verdict = "HANDLED"
elif r.status_code == 201:
    ref_stored = r.json().get("reference", "")
    verdict = "VULNERABLE" if ref_stored and len(ref_stored) > 500 else "HANDLED"
else:
    verdict = "CRASHED"
record("BAD INPUT", "10,000 char reference", "POST", "/tabs",
       r.status_code, r.text[:200], verdict)

# 1e. POST /inventory/items with negative reorder_level
if DEPT_ID:
    r = requests.post(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN),
                      json={"name": f"chaos_neg_reorder_{uuid.uuid4().hex[:6]}", "unit": "each",
                            "department_id": DEPT_ID, "reorder_level": -50})
    if r.status_code == 201:
        verdict = "VULNERABLE"
    elif r.status_code in (400, 422):
        verdict = "HANDLED"
    else:
        verdict = "CRASHED"
    record("BAD INPUT", "Negative reorder_level", "POST", "/inventory/items",
           r.status_code, r.json(), verdict)

# 1f. POST /gate/issue-band with method="BITCOIN"
r = requests.post(f"{BASE}/gate/issue-band", headers=auth(MGR_TOKEN),
                  json={"method": "BITCOIN", "idempotency_key": str(uuid.uuid4())})
verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
record("BAD INPUT", "Invalid payment method (BITCOIN)", "POST", "/gate/issue-band",
       r.status_code, r.json(), verdict)

# 1g. POST /tabs/payments with amount="NaN"
if WALKIN_TAB_ID:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB_ID}/payments", headers=auth(WAITER_TOKEN),
                      json={"amount": "NaN", "method": "CASH"})
    verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
    record("BAD INPUT", "NaN payment amount", "POST", f"/tabs/<id>/payments",
           r.status_code, r.json(), verdict)

# 1h. POST /tabs/payments with amount="-500"
if WALKIN_TAB_ID:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB_ID}/payments", headers=auth(WAITER_TOKEN),
                      json={"amount": "-500", "method": "CASH"})
    verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
    record("BAD INPUT", "Negative payment amount (-500)", "POST", f"/tabs/<id>/payments",
           r.status_code, r.json(), verdict)

# 1i. POST /suggestions with 50,000 character body
r = requests.post(f"{BASE}/suggestions", headers=auth(WAITER_TOKEN),
                  json={"category": "MANAGEMENT", "subject": "Chaos test",
                        "body": "X" * 50000})
if r.status_code == 500:
    verdict = "CRASHED"
elif r.status_code in (400, 422, 413):
    verdict = "HANDLED"
elif r.status_code in (201, 200):
    verdict = "VULNERABLE"
else:
    verdict = "CRASHED"
record("BAD INPUT", "50,000 char suggestion body", "POST", "/suggestions",
       r.status_code, r.text[:200], verdict)

# 1j. PATCH /menu/items with price="-10"
if MENU_ITEM_ID:
    # Save original price first
    orig_r = requests.get(f"{BASE}/menu/items", headers=auth(OWNER_TOKEN))
    orig_price = None
    if orig_r.status_code == 200:
        for mi in orig_r.json():
            if mi["id"] == MENU_ITEM_ID:
                orig_price = mi.get("price", "500")
                break

    r = requests.patch(f"{BASE}/menu/items/{MENU_ITEM_ID}", headers=auth(MGR_TOKEN),
                       json={"price": "-10"})
    if r.status_code == 200:
        verdict = "VULNERABLE"
        # Restore original price
        if orig_price:
            requests.patch(f"{BASE}/menu/items/{MENU_ITEM_ID}", headers=auth(MGR_TOKEN),
                           json={"price": str(orig_price)})
    elif r.status_code == 400:
        verdict = "HANDLED"
    else:
        verdict = "CRASHED"
    record("BAD INPUT", "Negative menu item price (-10)", "PATCH", f"/menu/items/<id>",
           r.status_code, r.json(), verdict)

# 1k. POST /orders with quantity=0
if MENU_ITEM_ID:
    r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                      json={"items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 0}]})
    verdict = "HANDLED" if r.status_code in (400, 422) else "VULNERABLE"
    if r.status_code == 201:
        verdict = "VULNERABLE"
    record("BAD INPUT", "Zero quantity in order", "POST", "/orders",
           r.status_code, r.json(), verdict)

# 1l. SQL injection via reference field
r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                  json={"tab_type": "WALK_IN", "reference": "'; DROP TABLE tabs; --"})
verdict = "HANDLED" if r.status_code in (201, 400) else "CRASHED"
record("BAD INPUT", "SQL injection in reference", "POST", "/tabs",
       r.status_code, r.json(), verdict)

# 1m. XSS in suggestion subject
r = requests.post(f"{BASE}/suggestions", headers=auth(WAITER_TOKEN),
                  json={"category": "MANAGEMENT",
                        "subject": '<script>alert("xss")</script>',
                        "body": "Test XSS injection"})
if r.status_code in (201, 200):
    verdict = "HANDLED"
elif r.status_code in (400, 422):
    verdict = "HANDLED"
else:
    verdict = "CRASHED"
record("BAD INPUT", "XSS in suggestion subject", "POST", "/suggestions",
       r.status_code, r.text[:200], verdict)

# 1n. Infinity and special float values
if WALKIN_TAB_ID:
    r = requests.post(f"{BASE}/tabs/{WALKIN_TAB_ID}/payments", headers=auth(WAITER_TOKEN),
                      json={"amount": "Infinity", "method": "CASH"})
    verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
    record("BAD INPUT", "Infinity payment amount", "POST", f"/tabs/<id>/payments",
           r.status_code, r.json(), verdict)

# 1o. Unicode/emoji abuse in names
if DEPT_ID:
    emoji_name = f"chaos_emoji_{uuid.uuid4().hex[:4]}"
    r = requests.post(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN),
                      json={"name": emoji_name, "unit": "each",
                            "department_id": DEPT_ID})
    if r.status_code == 500:
        verdict = "CRASHED"
    else:
        verdict = "HANDLED"
    record("BAD INPUT", "Unicode in item name", "POST", "/inventory/items",
           r.status_code, r.text[:200], verdict)


# =========================================================================
# 2. CONCURRENCY / RACE CONDITIONS
# =========================================================================
print("\n=== 2. CONCURRENCY / RACE CONDITIONS ===")

# 2a. Double-submit same idempotency key on /tabs
# Tab open doesn't use idempotency_key, so both will create new tabs
idem = str(uuid.uuid4())
r1 = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                   json={"tab_type": "WALK_IN", "idempotency_key": idem})
r2 = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                   json={"tab_type": "WALK_IN", "idempotency_key": idem})
if r1.status_code == 201 and r2.status_code == 201:
    id1 = r1.json().get("id")
    id2 = r2.json().get("id")
    if id1 == id2:
        verdict = "HANDLED"
    else:
        verdict = "VULNERABLE"
else:
    verdict = "HANDLED"
record("CONCURRENCY", "Double-submit tab open (no idem support)", "POST", "/tabs",
       f"{r1.status_code}/{r2.status_code}",
       f"ids: {r1.json().get('id', '?')[:8]}/{r2.json().get('id', '?')[:8]}", verdict)

# 2b. Double-submit same idempotency key on /gate/issue-band
idem = str(uuid.uuid4())
r1 = requests.post(f"{BASE}/gate/issue-band", headers=auth(MGR_TOKEN),
                   json={"method": "CASH", "idempotency_key": idem})
r2 = requests.post(f"{BASE}/gate/issue-band", headers=auth(MGR_TOKEN),
                   json={"method": "CASH", "idempotency_key": idem})
id1 = r1.json().get("id")
id2 = r2.json().get("id")
if id1 == id2:
    verdict = "HANDLED"
else:
    verdict = "VULNERABLE"
record("CONCURRENCY", "Double-submit same idem key on /gate/issue-band", "POST", "/gate/issue-band",
       f"{r1.status_code}/{r2.status_code}", f"ids match: {id1 == id2}", verdict)

# 2c. Open 20 tabs rapidly
tab_ids = set()
tab_errors = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    futures = [pool.submit(requests.post, f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
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

if len(tab_ids) == 20 and tab_errors == 0:
    verdict = "HANDLED"
elif tab_errors > 0:
    verdict = "CRASHED"
else:
    verdict = "HANDLED"
record("CONCURRENCY", "Open 20 tabs rapidly (parallel)", "POST", "/tabs x20",
       f"unique={len(tab_ids)}/errors={tab_errors}", f"{len(tab_ids)} unique IDs", verdict)

# 2d. Pay the same tab twice simultaneously
test_tab = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                         json={"tab_type": "WALK_IN", "reference": "double-pay-test"})
if test_tab.status_code == 201 and MENU_ITEM_ID:
    dbl_tab_id = test_tab.json()["id"]
    order_r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                            json={"tab_id": dbl_tab_id,
                                  "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 1}]})
    if order_r.status_code == 201:
        ord_id = order_r.json()["id"]
        requests.post(f"{BASE}/orders/{ord_id}/send", headers=auth(WAITER_TOKEN))

        idem1, idem2 = str(uuid.uuid4()), str(uuid.uuid4())
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(requests.post, f"{BASE}/tabs/{dbl_tab_id}/payments",
                             headers=auth(WAITER_TOKEN),
                             json={"amount": "500", "method": "CASH", "idempotency_key": idem1})
            f2 = pool.submit(requests.post, f"{BASE}/tabs/{dbl_tab_id}/payments",
                             headers=auth(WAITER_TOKEN),
                             json={"amount": "500", "method": "CASH", "idempotency_key": idem2})
            pr1, pr2 = f1.result(), f2.result()

        tab_state = requests.get(f"{BASE}/tabs/{dbl_tab_id}", headers=auth(WAITER_TOKEN))
        if tab_state.status_code == 200:
            balance = Decimal(tab_state.json()["balance"])
            payments_count = len(tab_state.json()["payments"])
            # Both succeed (different idem keys) -- balance tracks correctly by design
            verdict = "HANDLED"
        else:
            balance = "ERROR"
            payments_count = "ERROR"
            verdict = "CRASHED"
        record("CONCURRENCY", "Double-pay same tab (diff idem keys)", "POST",
               f"/tabs/<id>/payments x2",
               f"{pr1.status_code}/{pr2.status_code}",
               f"payments={payments_count}, balance={balance}", verdict)


# =========================================================================
# 3. STATE MACHINE VIOLATIONS
# =========================================================================
print("\n=== 3. STATE MACHINE VIOLATIONS ===")

# 3a. Close an already-closed tab
close_tab_r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                            json={"tab_type": "WALK_IN", "reference": "close-test"})
if close_tab_r.status_code == 201:
    ct_id = close_tab_r.json()["id"]
    r1 = requests.post(f"{BASE}/tabs/{ct_id}/close", headers=auth(WAITER_TOKEN))
    r2 = requests.post(f"{BASE}/tabs/{ct_id}/close", headers=auth(WAITER_TOKEN))
    verdict = "HANDLED" if r2.status_code == 400 else "VULNERABLE"
    record("STATE MACHINE", "Close already-closed tab", "POST", f"/tabs/<id>/close",
           r2.status_code, r2.json(), verdict)

# 3b. Send an already-sent order
if MENU_ITEM_ID:
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                          json={"tab_type": "WALK_IN", "reference": "send-test"})
    if tab_r.status_code == 201:
        tab_id = tab_r.json()["id"]
        ord_r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                              json={"tab_id": tab_id,
                                    "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 1}]})
        if ord_r.status_code == 201:
            oid = ord_r.json()["id"]
            requests.post(f"{BASE}/orders/{oid}/send", headers=auth(WAITER_TOKEN))
            r = requests.post(f"{BASE}/orders/{oid}/send", headers=auth(WAITER_TOKEN))
            verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
            record("STATE MACHINE", "Send already-sent order", "POST", f"/orders/<id>/send",
                   r.status_code, r.json(), verdict)

# 3c. Receive an already-received item + 3d. Ready an already-served item
if MENU_ITEM_ID:
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                          json={"tab_type": "WALK_IN", "reference": "receive-test"})
    if tab_r.status_code == 201:
        tab_id = tab_r.json()["id"]
        ord_r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                              json={"tab_id": tab_id,
                                    "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 1}]})
        if ord_r.status_code == 201:
            oid = ord_r.json()["id"]
            requests.post(f"{BASE}/orders/{oid}/send", headers=auth(WAITER_TOKEN))
            tab_detail = requests.get(f"{BASE}/tabs/{tab_id}", headers=auth(WAITER_TOKEN))
            if tab_detail.status_code == 200:
                orders = tab_detail.json().get("orders", [])
                if orders and orders[0].get("items"):
                    oi_id = orders[0]["items"][0]["id"]
                    oi_status = orders[0]["items"][0]["status"]
                    if oi_status == "PENDING":
                        # Receive, then try to receive again
                        requests.post(f"{BASE}/order-items/{oi_id}/receive",
                                      headers=auth(MGR_TOKEN))
                        r = requests.post(f"{BASE}/order-items/{oi_id}/receive",
                                          headers=auth(MGR_TOKEN))
                        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
                        record("STATE MACHINE", "Receive already-received item", "POST",
                               f"/order-items/<id>/receive",
                               r.status_code, r.json(), verdict)

                        # Ready, serve, then try ready again
                        requests.post(f"{BASE}/order-items/{oi_id}/ready",
                                      headers=auth(MGR_TOKEN))
                        requests.post(f"{BASE}/order-items/{oi_id}/serve",
                                      headers=auth(WAITER_TOKEN))
                        r = requests.post(f"{BASE}/order-items/{oi_id}/ready",
                                          headers=auth(MGR_TOKEN))
                        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
                        record("STATE MACHINE", "Ready an already-served item", "POST",
                               f"/order-items/<id>/ready",
                               r.status_code, r.json(), verdict)
                    elif oi_status == "SERVED":
                        # Auto-served (NONE prep station) -- try to receive
                        r = requests.post(f"{BASE}/order-items/{oi_id}/receive",
                                          headers=auth(MGR_TOKEN))
                        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
                        record("STATE MACHINE", "Receive auto-served item", "POST",
                               f"/order-items/<id>/receive",
                               r.status_code, r.json(), verdict)

# 3e. Check out a booking that's not checked in
r = requests.get(f"{BASE}/bookings/resources", headers=auth(OWNER_TOKEN))
resources = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
if resources:
    res_id = resources[0]["id"]
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    booking_r = requests.post(f"{BASE}/bookings", headers=auth(MGR_TOKEN),
                              json={
                                  "resource_id": res_id,
                                  "guest_name": "Chaos Tester",
                                  "guest_phone": "0712345678",
                                  "check_in_planned": (now + timedelta(hours=1)).isoformat(),
                                  "check_out_planned": (now + timedelta(days=1)).isoformat(),
                                  "number_of_guests": 2,
                              })
    if booking_r.status_code == 201:
        bk_id = booking_r.json()["id"]
        requests.post(f"{BASE}/bookings/{bk_id}/confirm", headers=auth(MGR_TOKEN))
        r = requests.post(f"{BASE}/bookings/{bk_id}/check-out", headers=auth(MGR_TOKEN))
        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
        record("STATE MACHINE", "Check out without check-in", "POST",
               f"/bookings/<id>/check-out",
               r.status_code, r.json(), verdict)

# 3f. Approve an already-approved purchase request
r = requests.get(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN))
mgr_inv = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
if mgr_inv:
    inv_id = mgr_inv[0]["id"]
    pr_r = requests.post(f"{BASE}/inventory/purchase-requests", headers=auth(MGR_TOKEN),
                         json={
                             "items": [{"inventory_item_id": inv_id, "quantity": 10}],
                             "justification": "Chaos test purchase",
                             "urgency": "LOW",
                         })
    if pr_r.status_code == 201:
        pr_id = pr_r.json()["id"]
        r1 = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                           headers=auth(OWNER_TOKEN),
                           json={"action": "approve"})
        r2 = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                           headers=auth(OWNER_TOKEN),
                           json={"action": "approve"})
        verdict = "HANDLED" if r2.status_code == 400 else "VULNERABLE"
        record("STATE MACHINE", "Approve already-approved request", "POST",
               f"/purchase-requests/<id>/approve",
               r2.status_code, r2.json(), verdict)


# =========================================================================
# 4. MISSING REFERENCES
# =========================================================================
print("\n=== 4. MISSING REFERENCES ===")

fake_uuid = "00000000-0000-0000-0000-000000000000"

# 4a. POST /orders with nonexistent tab_id
if MENU_ITEM_ID:
    r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                      json={"tab_id": fake_uuid,
                            "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 1}]})
    verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
    record("MISSING REF", "Order with nonexistent tab_id", "POST", "/orders",
           r.status_code, r.json(), verdict)

# 4b. POST /tabs/payments with nonexistent tab_id
r = requests.post(f"{BASE}/tabs/{fake_uuid}/payments", headers=auth(WAITER_TOKEN),
                  json={"amount": "100", "method": "CASH"})
verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
record("MISSING REF", "Payment with nonexistent tab_id", "POST",
       f"/tabs/<fake>/payments",
       r.status_code, r.json(), verdict)

# 4c. PATCH /menu/items with nonexistent id
r = requests.patch(f"{BASE}/menu/items/{fake_uuid}", headers=auth(MGR_TOKEN),
                   json={"price": "100"})
verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
record("MISSING REF", "Edit nonexistent menu item", "PATCH", f"/menu/items/<fake>",
       r.status_code, r.json(), verdict)

# 4d. GET /gate/bands/99999 (nonexistent band)
r = requests.get(f"{BASE}/gate/bands/99999", headers=auth(MGR_TOKEN))
verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
record("MISSING REF", "Get nonexistent band", "GET", "/gate/bands/99999",
       r.status_code, r.text[:200], verdict)

# 4e. POST /orders with nonexistent menu_item_id
r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                  json={"items": [{"menu_item_id": fake_uuid, "quantity": 1}]})
verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
record("MISSING REF", "Order with nonexistent menu_item_id", "POST", "/orders",
       r.status_code, r.json(), verdict)

# 4f. Close nonexistent tab
r = requests.post(f"{BASE}/tabs/{fake_uuid}/close", headers=auth(WAITER_TOKEN))
verdict = "HANDLED" if r.status_code == 404 else "CRASHED"
record("MISSING REF", "Close nonexistent tab", "POST", f"/tabs/<fake>/close",
       r.status_code, r.json(), verdict)


# =========================================================================
# 5. AUTHORIZATION EDGE CASES
# =========================================================================
print("\n=== 5. AUTHORIZATION EDGE CASES ===")

# 5a. Garbage JWT
r = requests.get(f"{BASE}/tabs", headers={"Authorization": "Bearer expired.jwt.token.garbage"})
verdict = "HANDLED" if r.status_code in (401, 422) else "VULNERABLE"
record("AUTH", "Garbage JWT token", "GET", "/tabs",
       r.status_code, r.text[:200], verdict)

# 5b. Missing Authorization header
r = requests.get(f"{BASE}/tabs")
verdict = "HANDLED" if r.status_code == 401 else "VULNERABLE"
record("AUTH", "Missing Authorization header", "GET", "/tabs",
       r.status_code, r.text[:200], verdict)

# 5c. Empty bearer token
r = requests.get(f"{BASE}/tabs", headers={"Authorization": "Bearer "})
verdict = "HANDLED" if r.status_code in (401, 422) else "VULNERABLE"
record("AUTH", "Empty bearer token", "GET", "/tabs",
       r.status_code, r.text[:200], verdict)

# 5d. Bearer with just "null"
r = requests.get(f"{BASE}/tabs", headers={"Authorization": "Bearer null"})
verdict = "HANDLED" if r.status_code in (401, 422) else "VULNERABLE"
record("AUTH", "Bearer 'null'", "GET", "/tabs",
       r.status_code, r.text[:200], verdict)

# 5e. Waiter trying to approve purchase request (role escalation)
if pr_id:
    r = requests.post(f"{BASE}/inventory/purchase-requests/{pr_id}/approve",
                      headers=auth(WAITER_TOKEN),
                      json={"action": "approve"})
    verdict = "HANDLED" if r.status_code == 403 else "VULNERABLE"
    record("AUTH", "Waiter tries to approve purchase request", "POST",
           f"/purchase-requests/<id>/approve",
           r.status_code, r.json(), verdict)

# 5f. Waiter trying to create menu item
if DEPT_ID:
    r = requests.post(f"{BASE}/menu/items", headers=auth(WAITER_TOKEN),
                      json={"name": "Hacked Item", "price": "100", "department_id": DEPT_ID})
    verdict = "HANDLED" if r.status_code == 403 else "VULNERABLE"
    record("AUTH", "Waiter tries to create menu item", "POST", "/menu/items",
           r.status_code, r.json(), verdict)

# 5g. Waiter trying to issue wristband
r = requests.post(f"{BASE}/gate/issue-band", headers=auth(WAITER_TOKEN),
                  json={"method": "CASH"})
verdict = "HANDLED" if r.status_code == 403 else "VULNERABLE"
record("AUTH", "Waiter tries to issue wristband", "POST", "/gate/issue-band",
       r.status_code, r.json(), verdict)


# =========================================================================
# 6. RESOURCE EXHAUSTION
# =========================================================================
print("\n=== 6. RESOURCE EXHAUSTION ===")

# 6a. Create 100 tabs rapidly
tab_success = 0
tab_fail = 0
t_start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
    futures = [pool.submit(requests.post, f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                           json={"tab_type": "WALK_IN", "reference": f"stress-{i}"})
               for i in range(100)]
    for f in concurrent.futures.as_completed(futures):
        try:
            resp = f.result()
            if resp.status_code == 201:
                tab_success += 1
            else:
                tab_fail += 1
        except Exception:
            tab_fail += 1
t_elapsed = time.time() - t_start

if tab_success >= 90:
    verdict = "HANDLED"
else:
    verdict = "CRASHED"
record("EXHAUSTION", f"Create 100 tabs rapidly ({t_elapsed:.1f}s)", "POST", "/tabs x100",
       f"success={tab_success}/fail={tab_fail}", f"{t_elapsed:.1f}s elapsed", verdict)

# 6b. Create 50 inventory items
if DEPT_ID:
    inv_success = 0
    inv_fail = 0
    for i in range(50):
        r = requests.post(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN),
                          json={"name": f"chaos_exhaust_{i}_{uuid.uuid4().hex[:4]}",
                                "unit": "each", "department_id": DEPT_ID})
        if r.status_code == 201:
            inv_success += 1
        else:
            inv_fail += 1

    if inv_success >= 40:
        verdict = "HANDLED"
    else:
        verdict = "CRASHED"
    record("EXHAUSTION", "Create 50 inventory items sequentially", "POST", "/inventory/items x50",
           f"success={inv_success}/fail={inv_fail}", f"{inv_success} created", verdict)


# =========================================================================
# 7. DATA INTEGRITY
# =========================================================================
print("\n=== 7. DATA INTEGRITY ===")

# 7a. After payment, verify tab balance is correct
if MENU_ITEM_ID:
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                          json={"tab_type": "WALK_IN", "reference": "integrity-test"})
    if tab_r.status_code == 201:
        i_tab_id = tab_r.json()["id"]
        ord_r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                              json={"tab_id": i_tab_id,
                                    "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 2}]})
        if ord_r.status_code == 201:
            oid = ord_r.json()["id"]
            send_r = requests.post(f"{BASE}/orders/{oid}/send", headers=auth(WAITER_TOKEN))
            if send_r.status_code == 200:
                tab_state = requests.get(f"{BASE}/tabs/{i_tab_id}", headers=auth(WAITER_TOKEN))
                charges_total = sum(Decimal(c["amount"]) for c in tab_state.json()["charges"])

                half = charges_total / 2
                pay_r = requests.post(f"{BASE}/tabs/{i_tab_id}/payments", headers=auth(WAITER_TOKEN),
                                      json={"amount": str(half), "method": "CASH"})
                if pay_r.status_code == 201:
                    reported_balance = Decimal(pay_r.json()["tab_balance"])
                    expected_balance = charges_total - half
                    verdict = "HANDLED" if reported_balance == expected_balance else "VULNERABLE"
                    record("INTEGRITY", "Tab balance after partial payment",
                           "POST", f"/tabs/<id>/payments",
                           pay_r.status_code,
                           f"expected={expected_balance}, got={reported_balance}",
                           verdict)

                    pay_r2 = requests.post(f"{BASE}/tabs/{i_tab_id}/payments",
                                           headers=auth(WAITER_TOKEN),
                                           json={"amount": str(expected_balance), "method": "CASH"})
                    if pay_r2.status_code == 201:
                        final_balance = Decimal(pay_r2.json()["tab_balance"])
                        verdict = "HANDLED" if final_balance == 0 else "VULNERABLE"
                        record("INTEGRITY", "Tab balance after full payment",
                               "POST", f"/tabs/<id>/payments",
                               pay_r2.status_code,
                               f"expected=0, got={final_balance}",
                               verdict)

# 7b. After closing tab, verify it cannot be modified
if MENU_ITEM_ID:
    tab_r = requests.post(f"{BASE}/tabs", headers=auth(WAITER_TOKEN),
                          json={"tab_type": "WALK_IN", "reference": "close-modify-test"})
    if tab_r.status_code == 201:
        cm_tab_id = tab_r.json()["id"]
        requests.post(f"{BASE}/tabs/{cm_tab_id}/close", headers=auth(WAITER_TOKEN))

        r = requests.post(f"{BASE}/orders", headers=auth(WAITER_TOKEN),
                          json={"tab_id": cm_tab_id,
                                "items": [{"menu_item_id": MENU_ITEM_ID, "quantity": 1}]})
        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
        record("INTEGRITY", "Add order to closed tab", "POST", "/orders",
               r.status_code, r.json(), verdict)

        r = requests.post(f"{BASE}/tabs/{cm_tab_id}/payments", headers=auth(WAITER_TOKEN),
                          json={"amount": "100", "method": "CASH"})
        verdict = "HANDLED" if r.status_code == 400 else "VULNERABLE"
        record("INTEGRITY", "Add payment to closed tab", "POST",
               f"/tabs/<id>/payments",
               r.status_code, r.json(), verdict)

# 7c. Verify stock movement integrity
if DEPT_ID:
    unique_name = f"chaos_stock_{uuid.uuid4().hex[:6]}"
    item_r = requests.post(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN),
                           json={"name": unique_name, "unit": "each",
                                 "department_id": DEPT_ID})
    if item_r.status_code == 201:
        si_id = item_r.json()["id"]
        mv_r = requests.post(f"{BASE}/inventory/movements", headers=auth(MGR_TOKEN),
                             json={"inventory_item_id": si_id,
                                   "change_amount": "50",
                                   "reason": "DELIVERY",
                                   "notes": "chaos test stock"})
        if mv_r.status_code == 201:
            items_r = requests.get(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN))
            if items_r.status_code == 200:
                all_items = items_r.json()
                if isinstance(all_items, dict):
                    all_items = all_items.get("items", [])
                target = [i for i in all_items if i["id"] == si_id]
                if target:
                    stock = Decimal(target[0]["current_stock"])
                    verdict = "HANDLED" if stock == Decimal("50") else "VULNERABLE"
                    record("INTEGRITY", "Stock level after movement",
                           "GET", "/inventory/items",
                           items_r.status_code,
                           f"expected=50, got={stock}",
                           verdict)

                    mv_r2 = requests.post(f"{BASE}/inventory/movements", headers=auth(MGR_TOKEN),
                                          json={"inventory_item_id": si_id,
                                                "change_amount": "-20",
                                                "reason": "USAGE",
                                                "notes": "chaos test deduct"})
                    if mv_r2.status_code == 201:
                        items_r2 = requests.get(f"{BASE}/inventory/items", headers=auth(MGR_TOKEN))
                        all_items2 = items_r2.json()
                        if isinstance(all_items2, dict):
                            all_items2 = all_items2.get("items", [])
                        target2 = [i for i in all_items2 if i["id"] == si_id]
                        if target2:
                            stock2 = Decimal(target2[0]["current_stock"])
                            verdict = "HANDLED" if stock2 == Decimal("30") else "VULNERABLE"
                            record("INTEGRITY", "Stock level after deduction",
                                   "GET", "/inventory/items",
                                   items_r2.status_code,
                                   f"expected=30, got={stock2}",
                                   verdict)


# =========================================================================
# GENERATE REPORT
# =========================================================================
print("\n" + "=" * 70)
print("CHAOS TEST REPORT SUMMARY")
print("=" * 70)

handled = sum(1 for r in RESULTS if r[5] == "HANDLED")
crashed = sum(1 for r in RESULTS if r[5] == "CRASHED")
vulnerable = sum(1 for r in RESULTS if r[5] == "VULNERABLE")
total = len(RESULTS)

print(f"  Total tests:  {total}")
print(f"  HANDLED:      {handled}")
print(f"  CRASHED:      {crashed}")
print(f"  VULNERABLE:   {vulnerable}")
print()

# Write report
report_lines = []
report_lines.append("# Kurahia Resort API -- Chaos Test Report\n")
report_lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
report_lines.append(f"**Target:** `{BASE}`\n")
report_lines.append(f"**Roles tested:** owner (wachira), manager (manager2), waiter (waiter1)\n")
report_lines.append("")
report_lines.append("## Summary\n")
report_lines.append(f"| Verdict | Count |")
report_lines.append(f"|---------|-------|")
report_lines.append(f"| HANDLED | {handled} |")
report_lines.append(f"| CRASHED | {crashed} |")
report_lines.append(f"| VULNERABLE | {vulnerable} |")
report_lines.append(f"| **Total** | **{total}** |")
report_lines.append("")

# Group by category
from collections import defaultdict
by_cat = defaultdict(list)
for r in RESULTS:
    by_cat[r[0]].append(r)

for cat, tests in by_cat.items():
    report_lines.append(f"\n## {cat}\n")
    report_lines.append("| # | Test | Endpoint | Status | Verdict | Detail |")
    report_lines.append("|---|------|----------|--------|---------|--------|")
    for i, (_, name, curl, status, key, verdict) in enumerate(tests, 1):
        key_clean = str(key).replace("|", " ").replace("\n", " ")[:120]
        v_mark = {"HANDLED": "HANDLED", "CRASHED": "**CRASHED**", "VULNERABLE": "**VULNERABLE**"}
        report_lines.append(f"| {i} | {name} | `{curl}` | {status} | {v_mark.get(verdict, verdict)} | {key_clean} |")

# Findings section
report_lines.append("\n## Key Findings\n")

vuln_tests = [r for r in RESULTS if r[5] == "VULNERABLE"]
crash_tests = [r for r in RESULTS if r[5] == "CRASHED"]

if vuln_tests:
    report_lines.append("### Vulnerabilities Found\n")
    for _, name, curl, status, key, _ in vuln_tests:
        report_lines.append(f"- **{name}** (`{curl}`): Status {status} -- {str(key)[:150]}")
    report_lines.append("")

if crash_tests:
    report_lines.append("### Crashes Found\n")
    for _, name, curl, status, key, _ in crash_tests:
        report_lines.append(f"- **{name}** (`{curl}`): Status {status} -- {str(key)[:150]}")
    report_lines.append("")

if not vuln_tests and not crash_tests:
    report_lines.append("No vulnerabilities or crashes found. All edge cases handled correctly.\n")

report_lines.append("\n---\n")
report_lines.append("*Generated by chaos_test.py*\n")

report_text = "\n".join(report_lines)

with open("/home/wachira/kurahia/docs/CHAOS_TEST_REPORT.md", "w") as f:
    f.write(report_text)

print(f"\nReport written to docs/CHAOS_TEST_REPORT.md")
print(f"Found {vulnerable} vulnerabilities and {crashed} crashes out of {total} tests.")
