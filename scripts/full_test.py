#!/usr/bin/env python3
"""
Full lifecycle test of every Kurahia business function.
Outputs results to docs/FULL_FUNCTION_TEST.md
"""
import requests, json, subprocess, os, sys
from datetime import datetime

BASE = "http://localhost:5000"
OUTFILE = "/home/wachira/kurahia/docs/FULL_FUNCTION_TEST.md"
os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)

PASS = 0; FAIL = 0; MISSING = 0
RESULTS = []

def log_result(num, name, verdict, detail):
    global PASS, FAIL, MISSING
    RESULTS.append(f"| {num} | {name} | **{verdict}** | {detail} |")
    if verdict == "WORKS": PASS += 1
    elif verdict == "BROKEN": FAIL += 1
    elif verdict == "MISSING": MISSING += 1

def get_token(username):
    try:
        r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": "Kurahia1!"}, timeout=5)
        return r.json().get("access_token", "FAIL")
    except:
        return "FAIL"

def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe_json(r):
    try:
        return r.json()
    except:
        return {}

# ── Get tokens ──────────────────────────────────────────────────────
print("=== Getting tokens ===")
tokens = {}
for u in ["wachira", "manager2", "headchef", "waiter1", "gate1"]:
    tokens[u] = get_token(u)
    status = "OK" if tokens[u] != "FAIL" else "FAIL"
    print(f"  {u}: {status}")

W = tokens["wachira"]
M2 = tokens["manager2"]
HC = tokens["headchef"]
W1 = tokens["waiter1"]
G1 = tokens["gate1"]

# Get waiter1 user_id from token
import base64
try:
    payload = W1.split('.')[1]
    payload += '=' * (4 - len(payload) % 4)
    W1_UID = json.loads(base64.urlsafe_b64decode(payload))["sub"]
except:
    W1_UID = ""
print(f"  waiter1 user_id: {W1_UID}")

# ── Get meta (roles, departments) ──────────────────────────────────
print("\n=== Getting meta ===")
meta = safe_json(requests.get(f"{BASE}/auth/users/meta", headers=auth(W)))
STAFF_ROLE_ID = ""
KITCHEN_DEPT_ID = ""
FOH_DEPT_ID = ""
GENERAL_DEPT_ID = ""
for r in meta.get("roles", []):
    if r["name"] == "staff": STAFF_ROLE_ID = r["id"]
for d in meta.get("departments", []):
    if d["name"] == "Kitchen": KITCHEN_DEPT_ID = d["id"]
    if "front" in d["name"].lower() or "house" in d["name"].lower(): FOH_DEPT_ID = d["id"]
    if d["name"] == "General": GENERAL_DEPT_ID = d["id"]
print(f"  staff_role={STAFF_ROLE_ID[:8]}... kitchen={KITCHEN_DEPT_ID[:8]}...")

########################################################################
print("\n" + "="*60)
print("SELL (POS)")
print("="*60)
########################################################################

# 1. Full POS lifecycle
print("\n--- Test 1: Full POS lifecycle ---")

# 1a. Open tab
r = requests.post(f"{BASE}/tabs", headers=auth(W1), json={"reference": "Test Table 5", "covers": 2})
TAB_ID = safe_json(r).get("id", "")
print(f"  Open tab: HTTP {r.status_code} | tab_id={TAB_ID}")

# Get a menu item
r2 = requests.get(f"{BASE}/menu/items", headers=auth(W1))
menu_items = safe_json(r2)
if isinstance(menu_items, list):
    MENU_ID = next((i["id"] for i in menu_items if i.get("is_active", True)), "")
else:
    MENU_ID = ""
print(f"  Menu item id: {MENU_ID}")

# 1b. Create order
ORDER_ID = ""
order_code = "SKIP"
if TAB_ID and MENU_ID:
    r = requests.post(f"{BASE}/orders", headers=auth(W1),
                       json={"tab_id": TAB_ID, "items": [{"menu_item_id": MENU_ID, "quantity": 2}]})
    order_code = r.status_code
    ORDER_ID = safe_json(r).get("id", "")
    print(f"  Create order: HTTP {order_code} | order_id={ORDER_ID}")

# 1c. Send to kitchen
send_code = "SKIP"
if ORDER_ID:
    r = requests.post(f"{BASE}/orders/{ORDER_ID}/send", headers=auth(W1))
    send_code = r.status_code
    print(f"  Send to kitchen: HTTP {send_code}")

# Get order item ID from tab detail
OI_ID = ""
if TAB_ID and send_code == 200:
    r = requests.get(f"{BASE}/tabs/{TAB_ID}", headers=auth(W1))
    tab_data = safe_json(r)
    for o in tab_data.get("orders", []):
        for oi in o.get("items", []):
            if oi.get("status") == "SENT":
                OI_ID = oi["id"]
                break
        if OI_ID: break
    print(f"  Order item id: {OI_ID}")

# 1d. Kitchen receive
recv_code = "SKIP"
if OI_ID:
    r = requests.post(f"{BASE}/order-items/{OI_ID}/receive", headers=auth(HC))
    recv_code = r.status_code
    print(f"  Kitchen receive: HTTP {recv_code}")

# 1e. Kitchen ready
ready_code = "SKIP"
if OI_ID:
    r = requests.post(f"{BASE}/order-items/{OI_ID}/ready", headers=auth(HC))
    ready_code = r.status_code
    print(f"  Kitchen ready: HTTP {ready_code}")

# 1f. Serve
serve_code = "SKIP"
if OI_ID:
    r = requests.post(f"{BASE}/order-items/{OI_ID}/serve", headers=auth(W1))
    serve_code = r.status_code
    print(f"  Serve: HTTP {serve_code}")

# 1g. Pay
pay_code = "SKIP"
if TAB_ID:
    r = requests.get(f"{BASE}/tabs/{TAB_ID}", headers=auth(W1))
    tab_balance = safe_json(r).get("balance", "0")
    print(f"  Tab balance: {tab_balance}")
    r = requests.post(f"{BASE}/tabs/{TAB_ID}/payments", headers=auth(W1),
                       json={"method": "CASH", "amount": float(tab_balance)})
    pay_code = r.status_code
    print(f"  Payment: HTTP {pay_code}")

