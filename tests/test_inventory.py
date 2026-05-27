"""
test_inventory.py — Chunk 2 test suite.

Covers:
  1.  Stock level = sum of movements (logical concurrency: multiple writes → correct sum)
  2.  Variance math in a known scenario
  3.  Spoilage / staff-meal / sent-back routed correctly (don't mix into variance wrong)
  4.  Watch-list items get tighter effective tolerance
  5.  Approval chain enforced (manager can't approve; must be owner)
  6.  Receipt mandatory for purchase
  7.  Decimal precision preserved end-to-end
  8.  Audit log gets an entry per movement
  9.  Idempotency keys block duplicate movements
  10. Role enforcement: staff can't submit a count; staff can't view /judge/alerts
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement, MovementReason
from app.models.stock_count import StockCount, CountType
from app.models.audit_log import AuditLog
from app.services.stock import get_current_stock
from app.services.variance import compute_variance


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def item(app):
    """A seeded Kitchen item for use in tests."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(
            name="Test Oil", unit="litre", department_id=dept.id, reorder_level="5",
        )
        db.session.add(it)
        db.session.commit()
        return it.id  # return ID, not ORM object (avoids detached-instance errors)


@pytest.fixture
def staff_item(app):
    """A staff-food item."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(
            name="Staff Beans", unit="kg", department_id=dept.id,
            reorder_level="2", is_staff_food=True,
        )
        db.session.add(it)
        db.session.commit()
        return it.id


@pytest.fixture
def watch_item(app):
    """A watch-list item with no explicit tolerance (uses computed tight tolerance)."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(
            name="Watch Whisky", unit="litre", department_id=dept.id,
            reorder_level="1", is_watch_list=True,
        )
        db.session.add(it)
        db.session.commit()
        return it.id


@pytest.fixture
def manager_token(client):
    rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
    return rv.get_json()["access_token"]


@pytest.fixture
def owner_token(client):
    rv = client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
    return rv.get_json()["access_token"]


@pytest.fixture
def staff_token(client):
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    return rv.get_json()["access_token"]


# ── 1. Stock level = sum of movements ────────────────────────────────────────

def test_stock_is_derived_from_movements(app, item):
    with app.app_context():
        # Add three movements: +10, +5, -3 → expected 12
        for amount, reason in [
            (Decimal("10"), MovementReason.PURCHASE),
            (Decimal("5"),  MovementReason.PURCHASE),
            (Decimal("-3"), MovementReason.SPOILAGE),
        ]:
            db.session.add(StockMovement(
                item_id=item, change_amount=amount, reason=reason.value,
                actor_id=_owner_id(app), idempotency_key=str(uuid.uuid4()),
            ))
        db.session.commit()

        stock = get_current_stock(item)
        assert stock == Decimal("12"), f"Expected 12, got {stock}"


def test_multiple_writes_correct_sum(app, item):
    """Simulate concurrent-style writes — sum must be exact regardless of order."""
    with app.app_context():
        movements = [Decimal("7"), Decimal("3"), Decimal("-2"), Decimal("5"), Decimal("-1")]
        for amt in movements:
            reason = MovementReason.PURCHASE if amt > 0 else MovementReason.SPOILAGE
            db.session.add(StockMovement(
                item_id=item, change_amount=amt, reason=reason.value,
                actor_id=_owner_id(app), idempotency_key=str(uuid.uuid4()),
            ))
        db.session.commit()

        expected = sum(movements, Decimal("0"))
        assert get_current_stock(item) == expected


# ── 2. Variance math ─────────────────────────────────────────────────────────

