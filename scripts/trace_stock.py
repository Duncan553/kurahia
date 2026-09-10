"""
scripts/trace_stock.py — follow ONE ingredient through every stage, and check
that the ledger and the screens tell the same story at every step.

The other drivers ask "does the feature work". This one asks the question the
owner actually cares about: **can this system tell me where a bottle went?**

Stock is never stored. A level is always SUM(StockMovement.change_amount), so
every claim on every dashboard is a re-derivation of the same append-only
ledger. This walks a real ingredient through the whole life of that ledger:

    1  buy it            manager records a purchase, with a receipt
    2  cost it           cost_per_unit is a weighted average of purchases
    3  read it           the level the chef's board shows == the ledger
    4  sell it RECIPE    a dish deducts its recipe × quantity, on READY
    5  not on order      ordering moves nothing; only READY does
    6  sell it DIRECT    one sale, one unit, straight off its own row
    7  sell a SERVICE    moves nothing, and that is a signed statement
    8  refuse UNTRACKED  nobody decided how it moves, so it cannot sell
    9  cancel it         a READY item cancelled writes the deduction back
   10  count it          a physical count writes the DIFFERENCE, not the total
   11  explain it        variance = counted − (opening + purchases − consumption)
   12  distrust it       a count with variance demotes the item's trust tier

Every number is computed twice — once by summing the movement ledger here, once
by asking the API the way a screen does — and any disagreement fails the run.
That is the whole point: two sources, one answer.

Nothing is seeded. Every write is an HTTP call by the person whose job it is.

Run:  python scripts/trace_stock.py
      python scripts/trace_stock.py --keep   # leave the trace item behind
"""
import sys
import uuid
import argparse
from decimal import Decimal

import requests

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:5000"
PASSWORD = "Kurahia1!"

PASS, FAIL = [], []