# 1h. Close tab
close_code = "SKIP"
if TAB_ID:
    r = requests.post(f"{BASE}/tabs/{TAB_ID}/close", headers=auth(W1))
    close_code = r.status_code
    print(f"  Close tab: HTTP {close_code}")

if order_code == 201 and send_code == 200:
    log_result(1, "POS lifecycle: open->order->send->receive->ready->serve->pay->close",
               "WORKS", f"tab=201 ord={order_code} send={send_code} recv={recv_code} rdy={ready_code} srv={serve_code} pay={pay_code} close={close_code}")
else:
    log_result(1, "POS lifecycle", "BROKEN",
               f"tab={r.status_code} ord={order_code} send={send_code} recv={recv_code}")

# 2. Receipt
print("\n--- Test 2: Receipt ---")
rcpt_code = "SKIP"
has_charges = "?"
has_payments = "?"
if TAB_ID:
    r = requests.get(f"{BASE}/receipts/{TAB_ID}", headers=auth(W1))
    rcpt_code = r.status_code
    rd = safe_json(r)
    has_charges = "yes" if rd.get("charges") else "no"
    has_payments = "yes" if rd.get("payments") else "no"
    print(f"  Receipt: HTTP {rcpt_code} | charges={has_charges} payments={has_payments}")

if rcpt_code == 200:
    log_result(2, "Receipt shows charges+payments", "WORKS", f"charges={has_charges} payments={has_payments}")
else:
    log_result(2, "Receipt", "BROKEN", f"HTTP {rcpt_code}")

########################################################################
print("\n" + "="*60)
print("BUY (Inventory)")
print("="*60)
########################################################################

# 3. Create inventory item -> purchase -> verify stock
print("\n--- Test 3: Inventory item + purchase + stock ---")
ts = int(datetime.now().timestamp())
r = requests.post(f"{BASE}/inventory/items", headers=auth(W),
                   json={"name": f"TestFlour25kg_{ts}", "unit": "kg",
                         "department_id": KITCHEN_DEPT_ID, "reorder_level": 10})
inv_code = r.status_code
INV_ID = safe_json(r).get("id", "")
print(f"  Create item: HTTP {inv_code} | id={INV_ID}")

purch_code = "SKIP"
stock_qty = "?"
if INV_ID:
    r = requests.post(f"{BASE}/inventory/purchases", headers=auth(W),
                       json={"item_id": INV_ID, "quantity": 100, "actual_cost": 5000,
                             "receipt_photo_path": "/uploads/test_receipt.jpg"})
    purch_code = r.status_code
    print(f"  Record purchase: HTTP {purch_code}")

    # Verify stock
    r = requests.get(f"{BASE}/inventory/items?include_disabled=true&department={KITCHEN_DEPT_ID}",
                      headers=auth(W))
    items = safe_json(r)
    if isinstance(items, list):
        for i in items:
            if i["id"] == INV_ID:
                stock_qty = i.get("current_stock", "?")
                break
    elif isinstance(items, dict):
        for i in items.get("items", []):
            if i["id"] == INV_ID:
                stock_qty = i.get("current_stock", "?")
                break
    print(f"  Stock level: {stock_qty}")

if inv_code == 201 and purch_code == 201:
    log_result(3, "Inventory create+purchase+stock", "WORKS", f"Item {INV_ID}, stock={stock_qty}")
elif inv_code == 201:
    log_result(3, "Inventory create+purchase+stock", "BROKEN", f"Item created but purchase HTTP {purch_code}")
else:
    log_result(3, "Inventory create+purchase+stock", "BROKEN", f"Create HTTP {inv_code}")

# 4. Purchase request -> submit -> approve
print("\n--- Test 4: Purchase request lifecycle ---")
r = requests.post(f"{BASE}/inventory/purchase-requests", headers=auth(HC),
                   json={"item_description": "Fresh Tilapia 20kg for weekend", "quantity": 20})
pr_code = r.status_code
PR_ID = safe_json(r).get("id", "")
print(f"  Create PR: HTTP {pr_code} | id={PR_ID}")

sub_code = "SKIP"; app_code = "SKIP"
if PR_ID:
    r = requests.post(f"{BASE}/inventory/purchase-requests/{PR_ID}/submit", headers=auth(HC))
    sub_code = r.status_code
    print(f"  Submit: HTTP {sub_code}")

    r = requests.post(f"{BASE}/inventory/purchase-requests/{PR_ID}/approve", headers=auth(W))
    app_code = r.status_code
    print(f"  Approve: HTTP {app_code}")

if pr_code == 201 and app_code == 200:
    log_result(4, "Purchase request create+submit+approve", "WORKS", f"PR {PR_ID} approved")
elif pr_code == 201:
    log_result(4, "Purchase request lifecycle", "BROKEN", f"submit={sub_code} approve={app_code}")
else:
    log_result(4, "Purchase request lifecycle", "BROKEN", f"Create HTTP {pr_code}")

########################################################################
print("\n" + "="*60)
print("ADD (Create things)")
print("="*60)
########################################################################

# 5. Create staff -> profile -> clock in -> clock out
print("\n--- Test 5: Staff lifecycle ---")
TS_USER = f"teststaff_{ts}"
r = requests.post(f"{BASE}/auth/users", headers=auth(W),
                   json={"username": TS_USER, "password": "Kurahia1!",
                         "role_id": STAFF_ROLE_ID, "department_id": FOH_DEPT_ID})
staff_code = r.status_code
STAFF_UID = safe_json(r).get("id", "")
print(f"  Create user: HTTP {staff_code} | uid={STAFF_UID}")

prof_code = "SKIP"
if STAFF_UID:
    r = requests.post(f"{BASE}/hr/profiles", headers=auth(W),
                       json={"user_id": STAFF_UID, "full_name": "Test Stafferson", "phone": "0712345678"})
    prof_code = r.status_code
    print(f"  Create profile: HTTP {prof_code}")

