"""
scripts/pwa_contract.py — does every screen's API call actually resolve?

The failure this exists to catch is the quiet one. A PWA screen asks for a
path, the backend has no such route (or the Vite proxy never forwards it), and
the screen renders empty. Nothing throws, nothing is logged, and the tablet
just shows nothing where the numbers should be. It has bitten this project
twice through PROXIED_PATHS alone.

So: read every api.get/post/patch/delete call out of the three PWAs' source,
resolve each one against the real Flask URL map, and report any that no route
can serve. Also flags GET paths that answer 5xx for the owner, since a screen
that 500s is as dead as one that 404s.

Run:  python scripts/pwa_contract.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models.user import User                             # noqa: E402
from flask_jwt_extended import create_access_token            # noqa: E402
from werkzeug.routing import RequestRedirect                  # noqa: E402
from werkzeug.exceptions import MethodNotAllowed, NotFound    # noqa: E402

APPS = ["employee_pwa/src", "owner_pwa/src", "station_pwa/src", "shared_ui/src"]

# api.get('/path')  api.post(`/path/${id}`)  axios.patch("/path")
#
# The quote that OPENS the literal is captured and reused as the terminator.
# A naive [^`'"]+ stops dead on the apostrophes inside a template ternary —
# `/menu/items/${id}/${active ? 'disable' : 'enable'}` — and reports a fake
# broken route. That was my first run: 7 "missing" paths, all my own bug.
#
# The `<...>` is the OTHER thing that blinded the first version. Screens call
# api.get<OverviewData>('/dashboard/overview') — a TypeScript generic between
# the method and the paren. Requiring "(" straight after "get" hid almost every
# typed GET in the codebase: the scan found 8 of them across three dashboard
# apps and looked plausible enough to believe.
CALL = re.compile(
    r"""(?:api|axios)\.(get|post|patch|put|delete)\s*(?:<[^(]*?>)?\s*\(\s*(['"`])(.*?)\2""",
    re.S)


def strip_templates(raw: str) -> list[str]:
    """`${...}` -> "1". A ternary inside one means the call has TWO real
    endpoints (disable/enable), so return both rather than guessing."""
    out = [raw]
    while True:
        expanded = []
        changed = False
        for s in out:
            m = re.search(r"\$\{([^{}]*)\}", s)
            if not m:
                expanded.append(s)
                continue
            changed = True
            inner = m.group(1)
            # a ternary picking between two literal path segments
            arms = re.findall(r"['\"]([^'\"]*)['\"]", inner)
            for value in (arms if len(arms) >= 2 else ["1"]):
                expanded.append(s[:m.start()] + value + s[m.end():])
        out = expanded
        if not changed:
            return out


def scan():
    """path -> {method: {files}}. One entry per distinct route the UI needs."""
    found = {}
    for root in APPS:
        for f in Path(root).rglob("*.ts*"):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for method, _quote, raw in CALL.findall(text):
                for candidate in strip_templates(raw):
                    path = candidate.split("?")[0].rstrip("/")
                    if not path.startswith("/"):
                        continue      # a relative or computed URL, not a route
                    (found.setdefault(path, {})
                          .setdefault(method.upper(), set()).add(str(f)))
    return found


# ── Permission contract ──────────────────────────────────────────────────────
# The nav check above proves a tile's route RESOLVES. It cannot prove the person
# being offered the tile may OPEN it — and that gap swallowed three bugs in one
# session: the Tables list, the stock-count gate, and front desk's Cash tile,
# which answered "This screen isn't yours to open" from her own nav bar.
#
# Both halves of that rule are written down in source and can be compared:
#
#   the OFFER    NAV_ITEMS[].visible(level, dept)   in layouts/AppLayout.tsx
#   the GUARD    <RequireRole minLevel={N}>         wrapping the screen's render
#
# So: work out the LOWEST role level at which a tile can still appear, look up
# the screen that route lands on, and read the level that screen demands. If the
# screen demands more than the tile's floor, somebody gets a button that refuses
# them. That is the whole check.

def _balanced(s):
    """True if every paren in `s` opens before it closes and all of them close.
    Used to decide whether a leading '(' really wraps the WHOLE expression —
    '(a) && (b)' starts with '(' and ends with ')' but the two do not pair, and
    stripping them would silently mangle the expression into 'a) && (b'."""
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _split_top(expr, op):
    """Split on `op` only at paren depth 0. `deptIs(d, 'a', 'b') && l >= 3`
    must split into two conjuncts, not shatter inside the argument list."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(expr):
        ch = expr[i]
        if depth == 0 and expr.startswith(op, i):
            parts.append(cur)
            cur = ""
            i += len(op)
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        cur += ch
        i += 1
    parts.append(cur)
    return [p.strip() for p in parts]


LEVEL_GE = re.compile(r"^(?:l|level)\s*>=\s*(\d+)$")


def offered_level(expr):
    """The lowest role_level that can still see this tile.

    OR takes the MINIMUM — either branch alone is enough to show the tile, so
    the weakest branch sets the floor. That is precisely the Cash bug:
    `deptIs(d,'front desk') || l >= 5` floors at 0, because a level-1 front-desk
    staffer satisfies the left branch on its own.

    AND takes the MAXIMUM — every conjunct must hold, so the strictest wins.
    Anything that is not a level test (deptIs, a capability flag) contributes 0:
    it says nothing about rank, so it cannot raise the floor."""
    expr = " ".join(expr.split()).rstrip(",").strip()
    while expr.startswith("(") and expr.endswith(")") and _balanced(expr[1:-1]):
        expr = expr[1:-1].strip()
    ors = _split_top(expr, "||")
    if len(ors) > 1:
        return min(offered_level(o) for o in ors)
    ands = _split_top(expr, "&&")
    if len(ands) > 1:
        return max(offered_level(a) for a in ands)
    m = LEVEL_GE.match(expr)
    return int(m.group(1)) if m else 0


def _nav_entries(text):
    """Every `{...}` object literal inside the nav array, as raw text.
    Brace-depth scanning rather than a regex because the entries carry comments
    and trailing commas; none of them nest braces, but depth costs nothing."""
    # Match through to the array's OWN bracket. Searching for the next "["
    # after the name lands on the one in the TYPE — `NavItem[]` — which opens
    # and closes immediately, so the scan below read an empty array and the
    # whole check passed by examining nothing. It reported "all match" for
    # three apps while parsing zero tiles.
    m = re.search(r"(?:NAV_ITEMS|SIDEBAR_ITEMS)\s*:\s*NavItem\[\]\s*=\s*\[", text)
    if not m:
        return []
    i = m.end() - 1
    depth, end = 0, len(text)
    for j in range(i, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                end = j
                break
    body = text[i + 1:end]
    out, depth, start = [], 0, None
    for j, ch in enumerate(body):
        if ch == "{":
            if depth == 0:
                start = j
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(body[start + 1:j])
                start = None
    return out


def screen_guard(pkg, screen_name):
    """The level a screen demands of whoever lands on it, read from the
    RequireRole that wraps its ENTIRE render — `return ( <RequireRole ...`.

    Nested ones are deliberately ignored: EventsScreen wraps only its "Create
    Event" BUTTON in RequireRole minLevel={5}, and the screen itself is open to
    everyone. Treating that as a whole-screen guard would report the Events tile
    as broken for every waiter in the resort, which is the opposite of true."""
    for f in (Path(pkg) / "src").rglob(f"{screen_name}.tsx"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"return\s*\(\s*<RequireRole\b([^>]*)>", text)
        if not m:
            return 0, None
        attrs = m.group(1)
        # `allow` is a CAPABILITY predicate (can_count_stock), and the component
        # lets it override the level entirely. No rank can express the rule, so
        # no rank comparison is honest here — say so instead of guessing.
        if "allow=" in attrs:
            return 0, "capability"
        lvl = re.search(r"minLevel=\{(\d+)\}", attrs)
        return (int(lvl.group(1)) if lvl else 0), None
    return 0, None


def permission_scan():
    """Compare every tile's floor against its screen's guard. Returns the breaks."""
    print("\npermission contract, per app:")
    print("  (compares each nav tile's visibility floor against the RequireRole")
    print("   guarding the screen it lands on. It cannot see the API's own rule —")
    print("   the Tables 403 was a backend disagreement and would not show here.)")
    breaks = []
    for pkg in ("employee_pwa", "owner_pwa", "station_pwa"):
        layout = Path(pkg) / "src" / "layouts" / "AppLayout.tsx"
        main_tsx = Path(pkg) / "src" / "main.tsx"
        if not (layout.exists() and main_tsx.exists()):
            continue
        # route path -> the screen component mounted there
        routes = dict(re.findall(r"path:\s*'([^']+)'\s*,\s*element:\s*<(\w+)",
                                 main_tsx.read_text()))
        bad, checked, unmapped = [], 0, []
        for entry in _nav_entries(layout.read_text()):
            p = re.search(r"path:\s*'([^']+)'", entry)
            if not p:
                continue
            path = p.group(1)
            v = re.search(r"visible:\s*\([^)]*\)\s*=>\s*(.+)", entry, re.S)
            # No `visible` at all (owner_pwa's sidebar) = shown to everyone who
            # reaches this app, so the floor is 0 — the strictest reading.
            floor = offered_level(v.group(1)) if v else 0
            screen = routes.get(path)
            if not screen:
                unmapped.append(path)
                continue
            need, kind = screen_guard(pkg, screen)
            checked += 1
            if kind == "capability":
                continue
            if need > floor:
                bad.append((path, screen, floor, need))
        status = ("all match their screen's guard" if not bad else
                  f"{len(bad)} MISMATCH")
        print(f"  {pkg:14} {checked:>3} tile(s), {status}")
        for path, screen, floor, need in bad:
            print(f"      {path}  offered from level {floor}, "
                  f"{screen} demands {need}")
        if unmapped:
            print(f"      (note: {len(unmapped)} tile path(s) not in the route "
                  f"table: {', '.join(unmapped)})")
        breaks += [(pkg, b[0]) for b in bad]
    return breaks


# ── Orphan endpoints ─────────────────────────────────────────────────────────
# The scan at the top of this file asks: does everything the UI calls exist?
# This asks the OPPOSITE, which is the question that actually loses features:
# does everything that exists have a door?
#
# GET /receipts — the central receipts search, with date and reference filters,
# built and tested in Phase A — had no caller in any of the three apps. Nobody
# noticed for months, because nothing fails. The endpoint answers perfectly; no
# screen ever asks it. The single-bill version (GET /receipts/<id>) had the same
# gap until FolioScreen was written for it.
#
# Not every orphan is a bug: callbacks that payment providers POST to, health
# probes, and CLI-facing routes are reached by things that are not a screen and
# never should be. Those are listed apart rather than counted, so the real
# question — "is this a feature nobody can reach?" — stays readable.

# Reached by something that is not a browser screen, by design.
NON_UI_PREFIXES = (
    "/finance/mpesa/callback", "/finance/mpesa/c2b", "/finance/bank/sms",
    "/finance/card/ipn", "/health", "/auth/refresh", "/uploads",
)


def all_path_literals():
    """Every API-looking string literal anywhere in the front-end source.

    The call scanner at the top only matches a literal sitting directly inside
    api.get(...), which is right for ITS question (does this call resolve?) but
    far too narrow for this one. Real code holds paths in variables and picks
    them with ternaries:

        const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'
        api.post(type === 'CLOCK_IN' ? '/hr/clock-in' : '/hr/clock-out')

    The first version of this check reported both queue endpoints and clock-out
    as features nobody could reach, which is the opposite of true — the kitchen
    board is one of the most-used screens in the resort. For the orphan
    question, wrongly counting a path as CALLED costs one missed finding;
    wrongly calling a live endpoint an orphan sends someone to build a door that
    already exists. So this deliberately errs wide.
    """
    lits = set()
    for root in APPS:
        for f in Path(root).rglob("*.ts*"):
            # main.tsx and AppLayout.tsx are ROUTER manifests: every "/calendar"
            # in them is a browser route, not an API call. Counting those as
            # callers is how POST /calendar hid — no screen can create a
            # calendar entry, so the Calendar screen is empty forever, and this
            # scan called it covered because the router mentions the word.
            if f.name in ("main.tsx", "AppLayout.tsx"):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            lits |= set(re.findall(r"""['"`](/[a-z][a-z0-9\-]*(?:/[^'"`\s${]*)*)['"`]""", text))
    return lits


def orphan_scan(app, calls):
    """Real routes that no screen calls. Returns the ones worth a door."""
    # Per METHOD, not per path.
    #
    # The first version collected a bare set of paths, so a route family counted
    # as covered the moment ANY method on it had a caller. POST /calendar has
    # never been called by anything — no screen can mark a peak date or a
    # holiday, so the Calendar screen is empty forever and always will be — and
    # this scan called it fine, because GET /calendar is read by two apps. A
    # write endpoint hiding behind its own read sibling is precisely the orphan
    # worth finding, and it was the one shape guaranteed to be missed.
    called: dict[str, set[str]] = {}
    for path, methods in calls.items():
        # A call built at runtime ("/tabs/${id}") was normalised to "/tabs/1"
        # by the scanner above; compare on the static head so a dynamic caller
        # still counts as covering its route family.
        parts = [p for p in path.split("/") if p]
        for i in range(len(parts), 0, -1):
            called.setdefault("/" + "/".join(parts[:i]), set()).update(
                m.upper() for m in methods)

    # Literals found loose in the source (a path held in a variable) carry no
    # method with them, so they cover every method — deliberately generous, to
    # keep this reporting real orphans rather than clever ones.
    for path in all_path_literals():
        parts = [p for p in path.split("/") if p]
        for i in range(len(parts), 0, -1):
            called.setdefault("/" + "/".join(parts[:i]), set()).add("*")

    def methods_called_for(rule) -> set[str]:
        r = str(rule)
        # Flask writes params as <id>; a caller reaches them as a value.
        head = r.split("<")[0].rstrip("/") or "/"
        hit = set()
        for c, ms in called.items():
            if c == head or c == r or c.startswith(head + "/"):
                hit |= ms
        return hit

    orphans, by_design = [], []
    for rule in sorted(app.url_map.iter_rules(), key=str):
        if rule.endpoint == "static":
            continue
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        hit = methods_called_for(rule)
        if "*" in hit:
            continue
        unreached = [m for m in methods if m not in hit]
        if not unreached:
            continue
        (by_design if str(rule).startswith(NON_UI_PREFIXES) else orphans).append(
            (str(rule), ",".join(unreached)))

    print("\nendpoints with no screen behind them:")
    if not orphans:
        print("  every route the API serves is reachable from some screen")
    else:
        print(f"  {len(orphans)} route(s) no app calls — each is a feature nobody can reach:")
        for path, methods in orphans:
            print(f"      {methods:<18} {path}")
    if by_design:
        print(f"  ({len(by_design)} more are called by providers, probes or the CLI, "
              f"not by a screen — expected)")
    return orphans


def main():
    app = create_app("development")
    calls = scan()
    print(f"{len(calls)} distinct API paths called across "
          f"{len(APPS)} front-end packages\n")

    missing, wrong_method, dynamic = [], [], []
    adapter = app.url_map.bind("localhost")

    def family_exists(path):
        """Some calls cannot be resolved statically — the template expands to a
        query string (`/disputes${qs}`) or to an action verb chosen at runtime
        (`/order-items/${id}/${action}`). Those are not broken routes, and
        calling them broken is the same false alarm as before. Instead check
        that the STATIC prefix has real routes hanging off it, and say plainly
        that the tail could not be verified from source."""
        head = path.rstrip("0123456789").rstrip("/")
        while head.count("/") >= 1 and head != "":
            if any(str(r).startswith(head) for r in app.url_map.iter_rules()):
                return head
            head = head.rsplit("/", 1)[0]
        return None

    for path, methods in sorted(calls.items()):
        for method in methods:
            try:
                adapter.match(path, method=method)
            except RequestRedirect:
                pass                                  # trailing-slash variant, fine
            except MethodNotAllowed:
                wrong_method.append((path, method, methods[method]))
            except NotFound:
                fam = family_exists(path)
                (dynamic if fam else missing).append(
                    (path, method, methods[method], fam))

    if missing:
        print(f"✗ {len(missing)} call(s) hit NO route — these screens render empty:")
        for path, method, files, _ in missing:
            where = ", ".join(sorted(Path(f).name for f in files)[:3])
            print(f"    {method:6} {path:48} {where}")
    else:
        print("✓ every path the front end calls resolves to a real route")

    if wrong_method:
        print(f"\n✗ {len(wrong_method)} call(s) use a method the route refuses:")
        for path, method, files in wrong_method:
            where = ", ".join(sorted(Path(f).name for f in files)[:3])
            print(f"    {method:6} {path:48} {where}")

    if dynamic:
        print(f"\n· {len(dynamic)} call(s) build the tail at runtime — prefix is real,"
              f" tail not checkable from source:")
        for path, method, files, fam in dynamic:
            where = ", ".join(sorted(Path(f).name for f in files)[:2])
            print(f"    {method:6} {path:44} under {fam}  ({where})")

    # Every GET the owner's screens make should actually answer. A 500 is a
    # dead screen too — it just fails louder than a 404.
    print("\nliveness of every GET, as the owner:")
    broken = []
    with app.app_context():
        owner = db.session.query(User).filter_by(username="amara.wanjiku").first()
        h = {"Authorization": f"Bearer {create_access_token(identity=owner.id)}"}
        c = app.test_client()
        checked = 0
        for path, methods in sorted(calls.items()):
            if "GET" not in methods:
                continue
            try:
                adapter.match(path, method="GET")
            except Exception:
                continue                              # already reported above
            r = c.get(path, headers=h, environ_base={"REMOTE_ADDR": "127.0.0.1"})
            checked += 1
            if r.status_code >= 500:
                broken.append((path, r.status_code))
    if broken:
        print(f"  ✗ {len(broken)} of {checked} GETs return a server error:")
        for path, code in broken:
            print(f"      {code}  {path}")
    else:
        print(f"  ✓ all {checked} GET paths answer without a server error")

    # ── Can the people who SEE a screen actually use it? ─────────────────────
    #
    # Nine times this session a control was offered to somebody the API then
    # refused: the check-in tile, self-pay, the variance tab, stock-count, the
    # cash tile, the STK-push level, the waiver level, the Gate hub, and the
    # Events create button. Every one had the same shape — the screen's floor
    # and the endpoint's floor disagreed — and none of the existing scans could
    # see it, because they compare a tile against a screen and stop at the
    # front door.
    #
    # This asks the API itself, as a real person at each level, rather than
    # inferring from source. GET only: probing writes as five roles would
    # change the data it is measuring.
    #
    # A 403 is only worth reporting when someone who can OPEN the screen gets
    # it. Owner-private money is a deliberate wall, not a bug — the manager is
    # refused /finance/dashboard on purpose, and no manager screen asks for it.
    print("\nwhat each role gets from the endpoints their screens call:")

    # The screen each path is called from, and that screen's own guard. A
    # refusal only matters when the person could have OPENED the screen that
    # asks — a waiter refused /audit/logs is the system working.
    # The APP is a floor before any screen guard is. owner_pwa's AuthGate
    # refuses anyone under role_level 10 at the door, which is why none of its
    # screens carry a RequireRole of their own — and why the first version of
    # this check reported a waiter being refused /audit/logs by the owner's
    # Audit screen. A waiter cannot reach that screen; they cannot reach that
    # APP. Reading the screen guard alone made 117 deliberate walls look like
    # bugs, which is the same cry-wolf failure as the sweep's.
    APP_FLOOR = {"owner_pwa": 10, "station_pwa": 0, "employee_pwa": 0, "shared_ui": 0}
    guard_of = {}
    for pkg, floor in APP_FLOOR.items():
        src = Path(pkg) / "src"
        if not src.exists():
            continue
        for f in src.rglob("*.tsx"):
            m = re.search(r"<RequireRole\s+minLevel=\{(\d+)\}", f.read_text(errors="ignore"))
            screen_floor = int(m.group(1)) if m else 0
            # A screen reached through two apps takes the LOWER floor — that is
            # the door the weakest person actually comes through.
            lvl = max(floor, screen_floor)
            guard_of[f.name] = min(guard_of.get(f.name, lvl), lvl)

    ROLES = [("waiter", "ivan.kipchoge", 1), ("spa/water", "esther.kamau", 2),
             ("front desk", "grace.muthoni", 3), ("manager", "brian.mwangi", 5),
             ("owner", "amara.wanjiku", 10)]
    real = []
    with app.app_context():
        c = app.test_client()
        for label, username, level in ROLES:
            u = db.session.query(User).filter_by(username=username).first()
            if not u:
                continue
            h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}
            for path, methods in sorted(calls.items()):
                if "GET" not in methods:
                    continue
                try:
                    adapter.match(path, method="GET")
                except Exception:
                    continue
                r = c.get(path, headers=h, environ_base={"REMOTE_ADDR": "127.0.0.1"})
                if r.status_code != 403:
                    continue
                # Which screens ask for it, and could this person have opened one?
                for f in methods.get("GET", set()):
                    name = Path(f).name
                    if guard_of.get(name, 0) <= level:
                        real.append((label, path, name))

    # Known blind spot, stated rather than hidden: attribution is per FILE, so a
    # path inside a section that only renders for managers — IncidentScreen's
    # "All Incidents" list, for instance — still counts as called by everyone
    # who can open the file. Reading the render condition would mean reading
    # JSX control flow, which is where a checker starts lying. Better to over-
    # report three and say so than to under-report the one that matters.
    if real:
        print(f"  ✗ {len(real)} case(s) where a role can open the screen but the"
              f" endpoint behind it refuses them:")
        print("     (per-file attribution — a path inside a manager-only SECTION"
              " still lists here)")
        for label, path, screen in real:
            print(f"      {label:<11} {path:<42} {screen}")
    else:
        print("  ✓ every GET a screen makes is allowed to everyone that screen lets in")

    # ── Internal navigation ───────────────────────────────────────────────────
    # The API contract is only half of it. A screen can also navigate to one of
    # its OWN routes that no longer exists, and nothing complains: React Router
    # quietly falls through to the catch-all, which in these apps is the login
    # screen. The person sees "it logged me out" and has no idea a screen moved.
    #
    # That is exactly what happened when the station tools left the employee
    # app: TWO redirect blocks and three notification tap-targets still pointed
    # at deleted routes. TypeScript cannot catch it — they are strings.
    print("\ninternal navigation, per app:")
    dead_nav = []
    for pkg in ("employee_pwa", "owner_pwa", "station_pwa"):
        main = Path(pkg) / "src" / "main.tsx"
        if not main.exists():
            continue
        declared = set(re.findall(r"path: '([^']+)'", main.read_text()))
        # ":id" style params — compare on the static prefix
        stems = {d.split("/:")[0] for d in declared}
        targets = set()
        for f in (Path(pkg) / "src").rglob("*.ts*"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            targets |= set(re.findall(r"""(?:Navigate to=|navigate\()['"](/[a-z0-9/-]*)""", text))
            if f.name in ("notificationRoutes.ts", "sw.ts"):
                targets |= set(re.findall(r""": '(/[a-z0-9/-]+)'""", text))
        bad = sorted(t for t in targets
                     if t and t not in declared and t.split("/:")[0] not in stems
                     and not any(t.startswith(s + "/") for s in stems if s != "/"))
        print(f"  {pkg:14} {len(targets):>3} target(s), "
              f"{'all resolve' if not bad else 'DEAD: ' + ', '.join(bad)}")
        dead_nav += [(pkg, t) for t in bad]

    perm_breaks = permission_scan()
    orphans = orphan_scan(app, calls)

    total_bad = (len(missing) + len(wrong_method) + len(broken)
                 + len(dead_nav) + len(perm_breaks))
    print("\n" + "=" * 62)
    print("front-end contract holds" if not total_bad
          else f"{total_bad} contract break(s)")
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
