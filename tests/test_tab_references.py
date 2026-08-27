"""
Tab references: keep the same table from becoming two.

`Tab.reference` is deliberately POLYMORPHIC. On the live database it holds:

    Band #1 .. Band #26        auto-generated at the gate
    Villa 6 / Wanjiru Kamau    villa plus the guest's name
    Table 2 — breakfast        an actual dining table
    Spa — Full Body Massage    a service tab
    6, 9                       someone meaning "Table 6" with no list in front of them

A Table model would be the wrong shape for that — only a minority of tabs are
dining tables at all, and bands and villas would not fit it. What free text
genuinely costs is consistency, so the fix is narrower: normalise on write, and
offer what has already been used so the waiter picks instead of types.
"""
import uuid

import pytest

from app.extensions import db
from app.models.tab import Tab


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _open(client, token, reference):
    rv = client.post("/tabs", json={"reference": reference,
                                    "idempotency_key": str(uuid.uuid4())},
                     headers=_auth(token))
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


# ── Normalisation ────────────────────────────────────────────────────────────

def test_internal_whitespace_is_collapsed(app, client, waiter_token):
    """"Table  5" and "Table 5" are the same table and must not become two rows
    in every report that groups by reference."""
    tab_id = _open(client, waiter_token, "Table   5")
    assert db.session.get(Tab, tab_id).reference == "Table 5"


def test_surrounding_whitespace_is_trimmed(app, client, waiter_token):
    tab_id = _open(client, waiter_token, "  Table 7  ")
    assert db.session.get(Tab, tab_id).reference == "Table 7"


def test_case_is_left_alone(app, client, waiter_token):
    """
    Deliberate. A reference carries guest names — "Villa 6 / Wanjiru Kamau" —
    and title-casing or lower-casing a person's name to tidy a key is not a
    trade worth making.
    """
    tab_id = _open(client, waiter_token, "Villa 6 / Wanjiru Kamau")
    assert db.session.get(Tab, tab_id).reference == "Villa 6 / Wanjiru Kamau"


def test_an_empty_reference_stays_null_not_blank(app, client, waiter_token):
    """A walk-in has no reference; "" and NULL must not both mean that."""
    tab_id = _open(client, waiter_token, "   ")
    assert db.session.get(Tab, tab_id).reference is None


# ── The pick-list ────────────────────────────────────────────────────────────

def test_the_references_route_is_not_swallowed_by_the_tab_id_route(app, client, waiter_token):
    """
    /tabs/references and /tabs/<tab_id> overlap. Werkzeug prefers the static
    rule, but that is exactly the sort of thing that silently breaks — so it is
    asserted rather than assumed.
    """
    rv = client.get("/tabs/references", headers=_auth(waiter_token))
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list), (
        "the static route must win; a 404 here means it was matched as a tab id"
    )


def test_previously_used_references_are_offered(app, client, waiter_token):
    _open(client, waiter_token, "Table 12")
    _open(client, waiter_token, "Beach Bar 3")

    refs = client.get("/tabs/references", headers=_auth(waiter_token)).get_json()
    assert "Table 12" in refs
    assert "Beach Bar 3" in refs


def test_the_list_does_not_repeat_the_same_place(app, client, waiter_token):
    """Three sittings at Table 9 is still one Table 9 in the pick-list."""
    for _ in range(3):
        _open(client, waiter_token, "Table 9")

    refs = client.get("/tabs/references", headers=_auth(waiter_token)).get_json()
    assert refs.count("Table 9") == 1


def test_case_variants_collapse_in_the_list(app, client, waiter_token):
    """Offering both "Table 4" and "table 4" would teach staff to create both."""
    _open(client, waiter_token, "Table 4")
    _open(client, waiter_token, "table 4")

    refs = client.get("/tabs/references", headers=_auth(waiter_token)).get_json()
    assert len([r for r in refs if r.strip().lower() == "table 4"]) == 1


def test_band_tabs_are_excluded(app, client, waiter_token):
    """
    The gate generates these automatically and a waiter never types one. On the
    live data there are 26 of them — listing those would bury the handful of
    names that actually matter.
    """
    _open(client, waiter_token, "Band #77")
    _open(client, waiter_token, "Table 3")

    refs = client.get("/tabs/references", headers=_auth(waiter_token)).get_json()
    assert "Table 3" in refs
    assert not any(r.startswith("Band #") for r in refs)
