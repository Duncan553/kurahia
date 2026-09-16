"""
Every API path a PWA calls must be in that PWA's vite proxy list.

The failure this prevents is nasty because it does not look like itself. Vite
only forwards the path prefixes named in `PROXIED_PATHS`; anything else it
answers ITSELF, with index.html or a 404. So the app's axios call comes back
200-with-HTML or 404, and the screen crashes somewhere far away — the manager's
dispute queue died on "disputes.map is not a function", which reads as a
frontend bug and is actually a missing line in a config file.

It has now happened three times: '/images' (every menu photo broken),
'/disputes' (the queue), '/lost-found' (this session). Each was found by a
person opening the screen. This test finds the next one in two seconds.

Deliberately NOT the reverse check: a proxy entry with no caller is harmless,
and several are there for paths a screen will reach for later.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APPS = ["station_pwa", "owner_pwa", "employee_pwa"]

# api.get('/x'), api.post(`/x/${id}`), api.patch("/x") — the four verbs the
# apps use, with any of the three quote styles.
CALL = re.compile(r"""api\.(?:get|post|patch|put|delete)\s*(?:<[^>]*>\s*)?\(\s*['"`](/[a-zA-Z0-9_\-]+)""")

# Relative paths and template-literal roots we cannot resolve statically.
IGNORE = {"/"}


def _proxied_paths(app: str) -> set[str]:
    cfg = (ROOT / app / "vite.config.ts").read_text()
    block = re.search(r"const PROXIED_PATHS = \[(.*?)\n\]", cfg, re.S)
    assert block, f"{app}/vite.config.ts has no PROXIED_PATHS array"
    # Strip // comments BEFORE reading quoted strings. An apostrophe inside one
    # ("this app's public/ folder") pairs with the next real quote and silently
    # shifts every entry after it — which made an earlier version of this very
    # check report 31 false missing paths.
    body = "\n".join(re.sub(r"//.*$", "", ln) for ln in block.group(1).splitlines())
    return set(re.findall(r"'(/[^']*)'", body))


def _called_paths(app: str) -> dict[str, str]:
    """{'/lost-found': 'src/screens/LostFoundScreen.tsx'} — path to first caller."""
    found: dict[str, str] = {}
    roots = [ROOT / app / "src", ROOT / "shared_ui" / "src"]
    for root in roots:
        for f in list(root.rglob("*.tsx")) + list(root.rglob("*.ts")):
            if "__tests__" in f.parts:
                continue
            for m in CALL.finditer(f.read_text()):
                p = m.group(1)
                if p not in IGNORE:
                    found.setdefault(p, str(f.relative_to(ROOT)))
    return found


@pytest.mark.parametrize("app", APPS)
def test_every_path_the_app_calls_is_proxied(app):
    proxied = _proxied_paths(app)
    called = _called_paths(app)
    missing = {p: where for p, where in called.items() if p not in proxied}
    assert not missing, (
        f"{app}/vite.config.ts does not proxy paths this app calls:\n" +
        "\n".join(f"  {p}  (called from {where})" for p, where in sorted(missing.items())) +
        f"\n\nAdd them to PROXIED_PATHS, or Vite answers the call itself and the "
        f"screen fails somewhere else entirely."
    )


@pytest.mark.parametrize("app", APPS)
def test_the_parser_actually_found_the_list(app):
    """Guards the guard.

    A regex that silently captures nothing turns this whole file into a test
    that always passes — which is worse than not having it. Both halves must
    come back non-trivial.
    """
    assert len(_proxied_paths(app)) > 10, f"{app}: PROXIED_PATHS parsed as near-empty"
    assert len(_called_paths(app)) > 10, f"{app}: found almost no api.* calls"
