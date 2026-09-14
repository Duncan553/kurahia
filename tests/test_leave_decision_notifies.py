"""
The person whose days off they are gets told the answer.

The approve modal says "The employee will be notified" and nothing sent
anything: the request changed status, the audit log recorded it, and the one
person whose time it was found out by asking again.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import Notification


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def pending(app, waiter_profile):
    with app.app_context():
        lr = LeaveRequest(
            employee_id=waiter_profile.id, leave_type="ANNUAL",
            start_date=(datetime.now(timezone.utc) + timedelta(days=5)).date(),
            end_date=(datetime.now(timezone.utc) + timedelta(days=7)).date(),
            status=LeaveStatus.PENDING.value, idempotency_key=str(uuid.uuid4()))
        db.session.add(lr); db.session.commit()
        return lr.id, waiter_profile.user_id


def _inbox(user_id):
    return db.session.query(Notification).filter_by(
        recipient_user_id=user_id, reference_type="leave_decision").all()


class TestLeaveDecisionNotifies:
    def test_approval_reaches_the_employee(self, client, app, manager_token, pending):
        lr_id, user_id = pending
        rv = client.post(f"/hr/leave-requests/{lr_id}/approve", headers=_hdr(manager_token))
        assert rv.status_code == 200
        with app.app_context():
            msgs = _inbox(user_id)
            assert len(msgs) == 1
            assert "approved" in msgs[0].subject.lower()

    def test_rejection_reaches_the_employee_too(self, client, app, manager_token, pending):
        """A refusal is the answer they most need — silence reads as 'still waiting'."""
        lr_id, user_id = pending
        rv = client.post(f"/hr/leave-requests/{lr_id}/reject",
                         json={"notes": "Fully booked that week"},
                         headers=_hdr(manager_token))
        assert rv.status_code == 200
        with app.app_context():
            msgs = _inbox(user_id)
            assert len(msgs) == 1
            assert "not approved" in msgs[0].subject.lower()
            assert "Fully booked" in msgs[0].body

    def test_the_message_names_who_decided(self, client, app, manager_token, pending):
        lr_id, user_id = pending
        client.post(f"/hr/leave-requests/{lr_id}/approve", headers=_hdr(manager_token))
        with app.app_context():
            assert "manager1" in _inbox(user_id)[0].body

    def test_it_cannot_be_sent_twice(self, client, app, manager_token, pending):
        """Second approve is refused as already-decided, so still one message."""
        lr_id, user_id = pending
        client.post(f"/hr/leave-requests/{lr_id}/approve", headers=_hdr(manager_token))
        client.post(f"/hr/leave-requests/{lr_id}/approve", headers=_hdr(manager_token))
        with app.app_context():
            assert len(_inbox(user_id)) == 1
