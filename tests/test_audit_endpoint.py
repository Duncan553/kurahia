"""
Read access to the audit trail.

The hash-chained log is the strongest control in the system and was reachable
ONLY via `flask audit verify-chain`. The owner could not answer "who voided that
order at 9pm?" without an SSH session — the best-designed feature was, in
practice, unusable.

Two properties matter more than the listing itself:

  1. OWNER ONLY. The log records what managers did, so a manager reading their
     own trail is not a control.
  2. READ ONLY. An audit trail reachable for writes through the API is an audit
     trail an attacker can reach.
"""
import uuid

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def some_history(app):
    """A few entries with distinct actors and actions to filter against."""
    AuditLog.log(actor="joyce.wambua", action="order_item.cancel",
                 target="tab-1", details="wrong table")
    AuditLog.log(actor="brian.mwangi", action="menu.item.edit",
                 target="Grilled Tilapia", details="price 1800 -> 900")
    AuditLog.log(actor="brian.mwangi", action="menu.item.disable",
                 target="Old Dish")
    db.session.commit()


# ── Access control ───────────────────────────────────────────────────────────

def test_owner_can_read_the_trail(app, client, owner_token, some_history):
    rv = client.get("/audit/logs", headers=_auth(owner_token))
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["total"] >= 3
    assert {e["actor"] for e in body["entries"]} >= {"joyce.wambua", "brian.mwangi"}


def test_a_manager_cannot_read_the_trail(app, client, manager_token, some_history):
    """
    The log records what managers do. Letting a manager read it — or worse,
    filter it to their own name — is not oversight.
    """
    rv = client.get("/audit/logs", headers=_auth(manager_token))
    assert rv.status_code == 403
    assert "owner" in rv.get_json()["error"].lower()


def test_a_waiter_cannot_read_the_trail(app, client, waiter_token, some_history):
    assert client.get("/audit/logs", headers=_auth(waiter_token)).status_code == 403


def test_the_trail_is_read_only(app, client, owner_token):
    """No verb other than GET should exist on the audit routes."""
    for method in ("post", "patch", "delete", "put"):
        rv = getattr(client, method)("/audit/logs", headers=_auth(owner_token))
        assert rv.status_code == 405, (
            f"{method.upper()} /audit/logs must not be routable — an audit trail "
            f"you can write through the API is not an audit trail"
        )


# ── Filtering: the point is answering a question ─────────────────────────────

def test_filter_by_actor_answers_who_did_this(app, client, owner_token, some_history):
    rv = client.get("/audit/logs?actor=brian", headers=_auth(owner_token))
    assert rv.status_code == 200
    entries = rv.get_json()["entries"]
    assert entries and all("brian" in e["actor"] for e in entries)


def test_filter_by_action_prefix(app, client, owner_token, some_history):
    """`menu.` must find every menu action without knowing the full verb list."""
    rv = client.get("/audit/logs?action=menu.", headers=_auth(owner_token))
    entries = rv.get_json()["entries"]
    assert len(entries) >= 2
    assert all(e["action"].startswith("menu.") for e in entries)


def test_the_details_carry_the_answer(app, client, owner_token, some_history):
    """A price change has to say what it changed FROM, or the trail is useless."""
    rv = client.get("/audit/logs?action=menu.item.edit", headers=_auth(owner_token))
    entry = rv.get_json()["entries"][0]
    assert "1800" in entry["details"] and "900" in entry["details"]


def test_a_bad_date_is_refused_in_plain_english(app, client, owner_token):
    rv = client.get("/audit/logs?from=last-tuesday", headers=_auth(owner_token))
    assert rv.status_code == 400
    assert "YYYY-MM-DD" in rv.get_json()["error"]


def test_paging_is_capped(app, client, owner_token, some_history):
    """An unbounded limit is a way to make the server do unbounded work."""
    rv = client.get("/audit/logs?limit=99999", headers=_auth(owner_token))
    assert rv.get_json()["limit"] <= 200


# ── Chain verification: showing history is not enough ────────────────────────

def test_owner_can_confirm_history_was_not_rewritten(app, client, owner_token, some_history):
    rv = client.get("/audit/verify", headers=_auth(owner_token))
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["intact"] is True
    assert body["entries_checked"] >= 3


def test_tampering_is_detected_through_the_endpoint(app, client, owner_token, some_history):
    """
    The whole reason the chain exists. Edit a row directly in the database — as
    someone with DB access would — and the endpoint must report it.
    """
    row = db.session.query(AuditLog).filter_by(actor="joyce.wambua").first()
    row.details = "nothing to see here"
    row.action = "order_item.serve"      # covered by the hash
    db.session.commit()

    rv = client.get("/audit/verify", headers=_auth(owner_token))
    body = rv.get_json()
    assert body["intact"] is False, "a rewritten entry must break the chain"
    assert "broken" in body["detail"].lower()


def test_a_manager_cannot_run_the_verification_either(app, client, manager_token):
    assert client.get("/audit/verify", headers=_auth(manager_token)).status_code == 403


def test_action_list_helps_the_owner_filter(app, client, owner_token, some_history):
    """So a UI can offer real options instead of asking the owner to guess."""
    rv = client.get("/audit/actions", headers=_auth(owner_token))
    assert rv.status_code == 200
    actions = rv.get_json()
    assert "menu.item.edit" in actions


# ── The chain's structural invariant ─────────────────────────────────────────

def test_every_entry_chains_off_the_one_immediately_before_it(app):
    """
    The invariant that was actually violated in production data.

    log() read the chain tail WITHOUT a lock, so two concurrent requests both
    saw the same "latest" row and both chained off it. One entry then skipped
    its predecessor and verify_chain() reported the history as broken forever —
    from ordinary traffic, not tampering. Observed on the dev database: two
    order_item.receive entries 6.6ms apart, the second chained off the row
    before the first.

    An alarm that is always sounding cannot distinguish a real rewrite from a
    busy Saturday, which made the whole control worthless.
    """
    for i in range(25):
        AuditLog.log(actor=f"actor{i}", action="test.sequence", target=str(i))
    db.session.commit()

    rows = (db.session.query(AuditLog)
            .filter_by(action="test.sequence")
            .order_by(AuditLog.timestamp.asc()).all())
    assert len(rows) == 25

    for earlier, later in zip(rows, rows[1:]):
        assert later.prev_hash == earlier.entry_hash, (
            f"entry {later.target} chained off the wrong row — it must link to "
            f"its immediate predecessor or the chain cannot be verified"
        )


def test_a_deleted_entry_is_detectable(app, client, owner_token, some_history):
    """
    Removing history must break the chain too, not just editing it — otherwise
    the cover-up is simply to delete the row rather than change it.
    """
    rows = db.session.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    assert len(rows) >= 3
    db.session.delete(rows[1])          # excise one from the middle
    db.session.commit()

    rv = client.get("/audit/verify", headers=_auth(owner_token))
    assert rv.get_json()["intact"] is False, (
        "deleting an entry must break the chain — otherwise the trail can be "
        "cleaned up rather than falsified"
    )
