"""
scripts/flag_liquor.py — mark which stock lines are liquor, as the manager.

`InventoryItem.is_alcoholic` is what lets the menu guards tell a bottle of rum
from a bottle of sugar syrup. Until a line is flagged, anyone who may author
bar drinks may pour it into a recipe — which is how a "Virgin Mojito" could
quietly deduct White Rum.

Nothing here writes to the database. Every flag is a PATCH by
`brian.mwangi` (manager), because the flag is a licensing statement and the
manager is who answers for it. Re-runnable: it only PATCHes lines that are
wrong, and prints what it changed.

The list is deliberately explicit rather than keyword-matched. "Soda Mix" and
"Sugar Syrup" live in the same department as the spirits, and a rule like
`"wine" in name` would flag a wine GLASS or miss `Spirit bottle 2a27`. A human
reads this list; a regex would not.

Run:  python scripts/flag_liquor.py
      python scripts/flag_liquor.py --dry-run
"""
import sys
import argparse

import requests

BASE = "http://127.0.0.1:5000"

# Every stock line at Waterfront that contains alcohol. Names carry the random
# suffixes the purchase drivers generate; match is exact, on purpose.
LIQUOR = {
    "Tusker Beer",
    "Guinness",
    "Vodka",
    "White Rum",
    "White Wine",
    "Case of Tusker cans ab51",
    "Crate of Tusker f187",
    "Case of wine d4a8",
    "Spirit bottle 2a27",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    r = requests.post(f"{BASE}/auth/login",
                      json={"username": "brian.mwangi", "password": "Kurahia1!"}, timeout=20)
    r.raise_for_status()
    mgr = {"Authorization": f"Bearer {r.json()['access_token']}"}

    items = requests.get(f"{BASE}/inventory/items", headers=mgr, timeout=20).json()
    by_name = {i["name"]: i for i in items}

    missing = LIQUOR - set(by_name)
    if missing:
        # Expect the four Management-department "Case of …"/"Crate of …" lines
        # here: they are disabled purchase-driver litter, and /inventory/items
        # only lists active stock. A recipe cannot reference an inactive item
        # either (pos/menu.py checks is_active), so they need no flag.
        print("not active in the store (skipped):", ", ".join(sorted(missing)))

    changed = failed = 0
    for name in sorted(LIQUOR & set(by_name)):
        item = by_name[name]
        if item.get("is_alcoholic"):
            print(f"  {name:<28} already flagged")
            continue
        if args.dry_run:
            print(f"  {name:<28} would flag")
            continue
        resp = requests.patch(f"{BASE}/inventory/items/{item['id']}", headers=mgr,
                              json={"is_alcoholic": True}, timeout=20)
        if resp.status_code != 200:
            print(f"  {name:<28} REFUSED {resp.status_code}: {resp.text[:80]}")
            failed += 1
            continue
        changed += 1
        print(f"  {name:<28} flagged as liquor")

    # Read back — a 200 is not proof the flag stuck.
    if not args.dry_run:
        after = {i["name"]: i.get("is_alcoholic") for i in
                 requests.get(f"{BASE}/inventory/items", headers=mgr, timeout=20).json()}
        wrong = [n for n in (LIQUOR & set(after)) if not after[n]]
        stray = [n for n, a in after.items() if a and n not in LIQUOR]
        if wrong:
            print("\nSTILL NOT FLAGGED:", ", ".join(wrong))
            failed += len(wrong)
        if stray:
            print("flagged but not on the list:", ", ".join(stray))

    print(f"\n{changed} flagged, {failed} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
