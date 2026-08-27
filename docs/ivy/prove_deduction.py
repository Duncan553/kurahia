#!/usr/bin/env python3
"""
Prove the stock deduction end to end, live, in one run.

The capture agent recorded stock_before == stock_after with no sale in between,
which proves nothing either way. This sells one Grilled Tilapia against band
#17's tab and watches the ingredient move, so the document can say it honestly.

Expected: Tilapia Fillet drops by exactly 0.35 kg — the recipe line for one dish.

Tokens are cached to disk: /auth/login allows 5 per minute per address, and this
script is run repeatedly while being written. Tripping that limit is the limiter
working, so wait it out rather than working around it.
"""
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "http://localhost:5000"
PW = "Kurahia1!"
CACHE = Path(__file__).parent / ".tokens.json"

TAB = "14055156-872b-4998-810c-d458cd560fd9"          # band #17's tab
DISH = "e71ad0c2-af3e-4ca6-9721-23cdf7717202"          # Grilled Tilapia, KSh 1,800
FILLET = "469e66cc-3087-4996-be61-85f8bf86c6d5"        # Tilapia Fillet, kg


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def login(user):
    if user in _cache:
        return _cache[user]
    for _ in range(6):
        st, b = call("POST", "/auth/login", body={"username": user, "password": PW})
        if st == 200:
            _cache[user] = b["access_token"]
            CACHE.write_text(json.dumps(_cache))
            return _cache[user]
        if st != 429:
            raise SystemExit(f"login failed for {user}: {st} {b}")
        print(f"  rate limited on {user}, waiting 65s…")
        time.sleep(65)
    raise SystemExit(f"{user} stayed rate limited")


def stock(token):
    """The derived level: the sum of every movement ever recorded for this item."""
    st, b = call("GET", f"/inventory/movements/summary?item_id={FILLET}", token)
    assert st == 200, b
    return b["totals"]["net"]


mgr = login("brian.mwangi")        # manager — only manager+ may read the ledger
chef = login("cynthia.achieng")    # head chef — owns the kitchen queue
waiter = login("ivan.kipchoge")    # waiter — takes the order

before = stock(mgr)
print(f"stock BEFORE     : {before} kg")

st, order = call("POST", "/orders", waiter, {
    "tab_id": TAB, "idempotency_key": str(uuid.uuid4()),
    "items": [{"menu_item_id": DISH, "quantity": 1}],
})
assert st == 201, order
print(f"order created    : {st}  {order['id'][:8]}  status={order['status']}")

st, _ = call("POST", f"/orders/{order['id']}/send", waiter, {"idempotency_key": str(uuid.uuid4())})
print(f"sent to kitchen  : {st}")

# There is no GET /orders/<id>. The chef finds the ticket on the kitchen queue,
# which is exactly how it works on the floor.
st, q = call("GET", "/kitchen/queue", chef)
rows = q if isinstance(q, list) else q.get("items") or q.get("queue") or []
mine = [r for r in rows if r.get("order_id") == order["id"]]
assert mine, f"ticket not on the kitchen queue (queue held {len(rows)} rows)"
oi = mine[0]["order_item_id"]
print(f"on kitchen queue : {mine[0]["menu_item"]}")

st, _ = call("POST", f"/order-items/{oi}/receive", chef, {"idempotency_key": str(uuid.uuid4())})
print(f"chef received    : {st}")
# READY is the moment consumption fires for anything with a prep station.
st, ready = call("POST", f"/order-items/{oi}/ready", chef, {"idempotency_key": str(uuid.uuid4())})
print(f"marked READY     : {st}")

after = stock(mgr)
print(f"stock AFTER      : {after} kg")

moved = float(before) - float(after)
ok = abs(moved - 0.35) < 1e-6
print(f"\nmoved            : {moved:.4f} kg   (recipe line says 0.3500)")
print("VERDICT          :", "DEDUCTED CORRECTLY" if ok else f"UNEXPECTED — {ready}")

json.dump({"dish": "Grilled Tilapia", "ingredient": "Tilapia Fillet",
           "before": before, "after": after, "moved": f"{moved:.4f}",
           "expected": "0.3500", "correct": ok},
          open("/home/wachira/kurahia/docs/ivy/deduction_proof.json", "w"), indent=1)