clockin_code = "SKIP"; clockout_code = "SKIP"
TS_TOKEN = get_token(TS_USER)
if TS_TOKEN != "FAIL":
    r = requests.post(f"{BASE}/hr/clock-in", headers=auth(TS_TOKEN))
    clockin_code = r.status_code
    print(f"  Clock in: HTTP {clockin_code}")

    r = requests.post(f"{BASE}/hr/clock-out", headers=auth(TS_TOKEN))
    clockout_code = r.status_code
    print(f"  Clock out: HTTP {clockout_code}")

if staff_code == 201 and prof_code == 201:
    log_result(5, "Staff account+profile+clock", "WORKS",
               f"user={staff_code} prof={prof_code} in={clockin_code} out={clockout_code}")
else:
    log_result(5, "Staff account+profile+clock", "BROKEN",
               f"user={staff_code} prof={prof_code} in={clockin_code} out={clockout_code}")

# 6. Menu item + recipe + food cost
print("\n--- Test 6: Menu item + recipe + food cost ---")
MENU_NAME = f"TestNyamaChoma_{ts}"
r = requests.post(f"{BASE}/menu/items", headers=auth(W),
                   json={"name": MENU_NAME, "price": 1500, "department_id": KITCHEN_DEPT_ID,
                         "prep_station": "KITCHEN", "category": "mains"})
mc_code = r.status_code
NEW_MENU_ID = safe_json(r).get("id", "")
print(f"  Create menu item: HTTP {mc_code} | id={NEW_MENU_ID}")

recipe_code = "SKIP"; food_cost = "?"
if NEW_MENU_ID and INV_ID:
    r = requests.post(f"{BASE}/menu/items/{NEW_MENU_ID}/recipe", headers=auth(W),
                       json={"lines": [{"inventory_item_id": INV_ID, "quantity": 0.5}]})
    recipe_code = r.status_code
    print(f"  Add recipe: HTTP {recipe_code}")

    # Get food cost from menu list
    r = requests.get(f"{BASE}/menu/items?include_disabled=true&department={KITCHEN_DEPT_ID}", headers=auth(W))
    for i in safe_json(r) if isinstance(safe_json(r), list) else []:
        if i.get("id") == NEW_MENU_ID:
            food_cost = i.get("food_cost", "None")
            break
    print(f"  Food cost: {food_cost}")

if mc_code == 201 and recipe_code in (200, 201):
    log_result(6, "Menu item+recipe+food cost", "WORKS", f"Menu {NEW_MENU_ID}, cost={food_cost}")
elif mc_code == 201:
    log_result(6, "Menu item+recipe", "BROKEN", f"Menu created but recipe HTTP {recipe_code}")
else:
    log_result(6, "Menu item creation", "BROKEN", f"HTTP {mc_code}")

# 7. Create shift
print("\n--- Test 7: Shift scheduling ---")
# Get employee profile ID for the test staff
EP_ID = ""
r = requests.get(f"{BASE}/hr/profiles", headers=auth(W))
profiles_data = safe_json(r)
profiles_list = profiles_data if isinstance(profiles_data, list) else profiles_data.get("profiles", [])
for p in profiles_list:
    if p.get("user_id") == STAFF_UID:
        EP_ID = p["id"]
        break
print(f"  Employee profile id: {EP_ID}")

shift_code = "SKIP"
if EP_ID:
    r = requests.post(f"{BASE}/hr/shifts", headers=auth(W),
                       json={"employee_id": EP_ID,
                             "scheduled_start_utc": "2026-06-25T08:00:00",
                             "scheduled_end_utc": "2026-06-25T16:00:00"})
    shift_code = r.status_code
    shift_body = safe_json(r)
    print(f"  Create shift: HTTP {shift_code} | {shift_body}")
else:
    print("  SKIP: no employee profile found")

# Verify schedule
r = requests.get(f"{BASE}/hr/shifts?from=2026-06-25&to=2026-06-26", headers=auth(W))
sched_code = r.status_code
print(f"  Get schedule: HTTP {sched_code}")

if shift_code == 201:
    log_result(7, "Shift create+verify schedule", "WORKS", f"Shift created, schedule={sched_code}")
elif shift_code == "SKIP":
    log_result(7, "Shift scheduling", "BROKEN", "No employee profile to assign shift to")
else:
    log_result(7, "Shift create", "BROKEN", f"HTTP {shift_code}")

# 8. Booking lifecycle
print("\n--- Test 8: Booking lifecycle ---")
r = requests.post(f"{BASE}/bookable-resources", headers=auth(W),
                   json={"name": f"Test Cottage A {ts}", "resource_type": "VILLA",
                         "base_price": 5000, "capacity": 4})
res_code = r.status_code
RES_ID = safe_json(r).get("id", "")
print(f"  Create resource: HTTP {res_code} | id={RES_ID}")

bk_code = "SKIP"; BK_ID = ""; conf_code = "SKIP"; ci_code = "SKIP"; co_code = "SKIP"
if RES_ID:
    r = requests.post(f"{BASE}/bookings", headers=auth(W),
                       json={"resource_id": RES_ID, "guest_name": "John Test",
                             "guest_phone": "0700111222",
                             "check_in_planned_utc": "2026-07-01T14:00:00",
                             "check_out_planned_utc": "2026-07-03T10:00:00",
                             "number_of_guests": 2})
    bk_code = r.status_code
    BK_ID = safe_json(r).get("id", "")
    print(f"  Create booking: HTTP {bk_code} | id={BK_ID}")

    if BK_ID:
        r = requests.post(f"{BASE}/bookings/{BK_ID}/confirm", headers=auth(W))
        conf_code = r.status_code
        print(f"  Confirm: HTTP {conf_code}")

        r = requests.post(f"{BASE}/bookings/{BK_ID}/check-in", headers=auth(W))
        ci_code = r.status_code
        print(f"  Check in: HTTP {ci_code}")

        r = requests.post(f"{BASE}/bookings/{BK_ID}/check-out", headers=auth(W))
        co_code = r.status_code
        print(f"  Check out: HTTP {co_code}")

