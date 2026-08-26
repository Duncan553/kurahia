"""
Regression tests for the BUDGET_EXCEEDED judge alert.

This check existed but had NEVER fired. `_run_budget_exceeded` read the spend as:

    spent = Decimal(str(b.spent)) if hasattr(b, 'spent') and b.spent else Decimal("0")

`Budget` has no `spent` column (app/models/budget.py), so `hasattr` was always
False, `spent` was always 0, and the `if spent <= budget_amt: continue` below it
always short-circuited. Spend is DERIVED from the purchase ledger (invariant 2),
so it now calls get_budget_spend().

There were no tests for this check at all, which is why it went unnoticed.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.budget import Budget
from app.models.department import Department
from app.models.inventory_item import InventoryItem
from app.models.judge_alert import JudgeAlert
from app.models.purchase import Purchase
from app.models.user import User


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def _make_spend(dept_id: str, amount: str, recorded_by_id: str) -> None:
    """Record a purchase against a department, which is what budget spend sums."""
    item = InventoryItem(
        name=f"Judge Test Item {uuid.uuid4().hex[:6]}",
        unit="kg",
        department_id=dept_id,
        cost_per_unit=Decimal("1"),
    )
    db.session.add(item)
    db.session.flush()

    now = datetime.now(timezone.utc)
    db.session.add(Purchase(
        item_id=item.id,
        quantity=Decimal("1"),
        actual_cost=Decimal(amount),
        receipt_photo_path="/images/receipts/test.jpg",
        recorded_by_id=recorded_by_id,
        # Must land inside the current month — that is the window the check sums.
        timestamp_added=now,
        idempotency_key=str(uuid.uuid4()),
    ))
    db.session.commit()


@pytest.fixture
def owner_id(app):
    return db.session.query(User).filter_by(username="owner1").first().id


@pytest.fixture
def dept_id(app):
    return db.session.query(Department).filter_by(name="Kitchen").first().id


def test_budget_exceeded_fires_when_spend_passes_the_budget(app, dept_id, owner_id):
    """The regression: with spend over budget, an alert must actually be created."""
    from app.judge.engine import _run_budget_exceeded

    db.session.add(Budget(
        department_id=dept_id, period=_current_period(),
        amount=Decimal("1000"), set_by_id=owner_id,
    ))
    db.session.commit()

    _make_spend(dept_id, "1500", owner_id)   # 150% of budget

    assert _run_budget_exceeded() == 1, "over-budget department must raise one alert"

    alert = db.session.query(JudgeAlert).filter_by(alert_type="BUDGET_EXCEEDED").one()
    # Plain-English message (invariant 5) carrying both numbers.
    assert "Kitchen" in alert.description
    assert "150%" in alert.description


def test_budget_not_exceeded_stays_silent(app, dept_id, owner_id):
    """Under budget must NOT alert — the check has to discriminate, not just fire."""
    from app.judge.engine import _run_budget_exceeded

    db.session.add(Budget(
        department_id=dept_id, period=_current_period(),
        amount=Decimal("1000"), set_by_id=owner_id,
    ))
    db.session.commit()

    _make_spend(dept_id, "400", owner_id)

    assert _run_budget_exceeded() == 0
    assert db.session.query(JudgeAlert).filter_by(alert_type="BUDGET_EXCEEDED").count() == 0


def test_budget_severity_escalates_past_120_percent(app, dept_id, owner_id):
    """HIGH above 120% of budget, MEDIUM below it."""
    from app.judge.engine import _run_budget_exceeded

    db.session.add(Budget(
        department_id=dept_id, period=_current_period(),
        amount=Decimal("1000"), set_by_id=owner_id,
    ))
    db.session.commit()

    _make_spend(dept_id, "1300", owner_id)   # 130%
    _run_budget_exceeded()

    alert = db.session.query(JudgeAlert).filter_by(alert_type="BUDGET_EXCEEDED").one()
    assert alert.severity == "HIGH"


def test_spend_is_scoped_to_the_budgets_own_department(app, dept_id, owner_id):
    """Another department's purchases must not push this one over budget."""
    from app.judge.engine import _run_budget_exceeded

    other = db.session.query(Department).filter_by(name="Bar").first()

    db.session.add(Budget(
        department_id=dept_id, period=_current_period(),
        amount=Decimal("1000"), set_by_id=owner_id,
    ))
    db.session.commit()

    _make_spend(other.id, "9000", owner_id)   # all of it on Bar, none on Kitchen

    assert _run_budget_exceeded() == 0, "Bar's spend must not breach Kitchen's budget"


def test_budget_for_a_different_period_is_ignored(app, dept_id, owner_id):
    """A budget row for another month must not be evaluated against this month."""
    from app.judge.engine import _run_budget_exceeded

    db.session.add(Budget(
        department_id=dept_id, period="1999-01",
        amount=Decimal("1"), set_by_id=owner_id,
    ))
    db.session.commit()

    _make_spend(dept_id, "5000", owner_id)

    assert _run_budget_exceeded() == 0
