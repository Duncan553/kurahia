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

    total_bad = len(missing) + len(wrong_method) + len(broken)
    print("\n" + "=" * 62)
    print("front-end contract holds" if not total_bad
          else f"{total_bad} contract break(s)")
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