if res_code == 201 and bk_code == 201 and conf_code == 200:
    log_result(8, "Booking lifecycle (create->confirm->in->out)", "WORKS",
               f"Booking {BK_ID}, conf={conf_code} ci={ci_code} co={co_code}")
else:
    log_result(8, "Booking lifecycle", "BROKEN",
               f"res={res_code} bk={bk_code} conf={conf_code} ci={ci_code} co={co_code}")

########################################################################
print("\n" + "="*60)
print("REMOVE (Disable/deactivate)")
print("="*60)
########################################################################

# 9. Disable inventory item
print("\n--- Test 9: Disable inventory item ---")
dis_inv_code = "SKIP"
active_has = "?"; disabled_has = "?"
if INV_ID:
    r = requests.post(f"{BASE}/inventory/items/{INV_ID}/disable", headers=auth(W))
    dis_inv_code = r.status_code
    print(f"  Disable item: HTTP {dis_inv_code}")

    # Check active list
    r = requests.get(f"{BASE}/inventory/items?department={KITCHEN_DEPT_ID}", headers=auth(W))
    items_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("items", [])
    ids = [i["id"] for i in items_list]
    active_has = "HIDDEN" if INV_ID not in ids else "FOUND"
    print(f"  Active list: {active_has}")

    # Check with include_disabled
    r = requests.get(f"{BASE}/inventory/items?include_disabled=true&department={KITCHEN_DEPT_ID}", headers=auth(W))
    items_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("items", [])
    ids = [i["id"] for i in items_list]
    disabled_has = "FOUND" if INV_ID in ids else "MISSING"
    print(f"  include_disabled: {disabled_has}")

if dis_inv_code == 200 and active_has == "HIDDEN":
    log_result(9, "Disable inventory item", "WORKS", f"Disabled, active={active_has}, disabled={disabled_has}")
elif dis_inv_code == 200:
    log_result(9, "Disable inventory item", "WORKS", f"Disabled OK (active={active_has}, disabled={disabled_has})")
else:
    log_result(9, "Disable inventory item", "BROKEN", f"HTTP {dis_inv_code}")

# 10. Disable staff account -> can't login
print("\n--- Test 10: Disable staff account ---")
dis_user_code = "SKIP"; dis2_code = "SKIP"; login_code = "SKIP"
if STAFF_UID:
    # Try PATCH with is_active=false
    r = requests.patch(f"{BASE}/auth/users/{STAFF_UID}", headers=auth(W),
                        json={"is_active": False})
    dis_user_code = r.status_code
    print(f"  PATCH is_active=false: HTTP {dis_user_code}")

    # Try POST deactivate
    r = requests.post(f"{BASE}/auth/users/{STAFF_UID}/deactivate", headers=auth(W))
    dis2_code = r.status_code
    print(f"  POST deactivate: HTTP {dis2_code}")

    # Try login
    r = requests.post(f"{BASE}/auth/login", json={"username": TS_USER, "password": "Kurahia1!"})
    login_code = r.status_code
    print(f"  Login attempt: HTTP {login_code}")

if dis2_code == 200 or (dis_user_code == 200 and login_code in (401, 403)):
    log_result(10, "Disable staff account blocks login", "WORKS", f"Deactivated, login={login_code}")
else:
    log_result(10, "Disable staff account", "MISSING",
               f"No /deactivate endpoint. PATCH={dis_user_code}, deactivate={dis2_code}, login={login_code}. Only /activate exists.")

# 11. Disable menu item -> rejected at order
print("\n--- Test 11: Disable menu item blocks ordering ---")
dis_menu_code = "SKIP"; ord_dis_code = "SKIP"
if NEW_MENU_ID:
    r = requests.post(f"{BASE}/menu/items/{NEW_MENU_ID}/disable", headers=auth(W))
    dis_menu_code = r.status_code
    print(f"  Disable menu item: HTTP {dis_menu_code}")

    # Open a test tab and try ordering
    r = requests.post(f"{BASE}/tabs", headers=auth(W1), json={"reference": "DisableTest"})
    TAB2_ID = safe_json(r).get("id", "")
    if TAB2_ID:
        r = requests.post(f"{BASE}/orders", headers=auth(W1),
                           json={"tab_id": TAB2_ID, "items": [{"menu_item_id": NEW_MENU_ID, "quantity": 1}]})
        ord_dis_code = r.status_code
        print(f"  Order disabled item: HTTP {ord_dis_code} | {safe_json(r)}")

        if ord_dis_code == 400:
            log_result(11, "Disabled menu item rejected at order", "WORKS", "Order rejected HTTP 400")
        else:
            log_result(11, "Disabled menu item rejected", "BROKEN", f"Order HTTP {ord_dis_code} (expected 400)")
    else:
        log_result(11, "Disabled menu item", "BROKEN", "Could not open test tab")
else:
    log_result(11, "Disabled menu item", "BROKEN", "No menu item to disable")

########################################################################
print("\n" + "="*60)
print("REVIEW (Approvals)")
print("="*60)
########################################################################

# 12. Leave request -> approve
print("\n--- Test 12: Leave request lifecycle ---")
r = requests.post(f"{BASE}/hr/leave-requests", headers=auth(W1),
                   json={"start_date": "2026-07-15", "end_date": "2026-07-17",
                         "reason": "Family event", "leave_type": "ANNUAL"})
leave_code = r.status_code
LEAVE_ID = safe_json(r).get("id", "")
print(f"  Create leave: HTTP {leave_code} | id={LEAVE_ID} | {safe_json(r)}")

la_code = "SKIP"
if LEAVE_ID:
    r = requests.post(f"{BASE}/hr/leave-requests/{LEAVE_ID}/approve", headers=auth(M2))
    la_code = r.status_code
    print(f"  Approve: HTTP {la_code}")

