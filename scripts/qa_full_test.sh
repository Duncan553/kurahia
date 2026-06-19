#!/usr/bin/env bash
# Full QA test script for Kurahia Resort backend
# Tests every scenario from the QA checklist

set -euo pipefail
BASE="http://localhost:5000"
RESULTS=""
TEST_NUM=0

# Helper: record a test result
record() {
  local test_name="$1" method="$2" endpoint="$3" expected="$4" actual="$5"
  TEST_NUM=$((TEST_NUM + 1))
  if [ "$actual" = "$expected" ]; then
    verdict="PASS"
  else
    verdict="FAIL"
  fi
  RESULTS="${RESULTS}| ${TEST_NUM} | ${test_name} | ${method} | ${endpoint} | ${expected} | ${actual} | ${verdict} |\n"
  echo "  #${TEST_NUM} ${verdict}: ${test_name} (expected=${expected}, actual=${actual})"
}

# Get HTTP status code
status() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

# Get response body
body() {
  curl -s "$@"
}

echo "=== ACQUIRING TOKENS ==="
OWNER=$(curl -s ${BASE}/auth/login -X POST -H 'Content-Type: application/json' -d '{"username":"wachira","password":"Kurahia1!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  Owner token acquired"
MGR=$(curl -s ${BASE}/auth/login -X POST -H 'Content-Type: application/json' -d '{"username":"manager2","password":"Kurahia1!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  Manager token acquired"
WAITER=$(curl -s ${BASE}/auth/login -X POST -H 'Content-Type: application/json' -d '{"username":"waiter1","password":"Kurahia1!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  Waiter token acquired"
GATE=$(curl -s ${BASE}/auth/login -X POST -H 'Content-Type: application/json' -d '{"username":"gate1","password":"Kurahia1!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  Gate token acquired"

OH="Authorization: Bearer ${OWNER}"
MH="Authorization: Bearer ${MGR}"
WH="Authorization: Bearer ${WAITER}"
GH="Authorization: Bearer ${GATE}"
CT="Content-Type: application/json"

echo ""
echo "=== HEALTH CHECK ==="
CODE=$(status ${BASE}/health)
record "Health check" "GET" "/health" "200" "$CODE"

echo ""
echo "=== OWNER TESTS ==="

CODE=$(status -H "$OH" ${BASE}/dashboard/overview)
record "Owner: dashboard overview" "GET" "/dashboard/overview" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/judge/alerts)
record "Owner: judge alerts" "GET" "/judge/alerts" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/finance/budgets/status)
record "Owner: budget status" "GET" "/finance/budgets/status" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/admin/settings)
record "Owner: admin settings GET" "GET" "/admin/settings" "200" "$CODE"

# PATCH settings: change business_day_start_hour to 7
IDEM1=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
CODE=$(status -X PATCH -H "$OH" -H "$CT" -d "{\"business_day_start_hour\":7,\"idempotency_key\":\"${IDEM1}\"}" ${BASE}/admin/settings)
record "Owner: admin settings PATCH (to 7)" "PATCH" "/admin/settings" "200" "$CODE"

# PATCH settings: change back to 6
IDEM2=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
CODE=$(status -X PATCH -H "$OH" -H "$CT" -d "{\"business_day_start_hour\":6,\"idempotency_key\":\"${IDEM2}\"}" ${BASE}/admin/settings)
record "Owner: admin settings PATCH (back to 6)" "PATCH" "/admin/settings" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/dashboard/bookings)
record "Owner: dashboard bookings" "GET" "/dashboard/bookings" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/dashboard/feedback)
record "Owner: dashboard feedback" "GET" "/dashboard/feedback" "200" "$CODE"

CODE=$(status -H "$OH" ${BASE}/dashboard/equipment)
record "Owner: dashboard equipment" "GET" "/dashboard/equipment" "200" "$CODE"

echo ""
echo "=== MANAGER TESTS ==="

CODE=$(status -H "$MH" ${BASE}/inventory/items)
record "Manager: inventory items GET" "GET" "/inventory/items" "200" "$CODE"

