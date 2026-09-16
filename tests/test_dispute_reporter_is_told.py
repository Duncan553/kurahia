"""
A grievance that is answered in silence reads as a grievance that was ignored.

Resolving or dismissing a dispute wrote the outcome into the row and stopped.
The person who filed it was never told — the resolution notes existed, and the
only way to find them was to keep reopening the Disputes screen on the chance
something had changed. Leave decisions already notify (app/hr/leave.py); the
complaint channel, where being answered is the entire point, did not.

Found by using it: a waiter filed one through the phone, the owner resolved it
with notes, and his inbox stayed empty.
"""
import uuid

import pytest

from app.extensions import db
from app.models.notification import Notification


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def filed_dispute(client, waiter_token, waiter_profile):
    """A waiter raises a complaint, the way the phone app does."""
    rv = client.post("/disputes", json={
        "category": "INTERPERSONAL",
        "description": "Three closing shifts in a row while the other waiter got days.",
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_hdr(waiter_token))
    assert rv.status_code in (200, 201), rv.get_json()
    return rv.get_json()["id"]


def _notices_for(dispute_id):
    return (db.session.query(Notification)
            .filter_by(reference_type="dispute_decision", reference_id=dispute_id)
            .all())


class TestTheReporterIsTold:

    def test_resolving_sends_the_notes_to_the_person_who_filed_it(
            self, client, manager_token, filed_dispute, waiter_profile):
        client.post(f"/disputes/{filed_dispute}/claim", headers=_hdr(manager_token))
        rv = client.post(f"/disputes/{filed_dispute}/resolve",
                         json={"resolution_notes": "Saturday closing now rotates."},
                         headers=_hdr(manager_token))
        assert rv.status_code == 200, rv.get_json()

        notices = _notices_for(filed_dispute)
        assert len(notices) == 1, "the reporter gets exactly one notice"
        n = notices[0]
        assert n.recipient_user_id == waiter_profile.user_id, \
            "it goes to the person who raised it, not the manager"
        assert "resolved" in n.subject.lower()
        assert "Saturday closing now rotates." in n.body, \
            "the notes are the answer — sending a bare 'resolved' tells him nothing"

    def test_dismissing_also_tells_him_and_does_not_claim_it_was_resolved(
            self, client, manager_token, filed_dispute):
        client.post(f"/disputes/{filed_dispute}/claim", headers=_hdr(manager_token))
        rv = client.post(f"/disputes/{filed_dispute}/dismiss",
                         json={"reason": "Rosters are set by seniority this quarter."},
                         headers=_hdr(manager_token))
        assert rv.status_code == 200, rv.get_json()

        n = _notices_for(filed_dispute)[0]
        assert "resolved" not in n.subject.lower(), \
            "a dismissal dressed up as a resolution is worse than no notice"
        assert "Rosters are set by seniority" in n.body

    def test_a_double_tap_on_resolve_cannot_send_it_twice(
            self, client, manager_token, filed_dispute):
        client.post(f"/disputes/{filed_dispute}/claim", headers=_hdr(manager_token))
        body = {"resolution_notes": "Sorted."}
        first = client.post(f"/disputes/{filed_dispute}/resolve", json=body,
                            headers=_hdr(manager_token))
        second = client.post(f"/disputes/{filed_dispute}/resolve", json=body,
                             headers=_hdr(manager_token))

        assert first.status_code == 200
        # The state machine refuses RESOLVED -> RESOLVED, so the second call is
        # rejected outright; the idempotency key is the belt to that braces, and
        # both together mean one notice.
        assert second.status_code == 400
        assert len(_notices_for(filed_dispute)) == 1

    def test_an_owner_only_complaint_still_reaches_its_reporter(
            self, client, owner_token, waiter_token, waiter_profile):
        """Owner-only hides the row from the MANAGER. It must not hide the
        answer from the person who wrote it."""
        rv = client.post("/disputes", json={
            "category": "PERFORMANCE",
            "description": "My overtime is missing from the payslip.",
            "is_owner_only": True,
            "idempotency_key": str(uuid.uuid4()),
        }, headers=_hdr(waiter_token))
        did = rv.get_json()["id"]

        client.post(f"/disputes/{did}/claim", headers=_hdr(owner_token))
        client.post(f"/disputes/{did}/resolve",
                    json={"resolution_notes": "Eight hours added to this cycle."},
                    headers=_hdr(owner_token))

        n = _notices_for(did)[0]
        assert n.recipient_user_id == waiter_profile.user_id
        assert "Eight hours added" in n.body