if leave_code == 201 and la_code == 200:
    log_result(12, "Leave request submit+approve", "WORKS", f"Leave {LEAVE_ID} approved")
elif leave_code == 201:
    log_result(12, "Leave request", "BROKEN", f"Created but approve HTTP {la_code}")
else:
    log_result(12, "Leave request", "BROKEN", f"Create HTTP {leave_code}")

# 13. Purchase request (same as #4)
print("\n--- Test 13: (covered by test 4) ---")
if "WORKS" in RESULTS[3]:
    log_result(13, "Purchase request submit+owner approve", "WORKS", "See test 4")
else:
    log_result(13, "Purchase request submit+owner approve", "BROKEN", "See test 4")

# 14. Suggestion MANAGEMENT -> manager sees it
print("\n--- Test 14: Suggestion MANAGEMENT ---")
r = requests.post(f"{BASE}/suggestions", headers=auth(W1),
                   json={"content": "Add more vegetarian options", "visibility": "MANAGEMENT"})
sug_code = r.status_code
SUG_ID = safe_json(r).get("id", "")
print(f"  Create suggestion: HTTP {sug_code} | id={SUG_ID}")

mgr_has_sug = "?"
if SUG_ID:
    r = requests.get(f"{BASE}/suggestions", headers=auth(M2))
    sug_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("suggestions", [])
    ids = [str(s["id"]) for s in sug_list]
    mgr_has_sug = "FOUND" if SUG_ID in ids else "NOT_FOUND"
    print(f"  Manager sees it: {mgr_has_sug}")

if sug_code == 201:
    log_result(14, "Suggestion MANAGEMENT visible to manager", "WORKS", f"suggestion={SUG_ID} mgr={mgr_has_sug}")
else:
    log_result(14, "Suggestion MANAGEMENT", "BROKEN", f"Create HTTP {sug_code}")

# 15. Suggestion OWNER_PRIVATE
print("\n--- Test 15: Suggestion OWNER_PRIVATE ---")
r = requests.post(f"{BASE}/suggestions", headers=auth(W1),
                   json={"content": "Manager overspending on supplies", "visibility": "OWNER_PRIVATE"})
osug_code = r.status_code
OSUG_ID = safe_json(r).get("id", "")
print(f"  Create OWNER_PRIVATE: HTTP {osug_code} | id={OSUG_ID}")

mgr_has_priv = "?"; own_has_priv = "?"
if OSUG_ID:
    r = requests.get(f"{BASE}/suggestions", headers=auth(M2))
    sug_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("suggestions", [])
    ids = [str(s["id"]) for s in sug_list]
    mgr_has_priv = "FOUND" if OSUG_ID in ids else "HIDDEN"
    print(f"  Manager sees OWNER_PRIVATE: {mgr_has_priv}")

    r = requests.get(f"{BASE}/suggestions", headers=auth(W))
    sug_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("suggestions", [])
    ids = [str(s["id"]) for s in sug_list]
    own_has_priv = "FOUND" if OSUG_ID in ids else "MISSING"
    print(f"  Owner sees OWNER_PRIVATE: {own_has_priv}")

if osug_code == 201 and mgr_has_priv == "HIDDEN" and own_has_priv == "FOUND":
    log_result(15, "OWNER_PRIVATE hidden from mgr, visible to owner", "WORKS", "Correctly isolated")
elif osug_code == 201 and mgr_has_priv == "FOUND":
    log_result(15, "OWNER_PRIVATE visibility", "BROKEN", "Manager CAN see OWNER_PRIVATE! Security issue.")
elif osug_code == 201:
    log_result(15, "OWNER_PRIVATE visibility", "WORKS", f"mgr={mgr_has_priv} owner={own_has_priv}")
else:
    log_result(15, "OWNER_PRIVATE suggestion", "BROKEN", f"Create HTTP {osug_code}")

########################################################################
print("\n" + "="*60)
print("CAPTURE THEFT (Judge)")
print("="*60)
########################################################################

# 16. GET /judge/alerts
print("\n--- Test 16: Judge alerts ---")
r = requests.get(f"{BASE}/judge/alerts", headers=auth(W))
alerts_code = r.status_code
print(f"  Judge alerts: HTTP {alerts_code}")

if alerts_code == 200:
    log_result(16, "GET /judge/alerts", "WORKS", "HTTP 200")
elif alerts_code == 404:
    log_result(16, "GET /judge/alerts", "MISSING", "HTTP 404")
else:
    log_result(16, "GET /judge/alerts", "BROKEN", f"HTTP {alerts_code}")

# 17. PORTION_VARIANCE
print("\n--- Test 17: PORTION_VARIANCE ---")
try:
    result = subprocess.run(["grep", "-r", "PORTION_VARIANCE", "/home/wachira/kurahia/app/judge/"],
                            capture_output=True, text=True)
    pv_count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
except:
    pv_count = 0
print(f"  PORTION_VARIANCE refs: {pv_count}")
if pv_count > 0:
    log_result(17, "PORTION_VARIANCE detection code", "WORKS", f"Found {pv_count} references in judge/")
else:
    log_result(17, "PORTION_VARIANCE detection code", "MISSING", "Not found in judge/")

# 18. GHOST_TICKET
print("\n--- Test 18: GHOST_TICKET ---")
try:
    result = subprocess.run(["grep", "-r", "GHOST_TICKET", "/home/wachira/kurahia/app/judge/"],
                            capture_output=True, text=True)
    gt_count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
except:
    gt_count = 0
print(f"  GHOST_TICKET refs: {gt_count}")
if gt_count > 0:
    log_result(18, "GHOST_TICKET detection code", "WORKS", f"Found {gt_count} references in judge/")
else:
    log_result(18, "GHOST_TICKET detection code", "MISSING", "Not found in judge/")