# POST inventory item
IDEM3=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
RESP=$(body -X POST -H "$MH" -H "$CT" -d "{\"name\":\"QA Test Item $(date +%s)\",\"unit\":\"kg\",\"department\":\"kitchen\",\"reorder_level\":5,\"idempotency_key\":\"${IDEM3}\"}" ${BASE}/inventory/items)
INV_CODE=$(echo "$RESP" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('item',{}).get('id','MISSING'))" 2>/dev/null || echo "ERROR")
INV_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$MH" -H "$CT" -d "{\"name\":\"QA Test Item $(date +%s)\",\"unit\":\"kg\",\"department\":\"kitchen\",\"reorder_level\":5,\"idempotency_key\":\"$(python3 -c 'import uuid;print(uuid.uuid4())')\"}" ${BASE}/inventory/items)
record "Manager: inventory items POST" "POST" "/inventory/items" "201" "$INV_STATUS"

# Get the created item ID from the first POST
INV_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['item']['id'])" 2>/dev/null || echo "")

if [ -n "$INV_ID" ] && [ "$INV_ID" != "MISSING" ]; then
  IDEM4=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
  CODE=$(status -X PATCH -H "$MH" -H "$CT" -d "{\"reorder_level\":10,\"idempotency_key\":\"${IDEM4}\"}" ${BASE}/inventory/items/${INV_ID})
  record "Manager: inventory item PATCH" "PATCH" "/inventory/items/{id}" "200" "$CODE"

  IDEM5=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
  CODE=$(status -X POST -H "$MH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM5}\"}" ${BASE}/inventory/items/${INV_ID}/disable)
  record "Manager: inventory item disable" "POST" "/inventory/items/{id}/disable" "200" "$CODE"

  IDEM6=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
  CODE=$(status -X POST -H "$MH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM6}\"}" ${BASE}/inventory/items/${INV_ID}/enable)
  record "Manager: inventory item enable" "POST" "/inventory/items/{id}/enable" "200" "$CODE"
else
  record "Manager: inventory item PATCH" "PATCH" "/inventory/items/{id}" "200" "SKIP(no id)"
  record "Manager: inventory item disable" "POST" "/inventory/items/{id}/disable" "200" "SKIP(no id)"
  record "Manager: inventory item enable" "POST" "/inventory/items/{id}/enable" "200" "SKIP(no id)"
fi

CODE=$(status -H "$MH" ${BASE}/menu/items)
record "Manager: menu items GET" "GET" "/menu/items" "200" "$CODE"

