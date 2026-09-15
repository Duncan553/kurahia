"""
Logging an incident has to reach a person.

The endpoint wrote the Incident row and an audit line and notified nobody,
while listing incidents is manager-only — so a guest hurt at the jet ski dock
sat in a table until a manager happened to open a screen they had no reason to
open. The reporter meanwhile saw "Incident logged." and reasonably believed it
had been raised.
"""
import uuid

from app.extensions import db


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _log(client, token, severity="HIGH", location="Jet ski dock"):
    return client.post("/incidents", json={
        "severity": severity, "location": location,
        "description": "Guest slipped on the wet boarding step.",
        "idempotency_key": str(uuid.uuid4()),
    }, headers=auth(token))


def _notifs_for_incident(incident_id):
    from app.models.notification import Notification
    return db.session.query(Notification).filter_by(
        reference_type="incident", reference_id=incident_id).all()


def test_logging_an_incident_notifies_a_manager(client, waiter_token, manager_token):
    """The waiter files it; the manager hears about it without being asked to look."""
    rv = _log(client, waiter_token)
    assert rv.status_code == 201, rv.get_json()
    inc_id = rv.get_json()["id"]

    notes = _notifs_for_incident(inc_id)
    assert notes, "incident reached nobody"

    from app.models.user import User
    for n in notes:
        recipient = db.session.get(User, n.recipient_user_id)
        # Never tell someone who then cannot open the list
        assert recipient.role.level >= 5
    assert "Jet ski dock" in notes[0].subject


def test_a_low_severity_incident_is_raised_too(client, waiter_token):
    """
    Severity is the reporter's guess made in the moment, and "low" is exactly
    how a small thing that was actually a big thing gets described.
    """
    rv = _log(client, waiter_token, severity="LOW", location="Pool steps")
    assert rv.status_code == 201
    assert _notifs_for_incident(rv.get_json()["id"])


def test_a_retried_report_does_not_double_the_alert(client, waiter_token):
    """Same idempotency key → same incident, and no second wave of alerts."""
    key = str(uuid.uuid4())
    body = {"severity": "MEDIUM", "location": "Bar", "description": "Broken glass.",
            "idempotency_key": key}

    first = client.post("/incidents", json=body, headers=auth(waiter_token))
    assert first.status_code == 201
    inc_id = first.get_json()["id"]
    count = len(_notifs_for_incident(inc_id))

    second = client.post("/incidents", json=body, headers=auth(waiter_token))
    assert second.status_code == 200
    assert second.get_json()["duplicate"] is True
    assert len(_notifs_for_incident(inc_id)) == count
