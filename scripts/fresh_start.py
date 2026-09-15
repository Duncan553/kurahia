"""
fresh_start.py — empty the resort, keep the keys.

Wipes every trading record and the whole catalogue so the system can be filled
with the resort's real data. What survives is the kernel that is configuration
rather than history:

    roles · departments · system settings · the WiFi allow-list
    judge baselines · conduct rules · event types
    the OWNER and the MANAGER accounts, with their profiles

Everything else goes: staff, stock lines, recipes, menu, suppliers, villas,
bookings, wristbands, tabs, charges, payments, orders, counts, movements,
purchases, shifts, clock events, leave, incidents, feedback, notifications, the
audit log and the alert history.

Why the audit log too: every row in it points at rows that no longer exist, and
a hash chain over deleted history is a chain over nothing. It restarts empty,
which is the honest state of a system that has not traded yet.

    .venv/bin/python scripts/fresh_start.py --yes

Refuses without --yes. Take a backup first:  flask system_cli backup
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                       # noqa: E402
from app.extensions import db                    # noqa: E402

KEEP_USERNAMES = {"amara.wanjiku", "brian.mwangi"}

# Deletion order matters: children before parents, or the FKs bite. Grouped the
# way the resort thinks about them rather than alphabetically.
# What SURVIVES. Everything else in the database goes.
#
# These are configuration, not history: the shape of the resort rather than
# anything that happened in it. Wiping them would mean rebuilding roles and
# departments before anyone could even sign in.
KEEP_TABLES = {
    "roles", "departments", "system_settings", "wifi_allow_list",
    "conduct_rules", "event_types", "notification_channel_configs",
    "alembic_version",
    "users", "employee_profiles",      # trimmed below to the owner and manager
}


def deletion_order(insp):
    """Every table before the ones it points at, worked out from the schema.

    Hand-written orders go stale the moment somebody adds a table, and the
    failure mode is a half-emptied database at the first foreign key. This walks
    the real foreign keys instead: a table can only be cleared once everything
    referring to it is gone.

    Self-references (users.created_by_id) are ignored — a table cannot wait for
    itself. A cycle between two tables would stop progress, so it is reported
    rather than silently skipped.
    """
    tables = [t for t in insp.get_table_names() if t not in KEEP_TABLES]
    # who points AT me
    referrers = {t: set() for t in tables}
    for t in tables:
        for fk in insp.get_foreign_keys(t):
            target = fk["referred_table"]
            if target in referrers and target != t:
                referrers[target].add(t)

    order, placed = [], set()
    while len(placed) < len(tables):
        ready = [t for t in tables
                 if t not in placed and not (referrers[t] - placed)]
        if not ready:
            remaining = [t for t in tables if t not in placed]
            raise SystemExit(f"Refused: foreign keys form a cycle across {remaining}")
        for t in sorted(ready):
            order.append(t)
            placed.add(t)
    return order


def main():
    if "--yes" not in sys.argv:
        print(__doc__)
        print("Refused: this deletes every trading record. Re-run with --yes.")
        raise SystemExit(1)

    app = create_app()
    with app.app_context():
        from sqlalchemy import text, inspect

        insp = inspect(db.engine)
        wiped = []

        for table in deletion_order(insp):
            n = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            db.session.execute(text(f"DELETE FROM {table}"))
            if n:
                wiped.append((table, n))

        # Staff last, once nothing points at them. The owner and the manager
        # stay: somebody has to be able to sign in and hire the rest.
        keep = ",".join(f"'{u}'" for u in KEEP_USERNAMES)
        gone = db.session.execute(text(
            f"SELECT COUNT(*) FROM users WHERE username NOT IN ({keep})")).scalar()
        db.session.execute(text(
            f"DELETE FROM employee_profiles WHERE user_id IN "
            f"(SELECT id FROM users WHERE username NOT IN ({keep}))"))
        db.session.execute(text(f"DELETE FROM users WHERE username NOT IN ({keep})"))
        db.session.commit()

        for table, n in wiped:
            print(f"  cleared {n:>6}  {table}")
        print(f"  cleared {gone:>6}  users (kept {', '.join(sorted(KEEP_USERNAMES))})")

        kept = db.session.execute(text("SELECT username FROM users ORDER BY username")).fetchall()
        print("\nStill here:", ", ".join(r[0] for r in kept))
        for t in ("roles", "departments", "system_settings", "wifi_allow_list"):
            if t in insp.get_table_names():
                c = db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"  {c:>3} {t}")


if __name__ == "__main__":
    main()
