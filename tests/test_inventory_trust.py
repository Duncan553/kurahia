"""
test_inventory_trust.py — Stage 3: trust-based counting.

Covers: trust tier computation, for_count=true param, dept-scoped access,
auto-demotion on variance, demotion expiry, audit log content.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.stock_count import StockCount, CountType
from app.models.count_demotion import CountDemotion
from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
from app.models.audit_log import AuditLog
from app.services.trust import compute_trust_tier, MUST_COUNT, QUICK_VERIFY, AUTO_CONFIRMED


# ── Shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def general_item(app):
    """A stable inventory item in General dept (manager's dept) — no watch list, old enough."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        # Use created_at 6 weeks ago so it passes the "new item" check
        it = InventoryItem(
            name="Stable Tusker",
            unit="crate",
            department_id=dept.id,
            reorder_level="1",
            created_at=datetime.now(timezone.utc) - timedelta(weeks=6),
        )
        db.session.add(it); db.session.commit()
        return it.id


@pytest.fixture
def kitchen_item(app):
    """An inventory item in Kitchen dept — for dept-scoping tests."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        it = InventoryItem(
            name="Kitchen Spice",
            unit="g",
            department_id=dept.id,
            reorder_level="10",
            created_at=datetime.now(timezone.utc) - timedelta(weeks=6),
        )
        db.session.add(it); db.session.commit()
        return it.id


def _add_movements(app, item_id, count, reason=MovementReason.PURCHASE.value):
    """Write `count` stock movements for item_id so activity thresholds are met."""
    with app.app_context():
        from app.models.user import User
        actor = db.session.query(User).filter_by(username="manager1").first()
        for _ in range(count):
            db.session.add(StockMovement(
                item_id=item_id,
                change_amount=Decimal("1"),
                reason=reason,
                actor_id=actor.id,
                idempotency_key=str(uuid.uuid4()),
            ))
        db.session.commit()


def _submit_count(client, token, item_id, counted, count_type="DAILY"):
    return client.post("/inventory/counts", json={
        "item_id":        item_id,
        "counted_amount": counted,
        "count_type":     count_type,
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})


# ── Trust tier: MUST_COUNT conditions ────────────────────────────────────────

def test_watch_list_item_is_must_count(app, general_item):
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        it.is_watch_list = True; db.session.commit()
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    assert tier == MUST_COUNT
    assert reason == "watch_list"


def test_new_item_is_must_count(app):
    """Item created < 4 weeks ago → MUST_COUNT regardless of other factors."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(
            name="Brand New Item",
            unit="piece",
            department_id=dept.id,
            reorder_level="0",
            # created_at defaults to now — which is < 4 weeks ago
        )
        db.session.add(it); db.session.commit()
        it = db.session.get(InventoryItem, it.id)
        tier, reason = compute_trust_tier(it)
    assert tier == MUST_COUNT
    assert reason == "new_item"