def test_variance_math_known_scenario(app, item):
    """
    Opening count: 10
    Purchase:      +5  (total 15)
    Spoilage:      -2  (total 13 expected)
    Closing count:  11 → variance = 11 - 13 = -2 (missing stock)
    """
    with app.app_context():
        actor_id = _owner_id(app)
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(hours=2)
        period_end   = now

        # Opening count (before period)
        db.session.add(StockCount(
            item_id=item, counted_amount=Decimal("10"), actor_id=actor_id,
            count_type=CountType.OPENING.value,
            timestamp_utc=period_start - timedelta(minutes=1),
            idempotency_key=str(uuid.uuid4()),
        ))
        # Purchase movement in period
        db.session.add(StockMovement(
            item_id=item, change_amount=Decimal("5"), reason=MovementReason.PURCHASE.value,
            actor_id=actor_id, idempotency_key=str(uuid.uuid4()),
            timestamp_utc=period_start + timedelta(minutes=10),
        ))
        # Spoilage in period
        db.session.add(StockMovement(
            item_id=item, change_amount=Decimal("-2"), reason=MovementReason.SPOILAGE.value,
            actor_id=actor_id, idempotency_key=str(uuid.uuid4()),
            timestamp_utc=period_start + timedelta(minutes=20),
        ))
        # Closing count in period
        db.session.add(StockCount(
            item_id=item, counted_amount=Decimal("11"), actor_id=actor_id,
            count_type=CountType.CLOSING.value,
            timestamp_utc=period_end - timedelta(minutes=1),
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()

        result = compute_variance(item, period_start, period_end)

        assert result is not None
        assert result["opening"]          == Decimal("10")
        assert result["purchases"]        == Decimal("5")
        assert result["consumption"]      == Decimal("2")
        assert result["expected_closing"] == Decimal("13")
        assert result["actual_closing"]   == Decimal("11")
        assert result["variance"]         == Decimal("-2")
        assert result["flagged"] is True   # -2 out of 13 = 15.4% > 5% tolerance


# ── 3. Movement routing ───────────────────────────────────────────────────────

def test_spoilage_counted_as_consumption(app, item):
    """Spoilage must appear in variance consumption, not purchases."""
    with app.app_context():
        actor_id = _owner_id(app)
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(hours=1)

        # Purchase (in)
        db.session.add(StockMovement(
            item_id=item, change_amount=Decimal("10"), reason=MovementReason.PURCHASE.value,
            actor_id=actor_id, idempotency_key=str(uuid.uuid4()),
            timestamp_utc=period_start + timedelta(minutes=5),
        ))
        # Spoilage (out)
        db.session.add(StockMovement(
            item_id=item, change_amount=Decimal("-3"), reason=MovementReason.SPOILAGE.value,
            actor_id=actor_id, idempotency_key=str(uuid.uuid4()),
            timestamp_utc=period_start + timedelta(minutes=10),
        ))
        # Closing count
        db.session.add(StockCount(
            item_id=item, counted_amount=Decimal("7"), actor_id=actor_id,
            count_type=CountType.CLOSING.value, timestamp_utc=now - timedelta(minutes=1),
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()

        result = compute_variance(item, period_start, now)
        assert result["consumption"] == Decimal("3")
        assert result["purchases"]   == Decimal("10")


def test_staff_meal_only_touches_staff_food(client, app, item, staff_item, manager_token):
    """Staff meal on a non-staff-food item must be rejected."""
    rv = client.post(
        "/inventory/movements/staff-meal",
        json={"item_id": item, "quantity": "1", "idempotency_key": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 400
    assert "staff-food" in rv.get_json()["error"].lower()


def test_staff_meal_on_staff_food_succeeds(client, app, staff_item, manager_token):
    rv = client.post(
        "/inventory/movements/staff-meal",
        json={"item_id": staff_item, "quantity": "1.5", "idempotency_key": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 201


# ── 4. Watch-list tighter tolerance ──────────────────────────────────────────

def test_watch_list_tighter_tolerance(app, watch_item):
    with app.app_context():
        item = db.session.get(InventoryItem, watch_item)
        # Watch-list default = system_default / 2 = 5 / 2 = 2.5%
        assert item.effective_tolerance() == Decimal("2.5")


def test_regular_item_default_tolerance(app, item):
    with app.app_context():
        it = db.session.get(InventoryItem, item)
        assert it.effective_tolerance() == Decimal("5")


# ── 5. Approval chain ────────────────────────────────────────────────────────

def test_only_owner_can_approve_purchase_request(app, client, item, manager_token, owner_token):
    # Create request
    rv = client.post(
        "/inventory/purchase-requests",
        json={"item_id": item, "quantity": "10"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 201
    pr_id = rv.get_json()["id"]

    # Manager tries to approve — must fail
    rv2 = client.post(
        f"/inventory/purchase-requests/{pr_id}/approve",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv2.status_code == 403

    # Owner approves — must succeed
    rv3 = client.post(
        f"/inventory/purchase-requests/{pr_id}/approve",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rv3.status_code == 200
    assert rv3.get_json()["status"] == "APPROVED"


# ── 6. Receipt mandatory ──────────────────────────────────────────────────────

def test_purchase_rejected_without_receipt(client, app, item, manager_token):
    rv = client.post(
        "/inventory/purchases",
        json={
            "item_id": item, "quantity": "5", "actual_cost": "500",
            # receipt_photo_path deliberately omitted
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 400
    assert "receipt" in rv.get_json()["error"].lower()


def test_purchase_accepted_with_receipt(client, app, item, manager_token):
    rv = client.post(
        "/inventory/purchases",
        json={
            "item_id": item, "quantity": "5", "actual_cost": "500",
            "receipt_photo_path": "/receipts/test.jpg",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert rv.status_code == 201
    # Stock should now be 5
    with app.app_context():
        assert get_current_stock(item) == Decimal("5")


# ── 7. Decimal precision ──────────────────────────────────────────────────────

def test_decimal_precision_preserved(app, item):
    """1.25 is exactly representable; verify it survives the DB round-trip."""
    with app.app_context():
        mv = StockMovement(
            item_id=item, change_amount=Decimal("1.25"),
            reason=MovementReason.PURCHASE.value,
            actor_id=_owner_id(app), idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(mv)
        db.session.commit()

        stock = get_current_stock(item)
        assert stock == Decimal("1.25"), f"Precision lost: got {stock}"


# ── 8. Audit log per movement ─────────────────────────────────────────────────

def test_audit_log_written_on_spoilage(client, app, item, manager_token):
    pre_count = _audit_count(app)
    client.post(
        "/inventory/movements/spoilage",
        json={"item_id": item, "quantity": "1", "idempotency_key": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert _audit_count(app) > pre_count


# ── 9. Idempotency blocks duplicates ──────────────────────────────────────────

def test_idempotency_blocks_duplicate_movement(client, app, item, manager_token):
    key = str(uuid.uuid4())
    payload = {
        "item_id": item, "quantity": "2",
        "receipt_photo_path": "/r/test.jpg",
        "actual_cost": "200",
        "idempotency_key": key,
    }
    rv1 = client.post("/inventory/purchases", json=payload,
                      headers={"Authorization": f"Bearer {manager_token}"})
    rv2 = client.post("/inventory/purchases", json=payload,
                      headers={"Authorization": f"Bearer {manager_token}"})

    assert rv1.status_code == 201
    assert rv2.status_code == 200
    assert rv2.get_json().get("duplicate") is True

    # Stock must only reflect one write
    with app.app_context():
        assert get_current_stock(item) == Decimal("2")


# ── 10. Role enforcement ──────────────────────────────────────────────────────

def test_staff_cannot_submit_count(client, app, item, staff_token):
    rv = client.post(
        "/inventory/counts",
        json={"item_id": item, "counted_amount": "10",
              "count_type": "DAILY", "idempotency_key": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert rv.status_code == 403


def test_staff_cannot_view_judge_alerts(client, staff_token):
    rv = client.get("/judge/alerts", headers={"Authorization": f"Bearer {staff_token}"})
    assert rv.status_code == 403


def test_owner_can_view_judge_alerts(client, owner_token):
    rv = client.get("/judge/alerts", headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200


# ── Helpers ───────────────────────────────────────────────────────────────────

def _owner_id(app) -> str:
    from app.models.user import User
    return db.session.query(User).filter_by(username="owner1").first().id


def _audit_count(app) -> int:
    with app.app_context():
        return db.session.query(AuditLog).count()
