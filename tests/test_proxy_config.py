"""
The Vite proxy lists must cover every API path the apps actually call.

THE BUG THIS EXISTS TO CATCH, because it bit twice and cost an hour each time:

Each PWA runs on its own port in development and talks to Flask on :5000. Vite
only forwards a request to Flask if its path prefix appears in PROXIED_PATHS in
that app's vite.config.ts. Any path NOT on that list is treated as a page
navigation, so Vite serves index.html instead -- and axios receives a 200 with
an HTML body and tries to parse it as JSON.

The failure is loud but points nowhere useful: "Unexpected token '<'". Nothing
in the screen, the endpoint or the tests is wrong. The blueprint was simply
added to Flask and never added to a text list in a build config, and no test
looked at that list. It happened with /booking-payments, then again with /audit.

Two directions are checked, because each catches a different mistake:

  called -> proxied   a new blueprint wired into a screen but not the proxy
                      (the bug above)
  proxied -> real     a typo or a leftover entry, which silently forwards a
                      path Flask has never served

Deliberately NOT asserted: that all three apps proxy the same paths. They
should not. The station tablet has no business reaching /finance, and its
shorter list is a boundary worth keeping, not drift worth fixing.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
APPS = ["employee_pwa", "owner_pwa", "station_pwa"]

# Matches the literal path in an axios call, covering the three shapes actually
# used in these apps:
#     api.get('/gate/wristbands')                 quoted, static
#     api.post<Resp>(`/tabs/${id}/close`)         generic + template literal
#     api.delete("/orders/" + id)                 double-quoted
# The capture stops at the first ${ or quote, so a template literal yields its
# static prefix -- which is all we need, since only the first segment matters.
API_CALL = re.compile(
    r"""api\.(?:get|post|put|patch|delete)      # the verb
        (?:<[^>]*>)?                            # optional TS generic, e.g. <Tab[]>
        \(\s*[`'"]                              # opening paren and quote
        (/[^`'"$]*)                             # the static leading path
    """,
    re.VERBOSE,
)

# PROXIED_PATHS = [ ... ] in vite.config.ts -- non-greedy to the first ]
PROXY_LIST = re.compile(r"PROXIED_PATHS\s*=\s*\[(.*?)\]", re.DOTALL)


def _proxied_paths(app_dir: str) -> set[str]:
    """The prefixes this app's dev server forwards to Flask."""
    config = (REPO / app_dir / "vite.config.ts").read_text()
    block = PROXY_LIST.search(config)
    assert block, f"{app_dir}/vite.config.ts has no PROXIED_PATHS array"
    # Pull the quoted strings out of the array body
    return set(re.findall(r"['\"](/[^'\"]+)['\"]", block.group(1)))


def _called_prefixes(app_dir: str) -> dict[str, set[str]]:
    """
    Map each API path prefix this app calls -> the files that call it.

    Keeping the file names means a failure says WHERE to look instead of just
    naming a path.
    """
    found: dict[str, set[str]] = {}
    src = REPO / app_dir / "src"
    for path in list(src.rglob("*.ts")) + list(src.rglob("*.tsx")):
        for call in API_CALL.findall(path.read_text()):
            # '/gate/wristbands?active=1' -> '/gate'. The proxy matches on the
            # first segment, so that is the only part that decides routing.
            prefix = "/" + call.lstrip("/").split("/")[0].split("?")[0]
            if len(prefix) > 1:  # ignore a bare '/'
                found.setdefault(prefix, set()).add(path.relative_to(src).as_posix())
    return found


@pytest.mark.parametrize("app_dir", APPS)
def test_every_called_path_is_proxied(app_dir):
    """A screen that calls an unproxied path receives HTML and dies on parse."""
    proxied = _proxied_paths(app_dir)
    missing = {
        prefix: sorted(files)
        for prefix, files in _called_prefixes(app_dir).items()
        if prefix not in proxied
    }
    assert not missing, (
        f"{app_dir} calls API paths its Vite proxy does not forward.\n"
        f"Vite will serve index.html and axios will fail with \"Unexpected token '<'\".\n"
        f"Add these to PROXIED_PATHS in {app_dir}/vite.config.ts:\n"
        + "\n".join(f"  {p}  <- called from {', '.join(f)}" for p, f in sorted(missing.items()))
    )


@pytest.mark.parametrize("app_dir", APPS)
def test_every_proxied_path_is_a_real_backend_route(app_dir, app):
    """
    A proxied path Flask never serves is a typo or a leftover.

    It fails quietly -- the request forwards, Flask 404s, and the screen shows
    an error that looks like a backend problem rather than a stale config line.
    """
    # Every first segment Flask actually serves, from the live URL map
    real = {
        "/" + str(rule).lstrip("/").split("/")[0]
        for rule in app.url_map.iter_rules()
        if str(rule) != "/static/<path:filename>"
    }
    unknown = sorted(p for p in _proxied_paths(app_dir) if p not in real)
    assert not unknown, (
        f"{app_dir}/vite.config.ts proxies paths no Flask route serves: {unknown}\n"
        f"Either the blueprint was removed or the entry is misspelt."
    )


def test_the_guard_would_actually_have_caught_the_audit_bug():
    """
    Proof the check is load-bearing rather than decorative.

    Reproduces the exact regression: /audit removed from the proxy list while
    AuditScreen still calls it. If this assertion stops holding, the detector
    has gone blind and the two tests above are worthless.
    """
    owner_calls = _called_prefixes("owner_pwa")
    assert "/audit" in owner_calls, "owner_pwa no longer calls /audit -- update this test"

    pretend_list = _proxied_paths("owner_pwa") - {"/audit"}
    assert "/audit" not in pretend_list, "the detector missed a path that is genuinely absent"