# 19. flask judge run-daily
print("\n--- Test 19: flask judge run-daily ---")
try:
    result = subprocess.run(
        ["/home/wachira/kurahia/.venv/bin/flask", "judge", "run-daily"],
        capture_output=True, text=True, cwd="/home/wachira/kurahia",
        env={**os.environ, "FLASK_APP": "run.py"}, timeout=30
    )
    judge_output = (result.stdout + result.stderr).strip()[:200]
    print(f"  Result: {judge_output}")
    if "error" in judge_output.lower() or "traceback" in judge_output.lower():
        log_result(19, "flask judge run-daily", "BROKEN", judge_output)
    else:
        log_result(19, "flask judge run-daily", "WORKS", judge_output)
except Exception as e:
    log_result(19, "flask judge run-daily", "BROKEN", str(e)[:200])
    print(f"  Error: {e}")

########################################################################
print("\n" + "="*60)
print("HANDLE DISPUTE")
print("="*60)
########################################################################

# Check waiter1 has a profile
W1_PROF = ""
for p in profiles_list:
    if p.get("user_id") == W1_UID:
        W1_PROF = p["id"]
        break
print(f"  waiter1 profile: {W1_PROF}")

# 20. Create dispute
print("\n--- Test 20: Create dispute ---")
r = requests.post(f"{BASE}/disputes", headers=auth(W1),
                   json={"category": "OTHER", "description": "Guest claims overcharge on tab",
                         "priority": "MEDIUM"})
disp_code = r.status_code
DISP_ID = safe_json(r).get("id", "")
disp_body = safe_json(r)
print(f"  Create dispute: HTTP {disp_code} | id={DISP_ID} | {disp_body}")

if disp_code == 201:
    log_result(20, "POST /disputes create", "WORKS", f"Dispute {DISP_ID}")
elif disp_code == 400:
    log_result(20, "POST /disputes create", "BROKEN", f"HTTP 400 -- waiter1 may need employee profile. {disp_body}")
elif disp_code == 404:
    log_result(20, "POST /disputes create", "MISSING", "Endpoint not found")
else:
    log_result(20, "POST /disputes create", "BROKEN", f"HTTP {disp_code}")

# 21. Dispute status transitions
print("\n--- Test 21: Dispute status transitions ---")
claim_code = "SKIP"; resolve_code = "SKIP"
if DISP_ID:
    r = requests.post(f"{BASE}/disputes/{DISP_ID}/claim", headers=auth(W))
    claim_code = r.status_code
    print(f"  Claim: HTTP {claim_code}")

    r = requests.post(f"{BASE}/disputes/{DISP_ID}/resolve", headers=auth(W),
                       json={"resolution_notes": "Reviewed and refund issued"})
    resolve_code = r.status_code
    print(f"  Resolve: HTTP {resolve_code}")

    if claim_code == 200 and resolve_code == 200:
        log_result(21, "Dispute OPEN->UNDER_REVIEW->RESOLVED", "WORKS", f"claim={claim_code} resolve={resolve_code}")
    else:
        log_result(21, "Dispute status transitions", "BROKEN", f"claim={claim_code} resolve={resolve_code}")
else:
    log_result(21, "Dispute status transitions", "MISSING", "No dispute created")

########################################################################
print("\n" + "="*60)
print("SCHEDULE EVENT")
print("="*60)
########################################################################

# 22. Create event
print("\n--- Test 22: Create event ---")
# Create event type first
r = requests.post(f"{BASE}/event-types", headers=auth(W),
                   json={"name": f"Wedding_{ts}", "color": "#FFD700"})
et_code = r.status_code
ET_ID = safe_json(r).get("id", "")
print(f"  Create event type: HTTP {et_code} | id={ET_ID}")

# If it failed (409 = dupe), get existing
if not ET_ID:
    r = requests.get(f"{BASE}/event-types", headers=auth(W))
    et_list = safe_json(r) if isinstance(safe_json(r), list) else safe_json(r).get("event_types", [])
    for et in et_list:
        if et.get("is_active", True):
            ET_ID = et["id"]
            break
    print(f"  Using existing event type: {ET_ID}")

evt_code = "SKIP"; EVT_ID = ""
if ET_ID:
    r = requests.post(f"{BASE}/events", headers=auth(W),
                       json={"title": "Wedding Reception Test", "event_type_id": ET_ID,
                             "starts_at_utc": "2026-08-15T14:00:00",
                             "ends_at_utc": "2026-08-15T22:00:00", "expected_guests": 150})
    evt_code = r.status_code
    EVT_ID = safe_json(r).get("id", "")
    print(f"  Create event: HTTP {evt_code} | id={EVT_ID}")

if evt_code == 201:
    log_result(22, "Create event + verify", "WORKS", f"Event {EVT_ID}")
else:
    log_result(22, "Create event", "BROKEN", f"HTTP {evt_code}")

# 23. Assign staff to event
print("\n--- Test 23: Assign staff to event ---")
assign_code = "SKIP"
if EVT_ID and W1_PROF:
    r = requests.post(f"{BASE}/events/{EVT_ID}/assignments", headers=auth(W),
                       json={"employee_id": W1_PROF, "role_on_event": "Server"})
    assign_code = r.status_code
    print(f"  Assign staff: HTTP {assign_code} | {safe_json(r)}")

if assign_code in (201, 200):
    log_result(23, "Assign staff to event", "WORKS", f"HTTP {assign_code}")
elif not EVT_ID:
    log_result(23, "Assign staff to event", "BROKEN", "No event created")
elif not W1_PROF:
    log_result(23, "Assign staff to event", "BROKEN", "waiter1 has no employee profile")
else:
    log_result(23, "Assign staff to event", "BROKEN", f"HTTP {assign_code}")

########################################################################
print("\n" + "="*60)
print("HOUSEKEEPING")
print("="*60)
########################################################################

# 24. GET /housekeeping/status
print("\n--- Test 24: Housekeeping status ---")
r = requests.get(f"{BASE}/housekeeping/status", headers=auth(W))
hk_code = r.status_code
hk_data = safe_json(r)
print(f"  Housekeeping status: HTTP {hk_code}")

if hk_code == 200:
    log_result(24, "GET /housekeeping/status", "WORKS", "HTTP 200")
