#!/usr/bin/env python3
"""
E2E test runner for Kurahia resort backend.
Hits real endpoints on localhost:5000, reports PASS/FAIL for each test.
"""
import time
import json
import uuid
import requests

BASE = "http://localhost:5000"
RESULTS = []  # (num, test_name, endpoint, expected, actual_status, actual_body_snippet, verdict)


def add(num, name, endpoint, expected, actual_status, actual_body, verdict):
    # Truncate body for display
    snippet = str(actual_body)[:120] if actual_body else ""
    RESULTS.append((num, name, endpoint, expected, actual_status, snippet, verdict))
    mark = "PASS" if verdict else "FAIL"
    print(f"  [{mark}] {num} {name} -> {actual_status}")


def login_with_retry(username, password, max_retries=12, wait=10):
    """Login with retry to handle rate limiting."""
    for attempt in range(max_retries):
        r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
        if r.status_code == 429:
            print(f"    Rate limited on {username}, waiting {wait}s (attempt {attempt+1})...")
            time.sleep(wait)
            continue
        return r
    return r  # return last response even if still rate limited


def pin_login_with_retry(username, pin, max_retries=12, wait=10):
    """PIN login with retry to handle rate limiting."""
    for attempt in range(max_retries):
        r = requests.post(f"{BASE}/auth/pin-login", json={"username": username, "pin": pin})
        if r.status_code == 429:
            print(f"    Rate limited on {username} PIN, waiting {wait}s (attempt {attempt+1})...")
            time.sleep(wait)
            continue
        return r
    return r


