"""
preflight.py — the checks that would have caught today's bugs, run on demand.

Every check below exists because something got through without it. None of them
is clever; they are all "ask the thing directly instead of assuming".

Run:  .venv/bin/python scripts/preflight.py
Exit: 0 clean, 1 if anything needs a human.
"""
import os
import ast
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []
NOTES: list[str] = []


def fail(check, msg):
    FAILURES.append(f"{check}: {msg}")


def note(msg):
    NOTES.append(msg)


# ── 1. Is the running server actually running the code on disk? ──────────────
# Bit me three times in one session. A permission change was edited, the probe
# still answered "Manager or above required.", and the obvious conclusion — the
# fix does not work — was wrong. The dev server runs with debug off and had not
# reloaded. Every "my fix did nothing" moment should check this FIRST.
def check_server_freshness():
    try:
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    m = re.search(r":5000\b.*pid=(\d+)", out)
    if not m:
        note("backend is not running on :5000 — nothing to check for staleness")
        return
    pid = m.group(1)
    try:
        started = os.path.getmtime(f"/proc/{pid}")
    except OSError:
        return

    newer = [
        p for p in (ROOT / "app").rglob("*.py")
        if p.stat().st_mtime > started
    ]
    if newer:
        names = ", ".join(sorted(p.relative_to(ROOT).as_posix() for p in newer)[:4])
        fail("stale server",
             f"{len(newer)} python file(s) changed since the server started "
             f"({names}...). Restart before believing any probe.")


# ── 2. (removed) React keys that can be null ─────────────────────────────────
# A static check was written here and deleted the same hour. TypeScript knows
# which type a variable has; a regex does not, so it flagged key={k.id} in a
# file where `id` is nullable on a DIFFERENT interface. Loosened to "nullable
# everywhere it is declared" it still produced 32 lines across 11 screens,
# almost all noise.
#
# A checker that cries wolf trains you to skip it, which is worse than no
# checker. The real detector costs nothing and has no false positives: React
# logs "Encountered two children with the same key" to the browser console.
# That belongs in the screen walk-through, not here — see SKILL.md step 3.