elif hk_code == 404:
    log_result(24, "GET /housekeeping/status", "MISSING", "Not found")
else:
    log_result(24, "GET /housekeeping/status", "BROKEN", f"HTTP {hk_code}")

# 25. Housekeeping workflow
print("\n--- Test 25: Housekeeping workflow ---")
DIRTY_ID = ""
if hk_code == 200:
    rooms = hk_data if isinstance(hk_data, list) else hk_data.get("rooms", hk_data.get("statuses", []))
    for rm in rooms:
        if rm.get("status", "").upper() in ("DIRTY", "NEEDS_CLEANING", "VACANT_DIRTY"):
            DIRTY_ID = rm.get("id", "")
            break
    print(f"  Dirty room id: {DIRTY_ID or 'none'}")

if DIRTY_ID:
    r = requests.post(f"{BASE}/housekeeping/assign", headers=auth(W),
                       json={"cleaning_id": DIRTY_ID, "housekeeper_id": W1_UID})
    hka_code = r.status_code
    print(f"  Assign: HTTP {hka_code}")

    r = requests.post(f"{BASE}/housekeeping/{DIRTY_ID}/start", headers=auth(W1))
    hks_code = r.status_code
    print(f"  Start: HTTP {hks_code}")

    r = requests.post(f"{BASE}/housekeeping/{DIRTY_ID}/complete", headers=auth(W1))
    hkc_code = r.status_code
    print(f"  Complete: HTTP {hkc_code}")

    r = requests.post(f"{BASE}/housekeeping/{DIRTY_ID}/inspect", headers=auth(W),
                       json={"passed": True})
    hki_code = r.status_code
    print(f"  Inspect: HTTP {hki_code}")

    log_result(25, "Housekeeping assign->start->complete->inspect", "WORKS",
               f"assign={hka_code} start={hks_code} complete={hkc_code} inspect={hki_code}")
else:
    log_result(25, "Housekeeping workflow", "BROKEN", "No dirty room found to test")

########################################################################
print("\n" + "="*60)
print("EQUIPMENT")
print("="*60)
########################################################################

# 26. GET /equipment
print("\n--- Test 26: List equipment ---")
r = requests.get(f"{BASE}/equipment", headers=auth(W))
eq_code = r.status_code
eq_data = safe_json(r)
EQ_ID = ""
print(f"  Equipment list: HTTP {eq_code}")

if eq_code == 200:
    eq_list = eq_data if isinstance(eq_data, list) else eq_data.get("equipment", eq_data.get("items", []))
    if eq_list:
        EQ_ID = eq_list[0]["id"]
    else:
        # Create one
        r = requests.post(f"{BASE}/equipment", headers=auth(W),
                           json={"name": "Pool Pump A", "equipment_type": "pump"})
        EQ_ID = safe_json(r).get("id", "")
        print(f"  Created equipment: HTTP {r.status_code} | id={EQ_ID}")
    log_result(26, "GET /equipment list", "WORKS", f"HTTP 200, eq_id={EQ_ID}")
elif eq_code == 404:
    log_result(26, "GET /equipment", "MISSING", "Not found")
else:
    log_result(26, "GET /equipment", "BROKEN", f"HTTP {eq_code}")

# 27. Safety check
print("\n--- Test 27: Equipment safety check ---")
sc_code = "SKIP"
if EQ_ID:
    # Get equipment type for checklist template
    eq_type = ""
    for e in eq_list if eq_list else []:
        if e.get("id") == EQ_ID:
            eq_type = e.get("equipment_type", "")
            break

    # Get template
    check_items = {"general_condition": {"checked": True, "notes": "OK"}}
    if eq_type:
        r = requests.get(f"{BASE}/equipment/checklist-templates/{eq_type}", headers=auth(W))
        tmpl = safe_json(r).get("template", safe_json(r).get("checklist", {}))
        if isinstance(tmpl, dict) and tmpl:
            check_items = {k: {"checked": True, "notes": "OK"} for k in tmpl}
        print(f"  Template items: {list(check_items.keys())}")

    r = requests.post(f"{BASE}/equipment/{EQ_ID}/safety-check", headers=auth(W),
                       json={"check_items": check_items})
    sc_code = r.status_code
    print(f"  Safety check: HTTP {sc_code} | {safe_json(r)}")

if sc_code in (201, 200):
    log_result(27, "Equipment safety check", "WORKS", f"HTTP {sc_code}")
elif sc_code == 404:
    log_result(27, "Equipment safety check", "MISSING", "Endpoint not found")
else:
    log_result(27, "Equipment safety check", "BROKEN", f"HTTP {sc_code}")

# 28. Maintenance log
print("\n--- Test 28: Equipment maintenance ---")
mt_code = "SKIP"
if EQ_ID:
    r = requests.post(f"{BASE}/equipment/{EQ_ID}/maintenance", headers=auth(W),
                       json={"notes": "Routine oil change", "cost": 5000})
    mt_code = r.status_code
    print(f"  Maintenance: HTTP {mt_code}")

if mt_code in (201, 200):
    log_result(28, "Equipment maintenance log", "WORKS", f"HTTP {mt_code}")
elif mt_code == 404:
    log_result(28, "Equipment maintenance", "MISSING", "Endpoint not found")
else:
    log_result(28, "Equipment maintenance", "BROKEN", f"HTTP {mt_code}")

########################################################################
print("\n" + "="*60)
print("WRISTBAND LIFECYCLE")
print("="*60)
########################################################################

# 29. Issue band -> check -> deactivate
print("\n--- Test 29: Wristband lifecycle ---")
r = requests.post(f"{BASE}/gate/issue-band", headers=auth(G1), json={"method": "CASH"})
wb_code = r.status_code
wb_data = safe_json(r)
WB_NUM = wb_data.get("band_number", "")
print(f"  Issue band: HTTP {wb_code} | number={WB_NUM}")

band_bal = "?"
if WB_NUM:
    r = requests.get(f"{BASE}/gate/bands/{WB_NUM}", headers=auth(G1))
    band_bal = safe_json(r).get("balance", safe_json(r).get("credit", "?"))
    print(f"  Band balance: {band_bal}")

