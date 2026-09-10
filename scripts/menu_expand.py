"""
scripts/menu_expand.py — widen the menu, through the real doors.

Same rule as scripts/catalogue.py: nothing here writes to the database. Every
dish is created by the person whose job it is, over HTTP, with their own login —
so if the authorship split is wrong, this script fails instead of quietly
proving nothing.

  head chef (cynthia)  food, and the bar's non-alcoholic side
  manager   (brian)    alcohol

Each dish is created, then CLASSIFIED, because an item nobody has classified is
UNTRACKED and cannot be sold — that block is deliberate. Recipes are built only
from ingredients actually in the store. Where a real dish needs something the
store does not stock (rice for pilau, wheat flour for chapati), the gap is
named in the notes rather than faked with a near-enough ingredient.

Re-runnable: an existing name 409s and is skipped, recipes replace rather
than stack.

Run:  python scripts/menu_expand.py
      python scripts/menu_expand.py --dry-run
"""
import sys
import uuid
import argparse

import requests

BASE = "http://127.0.0.1:5000"
PASSWORD = "Kurahia1!"

# department ids are looked up by name at run time — never hard-coded, because
# a fresh production database will not share this one's uuids.
DEPTS: dict[str, str] = {}


def login(username: str) -> dict:
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": username, "password": PASSWORD}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def load_departments(headers: dict) -> None:
    # same endpoint the Menu screen uses — departments are owner-editable data
    r = requests.get(f"{BASE}/auth/users/meta", headers=headers, timeout=20)
    r.raise_for_status()
    for d in r.json()["departments"]:
        DEPTS[d["name"]] = d["id"]


def inventory_index(headers: dict) -> dict[str, dict]:
    """name -> item, across every department this account may read."""
    r = requests.get(f"{BASE}/inventory/items", headers=headers, timeout=20)
    r.raise_for_status()
    return {i["name"]: i for i in r.json()}


# ── The dishes ────────────────────────────────────────────────────────────────
#
# recipe quantities are per ONE sale, in the ingredient's own stock unit.
# `missing` names what the kitchen really needs that the store has no line for.

DISHES = [
    # ---- kitchen, authored by the head chef -------------------------------
    dict(author="chef", name="Kachumbari", price="200", category="Sides",
         station="KITCHEN", dept="Kitchen",
         recipe={"Tomatoes": "0.1", "Onions": "0.05"}),

    dict(author="chef", name="Fish & Chips", price="1900", category="Mains",
         station="KITCHEN", dept="Kitchen",
         recipe={"Tilapia Fillet": "0.25", "Potatoes": "0.25", "Cooking Oil": "0.08"}),

    dict(author="chef", name="Beef Stew & Ugali", price="1100", category="Mains",
         station="KITCHEN", dept="Kitchen",
         recipe={"Beef Patties": "0.25", "Ugali Flour": "0.2", "Tomatoes": "0.1",
                 "Onions": "0.05", "Cooking Oil": "0.03"},
         missing="stewing beef — 'Beef Patties' is the only beef line in the store"),

    dict(author="chef", name="Sukuma & Chapati", price="450", category="Mains",
         station="KITCHEN", dept="Kitchen",
         recipe={"Sukuma Wiki": "0.15", "Cooking Oil": "0.03", "Onions": "0.03"},
         missing="wheat flour for the chapati — not stocked, so the chapati "
                 "itself is not deducted yet"),

    # ---- the bar's non-alcoholic side, also the head chef's ---------------
    dict(author="chef", name="Mango Juice", price="350", category="Soft Drinks",
         station="BAR", dept="Bar",
         recipe={"Mango": "0.2", "Sugar Syrup": "0.02"}),

    dict(author="chef", name="Lime Soda", price="300", category="Soft Drinks",
         station="BAR", dept="Bar",
         recipe={"Lime": "0.04", "Sugar Syrup": "0.03", "Soda Mix": "1"}),

    # ---- alcohol, the manager's list --------------------------------------
    dict(author="manager", name="Vodka (tot)", price="500", category="Cocktails",
         station="BAR", dept="Bar", alcoholic=True,
         # a 45ml tot out of a 750ml bottle — the measure catalogue.py already uses
         recipe={"Vodka": "0.06"}),

    dict(author="manager", name="Rum & Soda", price="650", category="Cocktails",
         station="BAR", dept="Bar", alcoholic=True,
         recipe={"White Rum": "0.06", "Soda 330ml": "0.5"}),
]

