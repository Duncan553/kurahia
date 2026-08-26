"""
Regression tests for the money half of the performance score.

compute_performance receives an EmployeeProfile.id (app/hr/performance.py:50).
Shift / LeaveRequest / ClockEvent are all keyed by profile, so punctuality and
attendance were fine. But:

  - CashReconciliation.staff_id is a FK to users.id
  - get_void_rates reports Order.created_by_id, also users.id

Comparing either to a profile id never matched, so short_count and void_rate_pct
were permanently 0 and cash_health / void_health were pinned at 100 for
everyone. Per SCORE_WEIGHTS those carry 0.15 + 0.15 — so 30% of every composite
score was a hardcoded constant, and a cashier with chronic shortfalls scored
identically to a clean one.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus
from app.models.employee_profile import EmployeeProfile
from app.models.user import User
from app.services.hr import compute_performance


@pytest.fixture
def waiter_profile_ids(app):
    """(profile_id, user_id) for waiter1 — deliberately different UUIDs."""
    user = db.session.query(User).filter_by(username="waiter1").first()
    profile = db.session.query(EmployeeProfile).filter_by(user_id=user.id).first()
    if not profile:
        profile = EmployeeProfile(user_id=user.id, full_name="Test Waiter",
                                  phone="+254700000001")
        db.session.add(profile)
        db.session.commit()
    assert profile.id != user.id, "the whole bug depends on these being different"
    return profile.id, user.id


def _period():
    end = datetime.now(timezone.utc) + timedelta(days=1)
    return end - timedelta(days=30), end


def _add_shortfall(user_id: str) -> None:
    """A SHORT reconciliation, keyed by users.id as the real model requires."""
    start, end = _period()
    # reconciled_by_id is NOT NULL — a manager always counts the cash in.
    manager_id = db.session.query(User).filter_by(username="manager1").first().id
    db.session.add(CashReconciliation(
        staff_id=user_id,
        reconciled_by_id=manager_id,
        status=ReconciliationStatus.SHORT.value,
        expected_amount=Decimal("1000"),
        actual_amount=Decimal("800"),
        difference=Decimal("-200"),
        period_start_utc=start,
        period_end_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    ))
    db.session.commit()


def test_cash_shortfall_actually_lowers_the_score(app, waiter_profile_ids):
    """The regression: a real shortfall must move cash_health off 100."""
    profile_id, user_id = waiter_profile_ids
    start, end = _period()

    before = compute_performance(profile_id, start, end)
    assert Decimal(before["cash_health_score"]) == Decimal("100")

    _add_shortfall(user_id)

    after = compute_performance(profile_id, start, end)
    assert Decimal(after["cash_health_score"]) < Decimal("100"), (
        "a SHORT reconciliation must reduce cash_health — if this is still 100 the "
        "lookup is comparing a profile id against users.id again"
    )
    assert after["detail"]["cash_shortfalls"] == 1


def test_composite_score_reflects_the_shortfall(app, waiter_profile_ids):
    """cash_health carries real weight, so the composite must move too."""
    profile_id, user_id = waiter_profile_ids
    start, end = _period()

    before = Decimal(compute_performance(profile_id, start, end)["composite_score"])
    _add_shortfall(user_id)
    after = Decimal(compute_performance(profile_id, start, end)["composite_score"])

    assert after < before, "30% of the score must not be a constant"


def test_another_employees_shortfall_does_not_touch_this_one(app, waiter_profile_ids):
    """Scoped to the right person — the fix must not over-match."""
    profile_id, _ = waiter_profile_ids
    other = db.session.query(User).filter_by(username="kitchen1").first()
    start, end = _period()

    _add_shortfall(other.id)

    scores = compute_performance(profile_id, start, end)
    assert Decimal(scores["cash_health_score"]) == Decimal("100")
    assert scores["detail"]["cash_shortfalls"] == 0