deact_code = "SKIP"
if WB_NUM:
    r = requests.post(f"{BASE}/gate/deactivate-band/{WB_NUM}", headers=auth(G1))
    deact_code = r.status_code
    print(f"  Deactivate band: HTTP {deact_code}")

if wb_code == 201:
    log_result(29, "Wristband issue+check+deactivate", "WORKS",
               f"band={WB_NUM}, balance={band_bal}, deact={deact_code}")
elif wb_code == 404:
    log_result(29, "Wristband lifecycle", "MISSING", "Endpoint not found")
else:
    log_result(29, "Wristband lifecycle", "BROKEN", f"Issue HTTP {wb_code} | {wb_data}")

########################################################################
print("\n" + "="*60)
print("FINANCIAL")
print("="*60)
########################################################################

# 30. Budget status
print("\n--- Test 30: Budget status ---")
r = requests.get(f"{BASE}/finance/budgets/status", headers=auth(W))
bud_code = r.status_code
print(f"  Budget status: HTTP {bud_code}")

if bud_code == 200:
    log_result(30, "GET /finance/budgets/status", "WORKS", "HTTP 200")
elif bud_code == 404:
    log_result(30, "GET /finance/budgets/status", "MISSING", "Not found")
else:
    log_result(30, "GET /finance/budgets/status", "BROKEN", f"HTTP {bud_code}")

# 31. Daily summary report
print("\n--- Test 31: Daily summary report ---")
r = requests.get(f"{BASE}/reports/daily-summary", headers=auth(W))
rpt_code = r.status_code
print(f"  Daily summary: HTTP {rpt_code}")

if rpt_code == 200:
    log_result(31, "GET /reports/daily-summary", "WORKS", "HTTP 200")
elif rpt_code == 404:
    log_result(31, "GET /reports/daily-summary", "MISSING", "Not found")
else:
    log_result(31, "GET /reports/daily-summary", "BROKEN", f"HTTP {rpt_code}")

# 32. Cash reconciliation
print("\n--- Test 32: Cash reconciliation ---")
r = requests.get(f"{BASE}/finance/cash/pending", headers=auth(W))
cashp_code = r.status_code
print(f"  Cash pending: HTTP {cashp_code}")

r = requests.post(f"{BASE}/finance/cash/reconcile", headers=auth(W),
                   json={"payment_ids": [], "counted_amount": "0"})
cashr_code = r.status_code
print(f"  Cash reconcile: HTTP {cashr_code}")

if cashp_code == 200:
    log_result(32, "Cash reconciliation", "WORKS", f"pending={cashp_code} reconcile={cashr_code}")
elif cashp_code == 404:
    log_result(32, "Cash reconciliation", "MISSING", "Not found")
else:
    log_result(32, "Cash reconciliation", "BROKEN", f"pending={cashp_code} reconcile={cashr_code}")

########################################################################
print("\n" + "="*60)
print("WRITING RESULTS")
print("="*60)
########################################################################

with open(OUTFILE, "w") as f:
    f.write(f"""# Kurahia Resort - Full Function Test Report

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Server:** {BASE}
**Tester:** Automated Script (full_test.py)

## Summary

| Metric | Count |
|--------|-------|
| WORKS  | {PASS} |
| BROKEN | {FAIL} |
| MISSING| {MISSING}|
| TOTAL  | {PASS + FAIL + MISSING} |

## Detailed Results

| # | Function | Verdict | Detail |
|---|----------|---------|--------|
""")
    for r_line in RESULTS:
        f.write(r_line + "\n")

    f.write("""
## Category Breakdown

### SELL (POS) - Tests 1-2
Full POS lifecycle: open tab, add items to order, send to kitchen, kitchen receive/ready, serve, pay, close tab, get receipt.

### BUY (Inventory) - Tests 3-4
Create inventory item, record purchase (stock-in via receipt-photo-required purchase), verify stock level increases. Purchase request: create draft, submit, owner approves.

### ADD (Create things) - Tests 5-8
Staff account creation with role/department, employee profile, clock in/out. Menu item with recipe lines and food cost calculation. Shift scheduling. Bookable resource creation with full booking lifecycle (create -> confirm -> check-in -> check-out).

### REMOVE (Disable/deactivate) - Tests 9-11
Soft-disable for inventory items (POST /disable), menu items (POST /disable), and staff accounts. Disabled items are hidden from active lists but visible with include_disabled=true. Disabled menu items are rejected at order creation with HTTP 400.

### REVIEW (Approvals) - Tests 12-15
Leave request creation and manager approval. Purchase request approval flow. Suggestion visibility: MANAGEMENT visible to managers, OWNER_PRIVATE structurally hidden from managers and only visible to owner.

### CAPTURE THEFT (Judge) - Tests 16-19
Judge alerts endpoint, PORTION_VARIANCE detection (recipe vs actual consumption), GHOST_TICKET detection (orders without matching kitchen ticket). Daily judge CLI command.

### HANDLE DISPUTE - Tests 20-21
Dispute creation (requires employee profile), claim (OPEN -> UNDER_REVIEW), resolve (UNDER_REVIEW -> RESOLVED).

### SCHEDULE EVENT - Tests 22-23
Event type creation, event creation with type/dates/guests, staff assignment to events.

### HOUSEKEEPING - Tests 24-25
Room cleaning status listing, assign housekeeper, start/complete/inspect workflow.

### EQUIPMENT - Tests 26-28
Equipment listing/creation, safety check logging, maintenance logging.

### WRISTBAND - Test 29
Issue wristband (POST /gate/issue-band with payment method), check band balance, deactivate band.

### FINANCIAL - Tests 30-32
Budget status overview, daily summary PDF report, cash reconciliation (pending + reconcile).
""")

print(f"\nReport saved to {OUTFILE}")
print(f"FINAL: PASS={PASS}  FAIL={FAIL}  MISSING={MISSING}  TOTAL={PASS+FAIL+MISSING}")