# Items that already exist but were never classified, so cannot be sold.
CLASSIFY_EXISTING = [
    dict(author="chef", name="Chips Masala",
         recipe={"Potatoes": "0.25", "Cooking Oil": "0.05", "Tomatoes": "0.05",
                 "Spices Mix": "0.01"}),
    dict(author="chef", name="Passion Juice",
         recipe={"Passion Fruit": "0.15", "Sugar Syrup": "0.02"}),
]


def create(item: dict, headers: dict, dry: bool) -> tuple[str | None, str]:
    body = {
        "name": item["name"], "price": item["price"], "category": item["category"],
        "prep_station": item["station"], "department_id": DEPTS[item["dept"]],
        "is_alcoholic": bool(item.get("alcoholic")),
        "idempotency_key": str(uuid.uuid4()),
    }
    if dry:
        return None, "would create"
    r = requests.post(f"{BASE}/menu/items", headers=headers, json=body, timeout=20)
    if r.status_code == 409:
        return None, "exists"
    if r.status_code != 201:
        return None, f"REFUSED {r.status_code}: {r.json().get('error', r.text)[:90]}"
    return r.json()["id"], "created"


def find_id(name: str, headers: dict) -> str | None:
    r = requests.get(f"{BASE}/menu/items", headers=headers,
                     params={"include_disabled": "true"}, timeout=20)
    r.raise_for_status()
    for i in r.json():
        if i["name"] == name:
            return i["id"]
    return None


def set_recipe(item_id: str, recipe: dict, stock: dict, headers: dict,
               notes: str | None) -> str:
    lines, unknown = [], []
    for ing, qty in recipe.items():
        if ing not in stock:
            unknown.append(ing)
            continue
        lines.append({"inventory_item_id": stock[ing]["id"], "quantity": qty})
    if unknown:
        return f"REFUSED — not in the store: {', '.join(unknown)}"
    # The key is "lines". Sending "ingredients" is accepted with a 201 and
    # writes an EMPTY recipe — which silently hands the item back to UNTRACKED.
    # This script reported "recipe set (5 ingredients)" for ten dishes that way,
    # counting what it had built locally instead of what the server kept.
    body = {"lines": lines, "idempotency_key": str(uuid.uuid4())}
    if notes:
        body["notes"] = notes
    r = requests.post(f"{BASE}/menu/items/{item_id}/recipe", headers=headers,
                      json=body, timeout=20)
    # this endpoint answers 201, not 200 — see project notes
    if r.status_code not in (200, 201):
        return f"REFUSED {r.status_code}: {r.json().get('error', r.text)[:90]}"

    # Read it back. A 201 says the request was accepted, not that the dish can
    # now be sold — only stock_tracking says that, and it is the whole point.
    # There is no GET /menu/items/<id>; the list is the way to read one back.
    check = requests.get(f"{BASE}/menu/items", headers=headers,
                         params={"include_disabled": "true"}, timeout=20)
    tracking = next((i["stock_tracking"] for i in check.json() if i["id"] == item_id), "?")
    if tracking != "RECIPE":
        return f"WROTE {len(lines)} lines but item is {tracking} — still not sellable"
    return f"recipe set ({len(lines)} lines) · RECIPE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    who = {"chef": login("cynthia.achieng"), "manager": login("brian.mwangi")}
    load_departments(who["manager"])
    stock = inventory_index(who["manager"])   # manager reads every department
    print(f"{len(DEPTS)} departments · {len(stock)} ingredients in the store\n")

    failures = 0
    for d in DISHES:
        h = who[d["author"]]
        item_id, how = create(d, h, args.dry_run)
        if how.startswith("REFUSED"):
            failures += 1
        if item_id is None and how == "exists":
            item_id = find_id(d["name"], h)
        note = f"{d['name']:<20} {d['author']:<8} {how}"
        if item_id and d.get("recipe") and not args.dry_run:
            missing = d.get("missing")
            notes = f"missing from the store: {missing}" if missing else None
            res = set_recipe(item_id, d["recipe"], stock, h, notes)
            note += f" · {res}"
            if res.startswith("REFUSED"):
                failures += 1
            if missing:
                note += f"\n{'':<20} ⚠ {missing}"
        print(note)

    print()
    for d in CLASSIFY_EXISTING:
        h = who[d["author"]]
        item_id = find_id(d["name"], h)
        if not item_id:
            print(f"{d['name']:<20} not found — skipped")
            continue
        if args.dry_run:
            print(f"{d['name']:<20} would classify")
            continue
        res = set_recipe(item_id, d["recipe"], stock, h, None)
        print(f"{d['name']:<20} {d['author']:<8} {res}")
        if res.startswith("REFUSED"):
            failures += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'done'} — {failures} refusal(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