# ── 3. Migrations that rebuild a table ───────────────────────────────────────
# Alembic autogenerates batch_alter_table, which on SQLite copies the whole
# table and re-declares every constraint. For a nullable ADD COLUMN that risk
# buys nothing.
def check_migrations():
    # Only migrations that are NEW work. Flagging history already applied is
    # advice nobody can act on — the table was rebuilt months ago either way.
    try:
        out = subprocess.run(["git", "status", "--porcelain", "migrations/versions"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    files = [ROOT / ln[3:].strip() for ln in out.splitlines() if ln.strip().endswith(".py")]
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Read the CODE, not the prose. Stripping "#" comments was the first fix,
        # after the check flagged a migration whose only mention of the call was
        # a comment explaining why it does not use one. It happened again the
        # moment that explanation moved into the module docstring, which no
        # amount of comment-stripping will catch.
        #
        # So ask the parser what is actually called. A checker that reads its own
        # advice back as a violation gets switched off, and the real findings go
        # with it.
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        called = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        code = text  # still used for the existing_type escape hatch below
        if "batch_alter_table" in called and "add_column" in called and "existing_type" not in code:
            fail("migration",
                 f"{f.name} uses batch_alter_table for an add_column — batch mode "
                 f"rebuilds the table on SQLite. Plain op.add_column is enough.")


# ── 4. Timestamps that have not happened yet ─────────────────────────────────
# auto_clockout stamped clock_in + 10h with no upper bound. Run at 13:07 it
# wrote clock-outs at 22:20, and the latest event for those people was then a
# clock-out in the future — so every clock-in afterwards was overtaken by it
# and three staff could not use the POS.
def check_future_timestamps(app):
    from app.extensions import db
    from app.models.clock_event import ClockEvent
    from app.models.stock_movement import StockMovement
    from app.models.payment import Payment

    now = datetime.now(timezone.utc)
    for model, field, label in (
        (ClockEvent, "occurred_at_utc", "clock event"),
        (StockMovement, "timestamp_utc", "stock movement"),
        (Payment, "created_at_utc", "payment"),
    ):
        col = getattr(model, field, None)
        if col is None:
            continue
        rows = db.session.query(model).filter(col > now.replace(tzinfo=None)).count()
        if rows:
            fail("future timestamp",
                 f"{rows} {label}(s) are dated in the future — nobody can have "
                 f"done something that has not happened yet")


# ── 5. States nobody is closing ──────────────────────────────────────────────
# The same shape four times: a row one person creates and a DIFFERENT person
# must close. The closing act always costs the second person something and
# gains them nothing, so it does not happen.
def check_open_states(app):
    from app.extensions import db
    from app.models.tab import Tab, TabStatus
    from app.models.leave_request import LeaveRequest, LeaveStatus

    now = datetime.now(timezone.utc)
    stale = db.session.query(Tab).filter(
        Tab.status == TabStatus.OPEN.value,
        Tab.opened_at_utc < (now - timedelta(hours=24)).replace(tzinfo=None),
    ).count()
    if stale:
        note(f"{stale} tab(s) open longer than 24h — `flask system_cli stale-sweep` raises them")

    pending = db.session.query(LeaveRequest).filter(
        LeaveRequest.status == LeaveStatus.PENDING.value).count()
    if pending > 5:
        note(f"{pending} leave request(s) pending — somebody is waiting on an answer")


# ── 6. Wage rates, because payroll silently produces nothing without them ────
def check_payroll_ready(app):
    from app.extensions import db
    from app.models.employee_profile import EmployeeProfile

    unset = db.session.query(EmployeeProfile).filter(
        EmployeeProfile.is_active.is_(True),
        EmployeeProfile.wage_rate.is_(None)).count()
    if unset:
        note(f"{unset} active staff have no wage rate — payroll cannot pay them")


# ── 6. A screen-sized refusal wrapped around a button ────────────────────────
# RequireRole always answers with a full-page "This screen isn't yours to open"
# panel, which is right for a screen and wrong for a control. Wrapped around a
# button it drops a page-sized refusal into a header row and tells the person
# the whole screen is forbidden when only that one action is. EventsScreen did
# exactly this, and a gate lead opening Events read the entire screen as
# closed to them. IfRole is the version for a control: it renders nothing.
def check_role_gate_shape():
    pwas = ["station_pwa", "owner_pwa", "employee_pwa", "shared_ui"]
    offenders = []
    for pkg in pwas:
        src = ROOT / pkg / "src"
        if not src.exists():
            continue
        for f in src.rglob("*.tsx"):
            lines = f.read_text().splitlines()
            for i, line in enumerate(lines):
                if "<RequireRole" not in line:
                    continue
                # what does it actually wrap? first non-blank line after it
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        break
                else:
                    continue
                # A control, not a region. Layout wrappers are the legitimate use.
                if re.match(r"<(Button|button|motion\.button|a)\b", nxt.strip()):
                    offenders.append(
                        f"{f.relative_to(ROOT)}:{i + 1} wraps {nxt.strip()[:40]}")
    if offenders:
        fail("role gate shape",
             "RequireRole around a control renders a page-sized refusal — "
             "use IfRole:\n      " + "\n      ".join(offenders))


def main():
    print("preflight — the checks that would have caught the last set of bugs\n")

    check_server_freshness()
    check_migrations()
    check_role_gate_shape()

    try:
        sys.path.insert(0, str(ROOT))
        from app import create_app
        app = create_app("development")
        with app.app_context():
            check_future_timestamps(app)
            check_open_states(app)
            check_payroll_ready(app)
    except Exception as exc:                       # noqa: BLE001
        note(f"database checks skipped: {exc}")

    for n in NOTES:
        print(f"  · {n}")
    if NOTES:
        print()

    if FAILURES:
        print(f"{len(FAILURES)} thing(s) need a human:\n")
        for f in FAILURES:
            print(f"  ✗ {f}")
        sys.exit(1)

    print("nothing mechanical is wrong. That is not the same as working —")
    print("open the screen and use it.")
    sys.exit(0)


if __name__ == "__main__":
    main()