def test_item_with_null_created_at_is_must_count(app):
    """Items with no created_at (pre-migration data) default to MUST_COUNT (safe)."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(name="Legacy Item", unit="kg", department_id=dept.id, reorder_level="0")
        it.created_at = None  # simulate pre-migration row
        db.session.add(it); db.session.commit()
        it = db.session.get(InventoryItem, it.id)
        tier, reason = compute_trust_tier(it)
    assert tier == MUST_COUNT
    assert reason == "new_item"


def test_recent_count_variance_is_must_count(app, client, manager_token, general_item):
    """An item that showed variance in a recent count → MUST_COUNT (COUNT movement exists)."""
    # Buy 10 units then count 8 → adjustment -2 → COUNT movement written
    _submit_count(client, manager_token, general_item, counted="10")  # zero adj, no movement
    # Now create a COUNT movement directly (simulating a variance count)
    with app.app_context():
        from app.models.user import User
        actor = db.session.query(User).filter_by(username="manager1").first()
        db.session.add(StockMovement(
            item_id=general_item,
            change_amount=Decimal("-2"),
            reason=MovementReason.COUNT.value,
            actor_id=actor.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    assert tier == MUST_COUNT
    assert reason == "recent_variance"


def test_judge_flagged_item_is_must_count(app, general_item):
    """Open JudgeAlert within last 7 days → MUST_COUNT."""
    with app.app_context():
        db.session.add(JudgeAlert(
            item_id=general_item,
            alert_type="VARIANCE",
            severity=AlertSeverity.HIGH.value,
            description="Suspicious variance",
            status=AlertStatus.OPEN.value,
        ))
        db.session.commit()
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    assert tier == MUST_COUNT
    assert reason == "judge_flagged"


def test_dismissed_judge_alert_not_must_count(app, general_item):
    """Dismissed JudgeAlert does not force MUST_COUNT."""
    with app.app_context():
        db.session.add(JudgeAlert(
            item_id=general_item,
            alert_type="VARIANCE",
            severity=AlertSeverity.LOW.value,
            description="Closed alert",
            status=AlertStatus.DISMISSED.value,
        ))
        db.session.commit()
        it = db.session.get(InventoryItem, general_item)
        tier, _ = compute_trust_tier(it)
    # No other flags → should be QUICK_VERIFY (low activity) not MUST_COUNT
    assert tier != MUST_COUNT


# ── Trust tier: QUICK_VERIFY ──────────────────────────────────────────────────

def test_low_activity_item_is_quick_verify(app, general_item):
    """Stable old item with < 5 movements in 30 days → QUICK_VERIFY."""
    _add_movements(app, general_item, count=2)   # only 2 movements
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    assert tier == QUICK_VERIFY
    assert reason == "low_activity"


# ── Trust tier: AUTO_CONFIRMED ────────────────────────────────────────────────

def test_stable_high_activity_item_is_auto_confirmed(app, general_item):
    """Old item with 5+ movements and no variance → AUTO_CONFIRMED."""
    _add_movements(app, general_item, count=6)   # 6 movements
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    assert tier == AUTO_CONFIRMED
    assert reason == "stable"


# ── for_count=true query param ────────────────────────────────────────────────

def test_for_count_adds_trust_tier(app, client, manager_token, general_item):
    """GET /inventory/items?for_count=true includes trust_tier per item + summary."""
    rv = client.get("/inventory/items?for_count=true",
                    headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    body = rv.get_json()
    assert "summary" in body
    assert "items" in body
    assert "total" in body["summary"]
    items = body["items"]
    match = next((i for i in items if i["id"] == general_item), None)
    assert match is not None
    assert "trust_tier" in match
    assert "trust_reason" in match


def test_for_count_false_returns_flat_list(app, client, manager_token):
    """Without for_count=true the response is still a flat JSON array."""
    rv = client.get("/inventory/items",
                    headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_for_count_summary_counts(app, client, manager_token, general_item):
    """Summary totals across all tiers sum to the item count."""
    rv = client.get("/inventory/items?for_count=true",
                    headers={"Authorization": f"Bearer {manager_token}"})
    body = rv.get_json()
    s = body["summary"]
    assert s["MUST_COUNT"] + s["QUICK_VERIFY"] + s["AUTO_CONFIRMED"] == s["total"]


# ── Dept-scoped access ────────────────────────────────────────────────────────

def test_head_chef_can_count_own_dept(app, client, kitchen_item):
    """A level-5 Kitchen user can count Kitchen items."""
    with app.app_context():
        from app.models.department import Department
        from app.models.role import Role
        from app.models.user import User
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        mgr_role = db.session.query(Role).filter_by(level=5).first()
        chef = User(username="chef_test_s3", role_id=mgr_role.id, department_id=kitchen.id)
        chef.set_password("ChefPass1!"); chef.set_pin("7777")
        db.session.add(chef); db.session.commit()

    rv_login = client.post("/auth/login", json={"username":"chef_test_s3","password":"ChefPass1!"})
    chef_token = rv_login.get_json()["access_token"]

    rv = _submit_count(client, chef_token, kitchen_item, counted="5")
    assert rv.status_code == 201, rv.get_json()


def test_head_chef_cannot_count_other_dept(app, client, general_item):
    """A level-5 Kitchen user cannot count items from another department."""
    with app.app_context():
        from app.models.department import Department
        from app.models.role import Role
        from app.models.user import User
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        mgr_role = db.session.query(Role).filter_by(level=5).first()
        chef = User(username="chef_test_s3b", role_id=mgr_role.id, department_id=kitchen.id)
        chef.set_password("ChefPass1!"); chef.set_pin("7778")
        db.session.add(chef); db.session.commit()

    rv_login = client.post("/auth/login", json={"username":"chef_test_s3b","password":"ChefPass1!"})
    chef_token = rv_login.get_json()["access_token"]

    # general_item is in General dept, chef is in Kitchen
    rv = _submit_count(client, chef_token, general_item, counted="5")
    assert rv.status_code == 403


def test_owner_can_count_any_dept(app, client, owner_token, kitchen_item):
    """An owner (level 10) can count items from any department."""
    rv = _submit_count(client, owner_token, kitchen_item, counted="5")
    assert rv.status_code == 201, rv.get_json()


# ── Auto-demotion on variance ─────────────────────────────────────────────────

def test_auto_confirmed_variance_triggers_demotion(app, client, manager_token, general_item):
    """When AUTO_CONFIRMED item shows variance on count, a CountDemotion is written."""
    # Make the item AUTO_CONFIRMED: 6+ movements, old, no flags
    _add_movements(app, general_item, count=6)
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        tier, _ = compute_trust_tier(it)
    assert tier == AUTO_CONFIRMED, f"Precondition: expected AUTO_CONFIRMED, got {tier}"

    # Submit a count with variance (counted 999, actual is ~6 from movements)
    rv = _submit_count(client, manager_token, general_item, counted="999")
    assert rv.status_code == 201
    body = rv.get_json()
    assert body["demoted"] is True
    assert body["prior_tier"] == AUTO_CONFIRMED

    # Confirm CountDemotion row written
    with app.app_context():
        dem = db.session.query(CountDemotion).filter_by(item_id=general_item).first()
        assert dem is not None
        assert dem.reason == "SPOT_CHECK_VARIANCE"

    # Now the item should be MUST_COUNT (active demotion)
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        tier2, reason2 = compute_trust_tier(it)
    assert tier2 == MUST_COUNT
    assert reason2 == "prior_variance"


def test_no_demotion_on_zero_variance(app, client, manager_token, general_item):
    """Exact match count (zero variance) on AUTO_CONFIRMED item → no demotion."""
    _add_movements(app, general_item, count=6)
    # Count exactly what's in stock
    with app.app_context():
        from app.services.stock import get_current_stock
        current = get_current_stock(general_item)

    rv = _submit_count(client, manager_token, general_item, counted=str(current))
    assert rv.status_code == 201
    assert rv.get_json()["demoted"] is False

    with app.app_context():
        dem = db.session.query(CountDemotion).filter_by(item_id=general_item).first()
        assert dem is None


def test_must_count_variance_no_demotion(app, client, manager_token, general_item):
    """Variance on a MUST_COUNT item does NOT create a demotion (already flagged)."""
    # Keep item as MUST_COUNT (watch_list=True)
    with app.app_context():
        it = db.session.get(InventoryItem, general_item)
        it.is_watch_list = True; db.session.commit()

    rv = _submit_count(client, manager_token, general_item, counted="999")
    assert rv.status_code == 201
    assert rv.get_json()["demoted"] is False  # only AUTO_CONFIRMED demotes


def test_demotion_expires_after_4_weeks(app, general_item):
    """A CountDemotion older than 4 weeks no longer forces MUST_COUNT."""
    with app.app_context():
        from app.models.user import User
        actor = db.session.query(User).filter_by(username="manager1").first()
        # Write a demotion dated 5 weeks ago (expired)
        old_demotion = CountDemotion(
            item_id=general_item,
            demoted_by_id=actor.id,
            reason="SPOT_CHECK_VARIANCE",
            demoted_at=datetime.now(timezone.utc) - timedelta(weeks=5),
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(old_demotion); db.session.commit()
        it = db.session.get(InventoryItem, general_item)
        tier, reason = compute_trust_tier(it)
    # Demotion expired; with no other flags and no movements, should be QUICK_VERIFY
    assert tier != MUST_COUNT or reason != "prior_variance"


# ── Audit log ─────────────────────────────────────────────────────────────────

def test_count_audit_log_includes_tier(app, client, manager_token, general_item):
    """Count submission writes an audit log entry containing the trust tier."""
    _add_movements(app, general_item, count=6)  # make AUTO_CONFIRMED
    _submit_count(client, manager_token, general_item, counted="5")

    with app.app_context():
        log = db.session.query(AuditLog).filter_by(action="inventory.count").first()
        assert log is not None
        assert "tier=" in log.details