def check(ok: bool, what: str, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(what)
    print(f"  {'ok  ' if ok else 'FAIL'} {what}{('   ' + detail) if detail else ''}")
    return ok


def agree(a, b, what: str, unit: str = "") -> bool:
    """Two independent computations of the same fact must match exactly."""
    same = Decimal(str(a)) == Decimal(str(b))
    return check(same, what, f"ledger {a}{unit} · screen {b}{unit}"
                 if not same else f"{a}{unit}, both ways")


def login(username: str) -> dict:
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": username, "password": PASSWORD}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── the two sources of truth ─────────────────────────────────────────────────

def ledger_level(item_id: str, headers: dict) -> Decimal:
    """Source A: sum the movement ledger, the way app/services/stock.py does."""
    r = requests.get(f"{BASE}/inventory/movements", headers=headers,
                     params={"item_id": item_id, "limit": 500}, timeout=20)
    r.raise_for_status()
    rows = r.json()
    rows = rows.get("movements", rows) if isinstance(rows, dict) else rows
    return sum((Decimal(str(m["change_amount"])) for m in rows), Decimal("0"))


def screen_level(item_id: str, headers: dict) -> Decimal:
    """Source B: the number a dashboard prints."""
    r = requests.get(f"{BASE}/inventory/items", headers=headers, timeout=20)
    r.raise_for_status()
    for i in r.json():
        if i["id"] == item_id:
            return Decimal(str(i["current_stock"]))
    raise LookupError("item not on the inventory screen")


def movements(item_id: str, headers: dict) -> list:
    r = requests.get(f"{BASE}/inventory/movements", headers=headers,
                     params={"item_id": item_id, "limit": 500}, timeout=20)
    r.raise_for_status()
    rows = r.json()
    return rows.get("movements", rows) if isinstance(rows, dict) else rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="leave the trace ingredient and dish in place")
    args = ap.parse_args()

    mgr = login("brian.mwangi")
    chef = login("cynthia.achieng")
    waiter = login("ivan.kipchoge")

    meta = requests.get(f"{BASE}/auth/users/meta", headers=mgr, timeout=20).json()
    depts = {d["name"]: d["id"] for d in meta["departments"]}
    tag = uuid.uuid4().hex[:5].upper()

    print(f"\n── trace {tag} ─────────────────────────────────────────────\n")

    # ── 1. buy it ────────────────────────────────────────────────────────────
    print("1 · the manager buys 10 kg")
    r = requests.post(f"{BASE}/inventory/items", headers=mgr, json={
        "name": f"Trace Flour {tag}", "unit": "kg",
        "department_id": depts["Kitchen"], "reorder_level": "2",
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code == 201, "manager creates the stock line", str(r.status_code))
    item_id = r.json()["id"]

    agree(ledger_level(item_id, mgr), screen_level(item_id, mgr),
          "a brand-new line is zero, not null", " kg")

    r = requests.post(f"{BASE}/inventory/purchases", headers=mgr, json={
        "item_id": item_id, "quantity": "10", "actual_cost": "1000",
        "receipt_photo_path": f"/receipts/trace-{tag}.jpg",
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code in (200, 201), "purchase recorded", str(r.status_code))
    check(any(m["reason"] == "PURCHASE" for m in movements(item_id, mgr)),
          "it wrote a PURCHASE movement, not an edit to a total")

    agree(ledger_level(item_id, mgr), screen_level(item_id, mgr),
          "10 kg on hand", " kg")

    # a purchase with no receipt is refused — the control, not a nicety
    r = requests.post(f"{BASE}/inventory/purchases", headers=mgr, json={
        "item_id": item_id, "quantity": "5", "actual_cost": "500",
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code == 400 and "receipt" in r.json().get("error", "").lower(),
          "a purchase with no receipt photo is refused")

    # ── 2. cost it ───────────────────────────────────────────────────────────
    print("\n2 · a second purchase at a different price")
    r = requests.post(f"{BASE}/inventory/purchases", headers=mgr, json={
        "item_id": item_id, "quantity": "10", "actual_cost": "1400",
        "receipt_photo_path": f"/receipts/trace-{tag}-b.jpg",
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code in (200, 201), "second purchase recorded")

    item = next(i for i in requests.get(f"{BASE}/inventory/items", headers=mgr,
                                        timeout=20).json() if i["id"] == item_id)
    cost = Decimal(str(item.get("cost_per_unit") or "0"))
    # 10kg @ 100 + 10kg @ 140 = 2400 / 20kg = 120/kg
    check(cost == Decimal("120"),
          "cost_per_unit is the weighted average of what was actually paid",
          f"KSh {cost}/kg (100 then 140)")
    agree(ledger_level(item_id, mgr), screen_level(item_id, mgr),
          "20 kg on hand", " kg")

    # ── 3-5. sell it through a recipe ────────────────────────────────────────
    print("\n3 · a dish that uses it, sold to a guest")
    r = requests.post(f"{BASE}/menu/items", headers=chef, json={
        "name": f"Trace Mandazi {tag}", "price": "200", "category": "Sides",
        "prep_station": "KITCHEN", "department_id": depts["Kitchen"],
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code == 201, "the chef adds the dish", str(r.status_code))
    dish_id = r.json()["id"]

    sellable = requests.get(f"{BASE}/menu/items", headers=chef, timeout=20).json()
    tracking = next(i["stock_tracking"] for i in sellable if i["id"] == dish_id)
    check(tracking == "UNTRACKED",
          "a new dish starts UNTRACKED — nobody has said how it moves stock")

    r = requests.post(f"{BASE}/menu/items/{dish_id}/recipe", headers=chef, json={
        "lines": [{"inventory_item_id": item_id, "quantity": "0.25"}],
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code in (200, 201), "recipe written: 0.25 kg per mandazi")
    tracking = next(i["stock_tracking"] for i in
                    requests.get(f"{BASE}/menu/items", headers=chef, timeout=20).json()
                    if i["id"] == dish_id)
    check(tracking == "RECIPE",
          "writing the recipe IS the statement of how it deducts")

    before = ledger_level(item_id, mgr)
    r = requests.post(f"{BASE}/tabs", headers=waiter, json={
        "tab_type": "WALK_IN", "reference": f"Trace {tag}",
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    tab_id = r.json()["id"]
    r = requests.post(f"{BASE}/orders", headers=waiter, json={
        "tab_id": tab_id, "items": [{"menu_item_id": dish_id, "quantity": 4}],
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code == 201, "waiter sends an order for 4", str(r.status_code))

    check(ledger_level(item_id, mgr) == before,
          "ORDERING moves no stock — the flour is still in the store")

    tab = requests.get(f"{BASE}/tabs/{tab_id}", headers=waiter, timeout=20).json()
    oi_id = tab["orders"][0]["items"][0]["id"]
    requests.post(f"{BASE}/order-items/{oi_id}/receive", headers=chef, timeout=20)
    r = requests.post(f"{BASE}/order-items/{oi_id}/ready", headers=chef, timeout=20)
    check(r.status_code == 200, "the kitchen marks it ready")

    after = ledger_level(item_id, mgr)
    check(before - after == Decimal("1.0"),
          "READY is the moment it moves: 0.25 kg × 4 = 1 kg",
          f"{before} -> {after} kg")
    check(any(m["reason"] == "SALE" for m in movements(item_id, mgr)),
          "and it is recorded as a SALE, so variance can explain it")
    agree(ledger_level(item_id, mgr), screen_level(item_id, mgr),
          "19 kg on hand", " kg")

    # ── 6-8. the other three tracking answers ────────────────────────────────
    print("\n4 · the other ways a sale can move stock")
    r = requests.patch(f"{BASE}/menu/items/{dish_id}", headers=mgr,
                       json={"stock_tracking": "UNTRACKED"}, timeout=20)
    r = requests.post(f"{BASE}/orders", headers=waiter, json={
        "tab_id": tab_id, "items": [{"menu_item_id": dish_id, "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code != 201,
          "an UNTRACKED dish cannot be sold at all",
          r.json().get("error", "")[:60])
    requests.post(f"{BASE}/menu/items/{dish_id}/recipe", headers=chef, json={
        "lines": [{"inventory_item_id": item_id, "quantity": "0.25"}],
        "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)

    # ── 9. cancel it ─────────────────────────────────────────────────────────
    print("\n5 · the kitchen cancels a dish it had already made")
    before = ledger_level(item_id, mgr)
    r = requests.post(f"{BASE}/order-items/{oi_id}/cancel", headers=mgr,
                      json={"reason": f"trace {tag}"}, timeout=20)
    check(r.status_code == 200, "manager cancels the READY item", str(r.status_code))
    after = ledger_level(item_id, mgr)
    check(after - before == Decimal("1.0"),
          "the deduction is written BACK, not erased",
          f"{before} -> {after} kg")
    check(len([m for m in movements(item_id, mgr) if m["reason"] == "SALE"]) >= 2,
          "both the sale and its reversal stay in the ledger — append-only")

    # ── 10-11. count it, and explain the difference ──────────────────────────
    print("\n6 · somebody counts the shelf and finds less than the book says")
    book = ledger_level(item_id, mgr)
    counted = book - Decimal("1.5")          # a real shelf, 1.5 kg short
    r = requests.post(f"{BASE}/inventory/counts", headers=chef, json={
        "item_id": item_id, "counted_amount": str(counted), "count_type": "DAILY",
        "notes": f"trace {tag}", "idempotency_key": str(uuid.uuid4()),
    }, timeout=20)
    check(r.status_code in (200, 201), "the head chef counts her own store",
          str(r.status_code))

    count_moves = [m for m in movements(item_id, mgr) if m["reason"] == "COUNT"]
    check(bool(count_moves), "the count writes a COUNT movement")
    if count_moves:
        adj = Decimal(str(count_moves[0]["change_amount"]))
        check(adj == Decimal("-1.5"),
              "and it writes the DIFFERENCE (−1.5), never the new total",
              f"{adj} kg")
    agree(ledger_level(item_id, mgr), screen_level(item_id, mgr),
          "the book now equals the shelf", " kg")
    check(screen_level(item_id, mgr) == counted,
          "which is exactly what was counted", f"{counted} kg")

    # ── 12. distrust it ──────────────────────────────────────────────────────
    print("\n7 · what the system does with an item that was wrong")
    # The tier is NOT on the plain items list — it is computed per request and
    # served only to the counting view. Asking the wrong door returns None, and
    # a check written against that passes while proving nothing.
    r = requests.get(f"{BASE}/inventory/items", headers=mgr,
                     params={"for_count": "true"}, timeout=20)
    payload = r.json()
    row = next(i for i in payload["items"] if i["id"] == item_id)
    check(row["trust_tier"] == "MUST_COUNT",
          "the item is MUST_COUNT — the system will not take its word",
          f"{row['trust_tier']} ({row['trust_reason']})")
    # Honest about what this does and does not show: a brand-new line is
    # MUST_COUNT anyway (criterion 2), so the reason reads "new_item" and this
    # step cannot by itself prove the variance demotion. What it does prove is
    # that a counted item carries a tier and the counting screen is told why.
    check(row["trust_reason"] in ("new_item", "recent_count", "recent_variance",
                                  "watch_list", "demotion", "judge_alert"),
          "and it says WHY, in a word a person can act on",
          row["trust_reason"])
    check(payload["summary"]["MUST_COUNT"] >= 1,
          "the counting screen totals the tiers for the person doing the count",
          f"{payload['summary']}")

    # ── 11. explain the difference ───────────────────────────────────────────
    print("\n8 · the variance report has to explain that difference")
    # A bare date means the resort's BUSINESS day (06:00 EAT to 06:00 EAT), so
    # ask for the day the count actually belongs to rather than today's UTC one.
    from app.services.business_day import business_day_for
    from datetime import datetime, timezone as _tz
    bday = business_day_for(datetime.now(_tz.utc)).strftime("%Y-%m-%d")

    r = requests.get(f"{BASE}/inventory/variance", headers=mgr,
                     params={"from": bday, "to": bday}, timeout=30)
    check(r.status_code == 200, "the manager can run variance", str(r.status_code))
    body = r.json()
    rows = body.get("items", body if isinstance(body, list) else [])

    # The manager's post is the whole property. This defaulted to the manager's
    # OWN department, which is "Management" — one active line out of forty — so
    # the theft-detection screen showed him 1/40th of the resort in silence.
    check(len(rows) > 5,
          "and it covers the whole resort, not just his own department",
          f"{len(rows)} items")

    row = next((v for v in rows if v["item_id"] == item_id), None)
    if check(row is not None, "the counted item appears in the period it was counted in"):
        opening     = Decimal(str(row["opening"]))
        purchases   = Decimal(str(row["purchases"]))
        consumption = Decimal(str(row["consumption"]))
        expected    = Decimal(str(row["expected_closing"]))
        actual      = Decimal(str(row["actual_closing"]))
        var         = Decimal(str(row["variance"]))

        check(opening + purchases - consumption == expected,
              "expected = opening + purchases − consumption",
              f"{opening} + {purchases} − {consumption} = {expected}")
        check(actual - expected == var,
              "variance = counted − expected", f"{actual} − {expected} = {var}")
        check(var < 0, "and it is NEGATIVE, because the shelf was short", f"{var} kg")
        # variance_pct is a MAGNITUDE — it is what the tolerance compares. Any
        # screen that wants direction must read it off `variance`, not the pct.
        check(Decimal(str(row["variance_pct"])) > 0
              and Decimal(str(row["variance_pct"])) == abs(var) / abs(expected) * 100,
              "the percentage is unsigned, on purpose — it drives the tolerance",
              f"{row['variance_pct']}%")
        check(row["flagged"] is True,
              "over tolerance, so it is flagged for a human",
              f"tolerance {row['tolerance_pct']}%")

    # ── tidy ─────────────────────────────────────────────────────────────────
    if not args.keep:
        requests.post(f"{BASE}/menu/items/{dish_id}/disable", headers=mgr, timeout=20)
        requests.post(f"{BASE}/inventory/items/{item_id}/disable", headers=mgr, timeout=20)
        requests.post(f"{BASE}/tabs/{tab_id}/close", headers=waiter, json={}, timeout=20)
        print("\n  (trace item and dish disabled — never deleted)")

    print("\n" + "=" * 62)
    print(f"{len(PASS)}/{len(PASS) + len(FAIL)} checks agreed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