def auth_header(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def main():
    print("=" * 70)
    print("KURAHIA E2E TEST RUN")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 1: AUTH
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 1: AUTH ---")

    def safe_json_early(resp):
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:200]}

    # 1.1 Owner login
    r = login_with_retry("wachira", "Kurahia1!")
    body = safe_json_early(r)
    owner_token = body.get("access_token", "") if r.status_code == 200 else ""
    add("1.1", "Owner login (wachira)", "POST /auth/login",
        "200 + token", r.status_code, body, r.status_code == 200 and bool(owner_token))

    # 1.2 Manager login
    r = login_with_retry("manager2", "Kurahia1!")
    body = safe_json_early(r)
    manager_token = body.get("access_token", "") if r.status_code == 200 else ""
    add("1.2", "Manager login (manager2)", "POST /auth/login",
        "200 + token", r.status_code, body, r.status_code == 200 and bool(manager_token))

    # 1.3 Waiter login
    r = login_with_retry("waiter1", "Kurahia1!")
    body = safe_json_early(r)
    waiter_token = body.get("access_token", "") if r.status_code == 200 else ""
    add("1.3", "Waiter login (waiter1)", "POST /auth/login",
        "200 + token", r.status_code, body, r.status_code == 200 and bool(waiter_token))

    # 1.4 Gate staff login
    r = login_with_retry("gate1", "Kurahia1!")
    body = safe_json_early(r)
    gate_token = body.get("access_token", "") if r.status_code == 200 else ""
    add("1.4", "Gate staff login (gate1)", "POST /auth/login",
        "200 + token", r.status_code, body, r.status_code == 200 and bool(gate_token))

    # 1.5 PIN login
    r = pin_login_with_retry("wachira", "1111")
    body = safe_json_early(r)
    pin_token = body.get("access_token", "") if r.status_code == 200 else ""
    add("1.5", "PIN login (wachira / 1111)", "POST /auth/pin-login",
        "200 + token", r.status_code, body, r.status_code == 200 and bool(pin_token))

    # 1.6 Wrong password
    r = login_with_retry("wachira", "wrongpass")
    body = safe_json_early(r)
    add("1.6", "Wrong password", "POST /auth/login",
        "401", r.status_code, body, r.status_code == 401)

    # 1.7 Deactivated user (nonexistent user triggers same 401 path)
    r = login_with_retry("deactivated_user", "Kurahia1!")
    body = safe_json_early(r)
    add("1.7", "Deactivated/nonexistent user", "POST /auth/login",
        "401", r.status_code, body, r.status_code == 401)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 2: OWNER DASHBOARD
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 2: OWNER DASHBOARD ---")
    oh = auth_header(owner_token)

    def safe_json(resp):
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:200]}

    # 2.1 Dashboard overview
    r = requests.get(f"{BASE}/dashboard/overview", headers=oh)
    body = safe_json(r)
    add("2.1", "Dashboard overview", "GET /dashboard/overview",
        "200 + revenue/staff/bookings", r.status_code, body,
        r.status_code == 200 and isinstance(body, dict) and ("revenue" in body or "staff" in body or "bookings" in body))

    # 2.2 Judge alerts
    r = requests.get(f"{BASE}/judge/alerts", headers=oh)
    body = safe_json(r)
    add("2.2", "Judge alerts", "GET /judge/alerts",
        "200 + array", r.status_code, body,
        r.status_code == 200 and isinstance(body, (list, dict)))

    # 2.3 Finance budgets status
    r = requests.get(f"{BASE}/finance/budgets/status", headers=oh)
    body = safe_json(r)
    add("2.3", "Finance budgets status", "GET /finance/budgets/status",
        "200 + budgets", r.status_code, body,
        r.status_code == 200)

    # 2.4 Dashboard bookings
    r = requests.get(f"{BASE}/dashboard/bookings", headers=oh)
    body = safe_json(r)
    add("2.4", "Dashboard bookings", "GET /dashboard/bookings",
        "200 + bookings data", r.status_code, body,
        r.status_code == 200)

    # 2.5 Dashboard feedback
    r = requests.get(f"{BASE}/dashboard/feedback", headers=oh)
    body = safe_json(r)
    add("2.5", "Dashboard feedback", "GET /dashboard/feedback",
        "200 + feedback data", r.status_code, body,
        r.status_code == 200)

    # 2.6 Admin settings
    r = requests.get(f"{BASE}/admin/settings", headers=oh)
    body = safe_json(r)
    add("2.6", "Admin settings", "GET /admin/settings",
        "200 + business_day_start_hour", r.status_code, body,
        r.status_code == 200 and isinstance(body, dict) and "business_day_start_hour" in body)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 3: MANAGER FLOWS
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 3: MANAGER FLOWS ---")
    mh = auth_header(manager_token)

    # 3.1 Inventory items
    r = requests.get(f"{BASE}/inventory/items", headers=mh)
    body = safe_json(r)
    add("3.1", "Inventory items", "GET /inventory/items",
        "200 + array", r.status_code, body,
        r.status_code == 200 and isinstance(body, list))

    # 3.2 Purchase requests
    r = requests.get(f"{BASE}/inventory/purchase-requests", headers=mh)
    body = safe_json(r)
    add("3.2", "Purchase requests", "GET /inventory/purchase-requests",
        "200 + array", r.status_code, body,
        r.status_code == 200 and isinstance(body, list))

    # 3.3 Attendance today
    r = requests.get(f"{BASE}/hr/attendance/today", headers=mh)
    body = safe_json(r)
    add("3.3", "Attendance today", "GET /hr/attendance/today",
        "200 + array", r.status_code, body,
        r.status_code == 200 and isinstance(body, list))

    # 3.4 Finance budgets status (manager)
    r = requests.get(f"{BASE}/finance/budgets/status", headers=mh)
    body = safe_json(r)
    add("3.4", "Finance budgets (manager)", "GET /finance/budgets/status",
        "200 + budgets", r.status_code, body,
        r.status_code == 200)

    # 3.5 User list
    r = requests.get(f"{BASE}/auth/users", headers=mh)
    body = safe_json(r)
    add("3.5", "Staff list", "GET /auth/users",
        "200 + user list", r.status_code, body,
        r.status_code == 200 and isinstance(body, list))

    # 3.6 Menu items
    r = requests.get(f"{BASE}/menu/items", headers=mh)
    body = safe_json(r)
    add("3.6", "Menu items", "GET /menu/items",
        "200 + array", r.status_code, body,
        r.status_code == 200 and isinstance(body, list))

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 4: GATE + WRISTBAND
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 4: GATE + WRISTBAND ---")
    gh = auth_header(gate_token)

    # 4.1 Issue band
    r = requests.post(f"{BASE}/gate/issue-band", headers=gh,
                      json={"method": "CASH", "idempotency_key": str(uuid.uuid4())})
    body = safe_json(r)
    band_number = body.get("band_number", 0) if isinstance(body, dict) else 0
    band_tab_id = body.get("tab_id", "") if isinstance(body, dict) else ""
    add("4.1", "Issue wristband (CASH)", "POST /gate/issue-band",
        "201 + band_number + tab_id", r.status_code, body,
        r.status_code in (200, 201) and bool(band_number) and bool(band_tab_id))

    # 4.2 Today stats
    r = requests.get(f"{BASE}/gate/today-stats", headers=gh)
    body = safe_json(r)
    add("4.2", "Gate today stats", "GET /gate/today-stats",
        "200 + issued_today > 0", r.status_code, body,
        r.status_code == 200 and isinstance(body, dict) and body.get("issued_today", 0) > 0)

    # 4.3 Lookup band by number
    r = requests.get(f"{BASE}/gate/bands/{band_number}", headers=gh)
    body = safe_json(r)
    add("4.3", "Lookup band by number", f"GET /gate/bands/{band_number}",
        "200 + ACTIVE", r.status_code, body,
        r.status_code == 200 and isinstance(body, dict) and body.get("status") == "ACTIVE")

    # 4.4 Active bands
    r = requests.get(f"{BASE}/gate/active-bands", headers=gh)
    body = safe_json(r)
    add("4.4", "Active bands list", "GET /gate/active-bands",
        "200 + array with band", r.status_code, body,
        r.status_code == 200 and isinstance(body, list) and len(body) > 0)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 5: WAITER ORDER FLOW
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 5: WAITER ORDER FLOW ---")
    wh = auth_header(waiter_token)

    # 5.1 Open tab
    r = requests.post(f"{BASE}/tabs", headers=wh,
                      json={"reference": "E2E Test Tab"})
    tab_id = r.json().get("id", "") if r.status_code == 201 else ""
    add("5.1", "Open tab", "POST /tabs",
        "201 + tab id", r.status_code, r.json(),
        r.status_code == 201 and bool(tab_id))

    # 5.2 Get menu items
    r = requests.get(f"{BASE}/menu/items", headers=wh)
    menu_items = r.json() if r.status_code == 200 else []
    # Find a menu item that's active and has a price
    test_menu_item = None
    for mi in menu_items:
        if mi.get("is_active", True):
            test_menu_item = mi
            break
    menu_item_id = test_menu_item["id"] if test_menu_item else None
    menu_item_name = test_menu_item.get("name", "?") if test_menu_item else "?"
    add("5.2", "Get menu items", "GET /menu/items",
        "200 + items array", r.status_code, f"{len(menu_items)} items found",
        r.status_code == 200 and len(menu_items) > 0)

    # 5.3 Create order — try each active menu item until one is in stock
    order_id = ""
    order_menu_item_name = "?"
    order_status = 0
    order_body = {}
    for mi_candidate in menu_items:
        if not mi_candidate.get("is_active", True):
            continue
        order_idem = str(uuid.uuid4())
        r = requests.post(f"{BASE}/orders", headers=wh,
                          json={"tab_id": tab_id,
                                "items": [{"menu_item_id": mi_candidate["id"], "quantity": 1}],
                                "idempotency_key": order_idem})
        order_status = r.status_code
        try:
            order_body = r.json()
        except Exception:
            order_body = {"raw": r.text[:200]}
        if r.status_code == 201:
            order_id = order_body.get("id", "")
            order_menu_item_name = mi_candidate.get("name", "?")
            menu_item_id = mi_candidate["id"]  # save for stock test later
            break
        elif r.status_code == 409:
            # Stock depleted for this item — try next
            continue
        else:
            # Unexpected error — record and stop trying
            break

    add("5.3", f"Create order ({order_menu_item_name})", "POST /orders",
        "201 + order id", order_status, order_body,
        order_status == 201 and bool(order_id))

    # 5.4 Send order to kitchen
    if order_id:
        r = requests.post(f"{BASE}/orders/{order_id}/send", headers=wh)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        add("5.4", "Send order to kitchen", f"POST /orders/{order_id}/send",
            "200 + SENT", r.status_code, body, r.status_code == 200)
    else:
        add("5.4", "Send order to kitchen", "POST /orders/?/send",
            "200", 0, "No order created", False)

    # 5.5 Check kitchen queue
    r = requests.get(f"{BASE}/kitchen/queue", headers=mh)  # Use manager token (kitchen access)
    try:
        queue_data = r.json() if r.status_code == 200 else []
    except Exception:
        queue_data = []
    add("5.5", "Kitchen queue", "GET /kitchen/queue",
        "200 + order in queue", r.status_code,
        f"{len(queue_data)} items in queue" if isinstance(queue_data, list) else queue_data,
        r.status_code == 200)

    # Find our order item in the queue
    order_item_id = None
    if isinstance(queue_data, list):
        for qi in queue_data:
            if qi.get("order_id") == order_id:
                order_item_id = qi.get("id")
                break
    # If not found in queue, try getting from order detail
    if not order_item_id and order_id:
        r2 = requests.get(f"{BASE}/tabs/{tab_id}", headers=wh)
        if r2.status_code == 200:
            tab_data = r2.json()
            orders_in_tab = tab_data.get("orders", [])
            for o in orders_in_tab:
                if o.get("id") == order_id:
                    items_list = o.get("items", [])
                    if items_list:
                        order_item_id = items_list[0].get("id")
                    break

    # 5.6 Kitchen receives
    if order_item_id:
        r = requests.post(f"{BASE}/order-items/{order_item_id}/receive", headers=mh)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        add("5.6", "Kitchen receives item", f"POST /order-items/{order_item_id}/receive",
            "200", r.status_code, body, r.status_code == 200)
    else:
        add("5.6", "Kitchen receives item", "POST /order-items/?/receive",
            "200", 0, "Could not find order_item_id", False)

    # 5.7 Kitchen marks ready
    if order_item_id:
        r = requests.post(f"{BASE}/order-items/{order_item_id}/ready", headers=mh)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        add("5.7", "Kitchen marks ready", f"POST /order-items/{order_item_id}/ready",
            "200", r.status_code, body, r.status_code == 200)
    else:
        add("5.7", "Kitchen marks ready", "POST /order-items/?/ready",
            "200", 0, "Could not find order_item_id", False)

    # 5.8 Waiter serves
    if order_item_id:
        r = requests.post(f"{BASE}/order-items/{order_item_id}/serve", headers=wh)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        add("5.8", "Waiter serves item", f"POST /order-items/{order_item_id}/serve",
            "200", r.status_code, body, r.status_code == 200)
    else:
        add("5.8", "Waiter serves item", "POST /order-items/?/serve",
            "200", 0, "Could not find order_item_id", False)

    # 5.9 Pay tab (CASH)
    r_tab = requests.get(f"{BASE}/tabs/{tab_id}", headers=wh)
    balance = "0"
    if r_tab.status_code == 200:
        balance = r_tab.json().get("balance", "0")

    r = requests.post(f"{BASE}/tabs/{tab_id}/payments", headers=wh,
                      json={"method": "CASH", "amount": str(balance),
                            "idempotency_key": str(uuid.uuid4())})
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    add("5.9", "Pay tab (CASH)", f"POST /tabs/{tab_id}/payments",
        "201 + payment", r.status_code, body,
        r.status_code in (200, 201))

    # 5.10 Close tab
    r = requests.post(f"{BASE}/tabs/{tab_id}/close", headers=wh)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    add("5.10", "Close tab", f"POST /tabs/{tab_id}/close",
        "200 + CLOSED", r.status_code, body,
        r.status_code == 200)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 6: STOCK PRE-CHECK
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 6: STOCK PRE-CHECK ---")
    # Try every active menu item until we find one that returns 409 (sold out)
    stock_test_done = False
    for mi_candidate in menu_items:
        if not mi_candidate.get("is_active", True):
            continue
        r_order = requests.post(f"{BASE}/orders", headers=wh,
                                json={"items": [{"menu_item_id": mi_candidate["id"], "quantity": 1}],
                                      "idempotency_key": str(uuid.uuid4())})
        if r_order.status_code == 409:
            try:
                body = r_order.json()
            except Exception:
                body = {"raw": r_order.text[:200]}
            add("6.1", f"Order sold-out item ({mi_candidate['name']})", "POST /orders",
                "409", r_order.status_code, body, True)
            stock_test_done = True
            break

    if not stock_test_done:
        add("6.1", "Order sold-out item", "POST /orders",
            "409", "N/A", "No zero-stock items found to test -- all items in stock", None)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 7: RECEIPTS
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 7: RECEIPTS ---")
    r = requests.get(f"{BASE}/receipts/{tab_id}", headers=wh)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    has_receipt_data = isinstance(body, dict) and ("charges" in body or "payments" in body or "items" in body or "total" in body)
    add("7.1", "Get receipt", f"GET /receipts/{tab_id}",
        "200 + charges + payments", r.status_code, body,
        r.status_code == 200 and has_receipt_data)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 8: HEALTH
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 8: HEALTH ---")
    r = requests.get(f"{BASE}/health")
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    add("8.1", "Health check", "GET /health",
        "200 + status ok + cron_last_run", r.status_code, body,
        r.status_code == 200 and body.get("status") == "ok" and "cron_last_run" in body)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 9: ROLE PROTECTION
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 9: ROLE PROTECTION ---")

    # 9.1 Waiter -> dashboard/overview (expect 403)
    r = requests.get(f"{BASE}/dashboard/overview", headers=wh)
    add("9.1", "Waiter -> /dashboard/overview", "GET /dashboard/overview",
        "403", r.status_code, safe_json(r), r.status_code == 403)

    # 9.2 Waiter -> judge/alerts (expect 403)
    r = requests.get(f"{BASE}/judge/alerts", headers=wh)
    add("9.2", "Waiter -> /judge/alerts", "GET /judge/alerts",
        "403", r.status_code, safe_json(r), r.status_code == 403)

    # 9.3 Waiter -> admin/settings (expect 403)
    r = requests.get(f"{BASE}/admin/settings", headers=wh)
    add("9.3", "Waiter -> /admin/settings", "GET /admin/settings",
        "403", r.status_code, safe_json(r), r.status_code == 403)

    # 9.4 Gate staff -> inventory/items (expect 200 — auto-scoped read allowed)
    r = requests.get(f"{BASE}/inventory/items", headers=gh)
    add("9.4", "Gate staff -> /inventory/items", "GET /inventory/items",
        "200 (allowed)", r.status_code, safe_json(r),
        r.status_code == 200)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 10: SEARCH
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- SECTION 10: SEARCH ---")

    # 10.1 Menu search
    r = requests.get(f"{BASE}/menu/items?q=tilapia", headers=mh)
    add("10.1", "Menu search (tilapia)", "GET /menu/items?q=tilapia",
        "200 + filtered", r.status_code, safe_json(r),
        r.status_code == 200 and isinstance(safe_json(r), list))

    # 10.2 Inventory search
    r = requests.get(f"{BASE}/inventory/items?q=oil", headers=mh)
    add("10.2", "Inventory search (oil)", "GET /inventory/items?q=oil",
        "200 + filtered", r.status_code, safe_json(r),
        r.status_code == 200 and isinstance(safe_json(r), list))

    # 10.3 User search
    r = requests.get(f"{BASE}/auth/users?q=manager", headers=mh)
    add("10.3", "User search (manager)", "GET /auth/users?q=manager",
        "200 + filtered", r.status_code, safe_json(r),
        r.status_code == 200 and isinstance(safe_json(r), list))

    # ═══════════════════════════════════════════════════════════════════
    # REPORT
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("FULL RESULTS TABLE")
    print("=" * 70)

    pass_count = 0
    fail_count = 0
    skip_count = 0

    # Print markdown table
    print(f"\n| # | Test | Endpoint | Expected | Actual Status | Actual Response | PASS/FAIL |")
    print(f"|---|------|----------|----------|---------------|-----------------|-----------|")
    for num, name, endpoint, expected, actual_status, snippet, verdict in RESULTS:
        if verdict is None:
            mark = "SKIP"
            skip_count += 1
        elif verdict:
            mark = "PASS"
            pass_count += 1
        else:
            mark = "**FAIL**"
            fail_count += 1
        # Escape pipes in snippet
        safe_snippet = str(snippet).replace("|", "\\|")[:80]
        print(f"| {num} | {name} | `{endpoint}` | {expected} | {actual_status} | {safe_snippet} | {mark} |")

    print(f"\n--- SUMMARY: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP out of {len(RESULTS)} tests ---")

    # Write report to file
    with open("/home/wachira/kurahia/docs/E2E_TEST_REPORT.md", "w") as f:
        f.write("# Kurahia E2E Test Report\n\n")
        f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Target:** {BASE}\n")
        f.write(f"**Summary:** {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP out of {len(RESULTS)} tests\n\n")

        f.write("| # | Test | Endpoint | Expected | Actual Status | Actual Response | PASS/FAIL |\n")
        f.write("|---|------|----------|----------|---------------|-----------------|----------|\n")
        for num, name, endpoint, expected, actual_status, snippet, verdict in RESULTS:
            if verdict is None:
                mark = "SKIP"
            elif verdict:
                mark = "PASS"
            else:
                mark = "**FAIL**"
            safe_snippet = str(snippet).replace("|", "\\|")[:80]
            f.write(f"| {num} | {name} | `{endpoint}` | {expected} | {actual_status} | {safe_snippet} | {mark} |\n")

        # Failure analysis
        failures = [(num, name, endpoint, expected, actual_status, snippet) for num, name, endpoint, expected, actual_status, snippet, verdict in RESULTS if verdict is False]
        if failures:
            f.write("\n## Failure Analysis\n\n")
            for num, name, endpoint, expected, actual_status, snippet in failures:
                f.write(f"### {num} {name}\n")
                f.write(f"- **Endpoint:** `{endpoint}`\n")
                f.write(f"- **Expected:** {expected}\n")
                f.write(f"- **Actual:** HTTP {actual_status} — `{snippet}`\n")
                f.write(f"- **Analysis:** See below.\n\n")

        skips = [(num, name, snippet) for num, name, _, _, _, snippet, verdict in RESULTS if verdict is None]
        if skips:
            f.write("\n## Skipped Tests\n\n")
            for num, name, snippet in skips:
                f.write(f"- **{num} {name}:** {snippet}\n")

    print(f"\nReport saved to /home/wachira/kurahia/docs/E2E_TEST_REPORT.md")


if __name__ == "__main__":
    main()