# POST menu item (create QA Burger)
IDEM7=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
MENU_RESP=$(body -X POST -H "$MH" -H "$CT" -d "{\"name\":\"QA Burger $(date +%s)\",\"price\":\"850.00\",\"department\":\"kitchen\",\"category\":\"main\",\"idempotency_key\":\"${IDEM7}\"}" ${BASE}/menu/items)
MENU_STATUS=$(echo "$MENU_RESP" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    # Check if error
    if 'message' in r and 'item' not in r:
        print('ERR')
    else:
        print('OK')
except:
    print('ERR')
" 2>/dev/null)
MENU_HTTP=$(status -X POST -H "$MH" -H "$CT" -d "{\"name\":\"QA Burger $(date +%s)b\",\"price\":\"850.00\",\"department\":\"kitchen\",\"category\":\"main\",\"idempotency_key\":\"$(python3 -c 'import uuid;print(uuid.uuid4())')\"}" ${BASE}/menu/items)
record "Manager: menu items POST" "POST" "/menu/items" "201" "$MENU_HTTP"

# Get menu item ID for PATCH
MENU_ID=$(echo "$MENU_RESP" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('item',{}).get('id', r.get('menu_item',{}).get('id','')))" 2>/dev/null || echo "")

if [ -n "$MENU_ID" ]; then
  IDEM8=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
  CODE=$(status -X PATCH -H "$MH" -H "$CT" -d "{\"price\":\"900.00\",\"idempotency_key\":\"${IDEM8}\"}" ${BASE}/menu/items/${MENU_ID})
  record "Manager: menu item PATCH" "PATCH" "/menu/items/{id}" "200" "$CODE"
else
  echo "  DEBUG menu POST response: $MENU_RESP"
  record "Manager: menu item PATCH" "PATCH" "/menu/items/{id}" "200" "SKIP(no id)"
fi

CODE=$(status -H "$MH" ${BASE}/inventory/purchase-requests)
record "Manager: purchase requests GET" "GET" "/inventory/purchase-requests" "200" "$CODE"

CODE=$(status -H "$MH" ${BASE}/hr/attendance/today)
record "Manager: HR attendance today" "GET" "/hr/attendance/today" "200" "$CODE"

CODE=$(status -H "$MH" ${BASE}/auth/users)
record "Manager: auth users GET" "GET" "/auth/users" "200" "$CODE"

echo ""
echo "=== GATE TESTS ==="

# Issue a band
IDEM9=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
BAND_RESP=$(body -X POST -H "$GH" -H "$CT" -d "{\"guest_name\":\"QA Test Guest\",\"payment_method\":\"cash\",\"amount\":\"3000.00\",\"idempotency_key\":\"${IDEM9}\"}" ${BASE}/gate/issue-band)
BAND_HTTP=$(echo "$BAND_RESP" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print('OK')
except:
    print('ERR')
" 2>/dev/null)
BAND_STATUS=$(status -X POST -H "$GH" -H "$CT" -d "{\"guest_name\":\"QA Test Guest 2\",\"payment_method\":\"cash\",\"amount\":\"3000.00\",\"idempotency_key\":\"$(python3 -c 'import uuid;print(uuid.uuid4())')\"}" ${BASE}/gate/issue-band)
record "Gate: issue band" "POST" "/gate/issue-band" "201" "$BAND_STATUS"

# Get band number from response
BAND_NUM=$(echo "$BAND_RESP" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('band',{}).get('band_number', r.get('band_number','')))" 2>/dev/null || echo "")

CODE=$(status -H "$GH" ${BASE}/gate/today-stats)
record "Gate: today stats" "GET" "/gate/today-stats" "200" "$CODE"

if [ -n "$BAND_NUM" ]; then
  CODE=$(status -H "$GH" ${BASE}/gate/bands/${BAND_NUM})
  record "Gate: band lookup" "GET" "/gate/bands/{n}" "200" "$CODE"
else
  echo "  DEBUG band response: $BAND_RESP"
  # Try with band number 1
  CODE=$(status -H "$GH" ${BASE}/gate/bands/1)
  record "Gate: band lookup" "GET" "/gate/bands/{n}" "200" "$CODE"
fi

CODE=$(status -H "$GH" ${BASE}/gate/active-bands)
record "Gate: active bands" "GET" "/gate/active-bands" "200" "$CODE"

echo ""
echo "=== WAITER FULL FLOW ==="

# Step 1: Create a tab (waiter opens a tab for a table)
IDEM_TAB=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
TAB_RESP=$(body -X POST -H "$WH" -H "$CT" -d "{\"table_number\":99,\"idempotency_key\":\"${IDEM_TAB}\"}" ${BASE}/tabs)
TAB_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$WH" -H "$CT" -d "{\"table_number\":99,\"idempotency_key\":\"${IDEM_TAB}\"}" ${BASE}/tabs)
echo "  DEBUG tab response: $TAB_RESP"
TAB_ID=$(echo "$TAB_RESP" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('tab',{}).get('id', ''))" 2>/dev/null || echo "")
record "Waiter: create tab" "POST" "/tabs" "201" "$TAB_STATUS"

# We need a valid menu item ID for ordering. Let's get one.
MENU_LIST=$(body -H "$WH" ${BASE}/menu/items)
FIRST_MENU_ID=$(echo "$MENU_LIST" | python3 -c "
import sys,json
r=json.load(sys.stdin)
items = r if isinstance(r, list) else r.get('items', r.get('menu_items', []))
for i in items:
    if i.get('is_active', True):
        print(i['id'])
        break
" 2>/dev/null || echo "")
echo "  Using menu item ID: $FIRST_MENU_ID"

if [ -n "$TAB_ID" ] && [ -n "$FIRST_MENU_ID" ]; then
  # Step 2: Create order
  IDEM_ORD=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
  ORD_RESP=$(body -X POST -H "$WH" -H "$CT" -d "{\"tab_id\":\"${TAB_ID}\",\"items\":[{\"menu_item_id\":\"${FIRST_MENU_ID}\",\"quantity\":1}],\"idempotency_key\":\"${IDEM_ORD}\"}" ${BASE}/orders)
  ORD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$WH" -H "$CT" -d "{\"tab_id\":\"${TAB_ID}\",\"items\":[{\"menu_item_id\":\"${FIRST_MENU_ID}\",\"quantity\":1}],\"idempotency_key\":\"${IDEM_ORD}\"}" ${BASE}/orders)
  echo "  DEBUG order response: $ORD_RESP"
  record "Waiter: create order" "POST" "/orders" "201" "$ORD_STATUS"

  ORDER_ID=$(echo "$ORD_RESP" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('order',{}).get('id', ''))" 2>/dev/null || echo "")
  ORDER_ITEM_ID=$(echo "$ORD_RESP" | python3 -c "
import sys,json
r=json.load(sys.stdin)
items = r.get('order',{}).get('items',[])
if items:
    print(items[0].get('id',''))
else:
    print('')
" 2>/dev/null || echo "")

  if [ -n "$ORDER_ID" ]; then
    # Step 3: Send order to kitchen
    IDEM_SEND=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
    CODE=$(status -X POST -H "$WH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_SEND}\"}" ${BASE}/orders/${ORDER_ID}/send)
    record "Waiter: send order" "POST" "/orders/{id}/send" "200" "$CODE"

    if [ -n "$ORDER_ITEM_ID" ]; then
      # Step 4: Manager/kitchen receives order item
      IDEM_RCV=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
      CODE=$(status -X POST -H "$MH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_RCV}\"}" ${BASE}/order-items/${ORDER_ITEM_ID}/receive)
      record "Manager: receive order item" "POST" "/order-items/{id}/receive" "200" "$CODE"

      # Step 5: Mark ready
      IDEM_RDY=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
      CODE=$(status -X POST -H "$MH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_RDY}\"}" ${BASE}/order-items/${ORDER_ITEM_ID}/ready)
      record "Manager: order item ready" "POST" "/order-items/{id}/ready" "200" "$CODE"

      # Step 6: Waiter serves
      IDEM_SRV=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
      CODE=$(status -X POST -H "$WH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_SRV}\"}" ${BASE}/order-items/${ORDER_ITEM_ID}/serve)
      record "Waiter: serve order item" "POST" "/order-items/{id}/serve" "200" "$CODE"
    else
      record "Manager: receive order item" "POST" "/order-items/{id}/receive" "200" "SKIP(no item id)"
      record "Manager: order item ready" "POST" "/order-items/{id}/ready" "200" "SKIP(no item id)"
      record "Waiter: serve order item" "POST" "/order-items/{id}/serve" "200" "SKIP(no item id)"
    fi

    # Step 7: Payment on tab
    # Get the tab balance first to know how much to pay
    TAB_INFO=$(body -H "$WH" ${BASE}/tabs/${TAB_ID})
    TAB_BALANCE=$(echo "$TAB_INFO" | python3 -c "
import sys,json
r=json.load(sys.stdin)
tab=r.get('tab',r)
print(tab.get('balance', tab.get('total','0')))
" 2>/dev/null || echo "850.00")
    echo "  Tab balance: $TAB_BALANCE"

    IDEM_PAY=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
    PAY_RESP=$(body -X POST -H "$WH" -H "$CT" -d "{\"amount\":\"${TAB_BALANCE}\",\"method\":\"cash\",\"idempotency_key\":\"${IDEM_PAY}\"}" ${BASE}/tabs/${TAB_ID}/payments)
    PAY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$WH" -H "$CT" -d "{\"amount\":\"${TAB_BALANCE}\",\"method\":\"cash\",\"idempotency_key\":\"${IDEM_PAY}\"}" ${BASE}/tabs/${TAB_ID}/payments)
    echo "  DEBUG payment response: $PAY_RESP"
    record "Waiter: tab payment" "POST" "/tabs/{id}/payments" "201" "$PAY_STATUS"

    # Step 8: Close tab
    IDEM_CLOSE=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
    CLOSE_RESP=$(body -X POST -H "$WH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_CLOSE}\"}" ${BASE}/tabs/${TAB_ID}/close)
    CLOSE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$WH" -H "$CT" -d "{\"idempotency_key\":\"${IDEM_CLOSE}\"}" ${BASE}/tabs/${TAB_ID}/close)
    echo "  DEBUG close response: $CLOSE_RESP"
    record "Waiter: close tab" "POST" "/tabs/{id}/close" "200" "$CLOSE_STATUS"

    # Step 9: Get receipt
    # Receipt ID might be the tab ID or returned from close
    RECEIPT_ID=$(echo "$CLOSE_RESP" | python3 -c "
import sys,json
r=json.load(sys.stdin)
print(r.get('receipt',{}).get('id', r.get('receipt_id', '')))
" 2>/dev/null || echo "")
    if [ -z "$RECEIPT_ID" ]; then
      RECEIPT_ID="$TAB_ID"
    fi
    CODE=$(status -H "$WH" ${BASE}/receipts/${RECEIPT_ID})
    record "Waiter: get receipt" "GET" "/receipts/{id}" "200" "$CODE"
  else
    record "Waiter: create order" "POST" "/orders" "201" "SKIP(no tab)"
    record "Waiter: send order" "POST" "/orders/{id}/send" "200" "SKIP"
    record "Manager: receive order item" "POST" "/order-items/{id}/receive" "200" "SKIP"
    record "Manager: order item ready" "POST" "/order-items/{id}/ready" "200" "SKIP"
    record "Waiter: serve order item" "POST" "/order-items/{id}/serve" "200" "SKIP"
    record "Waiter: tab payment" "POST" "/tabs/{id}/payments" "201" "SKIP"
    record "Waiter: close tab" "POST" "/tabs/{id}/close" "200" "SKIP"
    record "Waiter: get receipt" "GET" "/receipts/{id}" "200" "SKIP"
  fi
else
  echo "  DEBUG: TAB_ID=$TAB_ID FIRST_MENU_ID=$FIRST_MENU_ID"
  for t in "Waiter: create order|POST|/orders|201" "Waiter: send order|POST|/orders/{id}/send|200" "Manager: receive order item|POST|/order-items/{id}/receive|200" "Manager: order item ready|POST|/order-items/{id}/ready|200" "Waiter: serve order item|POST|/order-items/{id}/serve|200" "Waiter: tab payment|POST|/tabs/{id}/payments|201" "Waiter: close tab|POST|/tabs/{id}/close|200" "Waiter: get receipt|GET|/receipts/{id}|200"; do
    IFS='|' read -r name method ep exp <<< "$t"
    record "$name" "$method" "$ep" "$exp" "SKIP"
  done
fi

echo ""
echo "=== HR TESTS ==="

CODE=$(status -H "$WH" ${BASE}/hr/clock-status)
record "HR: clock status (waiter)" "GET" "/hr/clock-status" "200" "$CODE"

# POST suggestion MANAGEMENT
IDEM_SUG1=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
CODE=$(status -X POST -H "$WH" -H "$CT" -d "{\"content\":\"QA test suggestion MANAGEMENT\",\"visibility\":\"MANAGEMENT\",\"idempotency_key\":\"${IDEM_SUG1}\"}" ${BASE}/suggestions)
record "HR: post suggestion MANAGEMENT" "POST" "/suggestions" "201" "$CODE"

# POST suggestion OWNER_PRIVATE
IDEM_SUG2=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
CODE=$(status -X POST -H "$WH" -H "$CT" -d "{\"content\":\"QA test suggestion OWNER_PRIVATE\",\"visibility\":\"OWNER_PRIVATE\",\"idempotency_key\":\"${IDEM_SUG2}\"}" ${BASE}/suggestions)
record "HR: post suggestion OWNER_PRIVATE" "POST" "/suggestions" "201" "$CODE"

# GET suggestions as manager (OWNER_PRIVATE should be hidden)
SUG_MGR=$(body -H "$MH" ${BASE}/suggestions)
HAS_OWNER_PRIVATE_MGR=$(echo "$SUG_MGR" | python3 -c "
import sys,json
r=json.load(sys.stdin)
items = r if isinstance(r, list) else r.get('suggestions', [])
for i in items:
    if i.get('visibility') == 'OWNER_PRIVATE' or 'OWNER_PRIVATE' in i.get('content',''):
        print('VISIBLE')
        sys.exit(0)
print('HIDDEN')
" 2>/dev/null || echo "ERROR")
SUG_MGR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$MH" ${BASE}/suggestions)
# For manager, OWNER_PRIVATE should be hidden
if [ "$SUG_MGR_STATUS" = "200" ] && [ "$HAS_OWNER_PRIVATE_MGR" = "HIDDEN" ]; then
  record "HR: suggestions (mgr, OWNER_PRIVATE hidden)" "GET" "/suggestions" "200+HIDDEN" "200+HIDDEN"
else
  record "HR: suggestions (mgr, OWNER_PRIVATE hidden)" "GET" "/suggestions" "200+HIDDEN" "${SUG_MGR_STATUS}+${HAS_OWNER_PRIVATE_MGR}"
fi

# GET suggestions as owner (OWNER_PRIVATE should be visible)
SUG_OWN=$(body -H "$OH" ${BASE}/suggestions)
HAS_OWNER_PRIVATE_OWN=$(echo "$SUG_OWN" | python3 -c "
import sys,json
r=json.load(sys.stdin)
items = r if isinstance(r, list) else r.get('suggestions', [])
for i in items:
    if i.get('visibility') == 'OWNER_PRIVATE':
        print('VISIBLE')
        sys.exit(0)
print('HIDDEN')
" 2>/dev/null || echo "ERROR")
SUG_OWN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$OH" ${BASE}/suggestions)
if [ "$SUG_OWN_STATUS" = "200" ] && [ "$HAS_OWNER_PRIVATE_OWN" = "VISIBLE" ]; then
  record "HR: suggestions (owner, OWNER_PRIVATE visible)" "GET" "/suggestions" "200+VISIBLE" "200+VISIBLE"
else
  record "HR: suggestions (owner, OWNER_PRIVATE visible)" "GET" "/suggestions" "200+VISIBLE" "${SUG_OWN_STATUS}+${HAS_OWNER_PRIVATE_OWN}"
fi

echo ""
echo "=== SECURITY TESTS (role enforcement) ==="

CODE=$(status -H "$WH" ${BASE}/dashboard/overview)
record "Security: waiter->dashboard/overview" "GET" "/dashboard/overview" "403" "$CODE"

CODE=$(status -H "$WH" ${BASE}/judge/alerts)
record "Security: waiter->judge/alerts" "GET" "/judge/alerts" "403" "$CODE"

CODE=$(status -H "$WH" ${BASE}/admin/settings)
record "Security: waiter->admin/settings" "GET" "/admin/settings" "403" "$CODE"

CODE=$(status -H "$GH" ${BASE}/inventory/purchase-requests)
record "Security: gate->inventory/purchase-requests" "GET" "/inventory/purchase-requests" "403" "$CODE"

echo ""
echo "=== ALL TESTS COMPLETE ==="
echo ""

# Count pass/fail
PASS_COUNT=$(echo -e "$RESULTS" | grep -c "| PASS |" || true)
FAIL_COUNT=$(echo -e "$RESULTS" | grep -c "| FAIL |" || true)
echo "TOTAL: $TEST_NUM tests | PASS: $PASS_COUNT | FAIL: $FAIL_COUNT"
echo ""

# Write report
cat > /home/wachira/kurahia/docs/FULL_QA_REPORT.md << REPORT_EOF
# Full QA Report — Kurahia Resort Backend

**Date:** $(date '+%Y-%m-%d %H:%M:%S')
**Server:** http://localhost:5000
**Total Tests:** ${TEST_NUM} | **PASS:** ${PASS_COUNT} | **FAIL:** ${FAIL_COUNT}

---

## Results

| # | Test | Method | Endpoint | Expected | Actual | PASS/FAIL |
|---|------|--------|----------|----------|--------|-----------|
$(echo -e "$RESULTS")

---

## Test Categories

### Owner (9 tests)
Dashboard overview, judge alerts, budget status, admin settings GET + PATCH x2, bookings, feedback, equipment.

### Manager (10 tests)
Inventory CRUD (GET, POST, PATCH, disable, enable), menu CRUD (GET, POST, PATCH), purchase requests, HR attendance, auth users.

### Gate (4 tests)
Issue band, today stats, band lookup, active bands.

### Waiter Full Flow (8 tests)
Tab creation -> order -> send -> receive -> ready -> serve -> payment -> close -> receipt.

### HR / Suggestions (4 tests)
Clock status, post MANAGEMENT suggestion, post OWNER_PRIVATE suggestion, verify visibility filtering for manager and owner.

### Security (4 tests)
Waiter blocked from owner endpoints (dashboard, judge, settings), gate blocked from inventory.

### Health (1 test)
Basic health endpoint.

---

*Generated by QA test script*
REPORT_EOF

echo "Report saved to docs/FULL_QA_REPORT.md"
