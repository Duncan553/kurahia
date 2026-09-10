"""
scripts/retire_stale_pings.py — clear "ready for pickup" alerts whose item is done.

From now on `app/pos/orders.py` retires the ping when an item is served or
cancelled. This clears the BACKLOG left before that: alerts sitting on waiters'
Tables screens for items served days ago, on tables that are closed and paid.
On the dev database that backlog buries the actual tables under a wall of
bells.

It marks read only pings whose order item has left READY — nothing a waiter is
genuinely still waiting to collect is touched. Each one goes through
`POST /notifications/<id>/mark-read` as the waiter it belongs to, because that
is the endpoint that owns the state.

Run:  python scripts/retire_stale_pings.py --dry-run
      python scripts/retire_stale_pings.py --apply
"""
import sys
import time
import argparse
from collections import Counter

sys.path.insert(0, ".")

import requests                                              # noqa: E402
from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models.notification import Notification, NotificationStatus   # noqa: E402
from app.models.order_item import OrderItem, OrderItemStatus  # noqa: E402
from app.models.user import User                             # noqa: E402

BASE = "http://127.0.0.1:5000"
PASSWORD = "Kurahia1!"

# Everything that means "this errand is over".
DONE = {OrderItemStatus.SERVED.value, OrderItemStatus.CANCELLED.value}


def find_stale():
    rows = (db.session.query(Notification)
            .filter_by(reference_type="order_ready")
            .filter(Notification.status != NotificationStatus.READ.value)
            .all())
    stale = []
    for n in rows:
        oi = db.session.get(OrderItem, n.reference_id) if n.reference_id else None
        # An orphaned ping (item deleted) is also stale; a still-READY one is not.
        if oi is None or oi.status in DONE:
            stale.append((n, oi))
    return rows, stale


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.apply or args.dry_run):
        print("Pass --dry-run to look, --apply to clear.")
        return 2

    app = create_app("development")
    with app.app_context():
        rows, stale = find_stale()
        by_user = Counter()
        for n, oi in stale:
            u = db.session.get(User, n.recipient_user_id)
            by_user[u.username if u else "?"] += 1

        print(f"{len(rows)} unread pickup ping(s); {len(stale)} refer to an item "
              f"already served or cancelled")
        for who, count in by_user.most_common():
            print(f"  {who:<18} {count}")
        if not stale:
            print("nothing to clear")
            return 0
        if args.dry_run:
            print("\nDRY RUN — nothing changed")
            return 0

        # group by recipient so each waiter's own token clears their own inbox
        targets: dict[str, list[str]] = {}
        skipped_inactive = Counter()
        for n, _ in stale:
            u = db.session.get(User, n.recipient_user_id)
            if not u:
                continue
            if not u.is_active:
                # A disabled account cannot sign in, by design — and nobody is
                # reading its inbox either. Report, don't fail.
                skipped_inactive[u.username] += 1
                continue
            targets.setdefault(u.username, []).append(n.id)
        for who, count in skipped_inactive.items():
            print(f"  {who:<18} {count} left as-is (account disabled — nobody reads it)")

    cleared = failed = 0
    for username, ids in targets.items():
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": username, "password": PASSWORD}, timeout=20)
        if r.status_code == 429:
            # Login is rate-limited 5/min per IP. Signing in as several waiters
            # in a row hits it, and a 429 is a "wait", not a "no".
            print(f"{username:<18} rate-limited — waiting 65s and trying once more")
            time.sleep(65)
            r = requests.post(f"{BASE}/auth/login",
                              json={"username": username, "password": PASSWORD}, timeout=20)
        if r.status_code != 200:
            print(f"{username}: cannot sign in ({r.status_code}) — skipped {len(ids)}")
            failed += len(ids)
            continue
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        for nid in ids:
            resp = requests.post(f"{BASE}/notifications/{nid}/mark-read", headers=h, timeout=20)
            if resp.status_code == 200:
                cleared += 1
            else:
                failed += 1
        print(f"{username:<18} {len(ids)} ping(s) processed")

    # read back — a 200 per call is not proof the inbox is clear
    with create_app("development").app_context():
        _, still = find_stale()
    print(f"\ncleared {cleared}, {failed} failed, {len(still)} stale ping(s) remaining")
    return 1 if (failed or still) else 0


if __name__ == "__main__":
    sys.exit(main())
