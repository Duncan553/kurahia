"""
test_stage5_auto_draft.py — Stage 5: auto-draft purchase requests + submit/dismiss + COST_VARIANCE.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.department import Department
from app.models.user import User
from app.models.stock_movement import StockMovement, MovementReason
from app.models.purchase_request import PurchaseRequest, RequestStatus
from app.models.recipe_line import RecipeLine
from app.models.menu_item import MenuItem
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.order import Order, OrderStatus
from app.models.judge_alert import JudgeAlert
from app.services.stock import get_current_stock


def _system_user_id():
    return db.session.query(User).filter_by(username="manager1").first().id


@pytest.fixture
def inv_item(app):
    """An inventory item with reorder_level=10, zero stock."""
    dept = db.session.query(Department).filter_by(name="Kitchen").first()
    item = InventoryItem(
        name="Test Flour", unit="kg", department_id=dept.id,
        reorder_level=Decimal("10"), cost_per_unit=Decimal("80"),
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture
def stocked_item(app):
    """An item with reorder_level=10 and current stock of 15 (above reorder)."""
    dept = db.session.query(Department).filter_by(name="Kitchen").first()
    item = InventoryItem(
        name="Test Rice", unit="kg", department_id=dept.id,
        reorder_level=Decimal("10"), cost_per_unit=Decimal("120"),
    )
    db.session.add(item)
    db.session.flush()
    mv = StockMovement(
        item_id=item.id, change_amount=Decimal("15"),
        reason=MovementReason.PURCHASE.value,
        actor_id=_system_user_id(),
        idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(mv)
    db.session.commit()
    return item


# ── Auto-draft CLI tests ─────────────────────────────────────────────────────

class TestAutoDraft:
    def test_creates_draft_for_item_below_reorder(self, app, inv_item):
        """Item at zero stock with reorder_level=10 → DRAFT with qty=20."""
        runner = app.test_cli_runner()
        result = runner.invoke(args=["inventory", "auto-draft"])
        assert "1 DRAFT" in result.output

        pr = db.session.query(PurchaseRequest).filter_by(item_id=inv_item.id).first()
        assert pr is not None
        assert pr.status == RequestStatus.DRAFT.value
        assert pr.system_generated is True
        assert pr.requested_by_id is None
        assert pr.quantity == Decimal("20")

    def test_skips_item_above_reorder(self, app, stocked_item):
        """Item with stock=15, reorder=10 → no draft created."""
        runner = app.test_cli_runner()
        result = runner.invoke(args=["inventory", "auto-draft"])
        assert "0 DRAFT" in result.output

        pr = db.session.query(PurchaseRequest).filter_by(item_id=stocked_item.id).first()
        assert pr is None

    def test_idempotent_no_duplicate_drafts(self, app, inv_item):
        """Running auto-draft twice doesn't create duplicates."""
        runner = app.test_cli_runner()
        runner.invoke(args=["inventory", "auto-draft"])
        runner.invoke(args=["inventory", "auto-draft"])

        count = db.session.query(PurchaseRequest).filter_by(item_id=inv_item.id).count()
        assert count == 1

    def test_skips_item_with_pending_request(self, app, inv_item):
        """Item already has a PENDING request → no draft."""
        pr = PurchaseRequest(
            item_id=inv_item.id, quantity=Decimal("5"),
            status=RequestStatus.PENDING.value,
            requested_by_id=db.session.query(db.text("id")).from_statement(
                db.text("SELECT id FROM users WHERE username='manager1'")
            ).scalar(),
        )
        db.session.add(pr)
        db.session.commit()

        runner = app.test_cli_runner()
        result = runner.invoke(args=["inventory", "auto-draft"])
        assert "0 DRAFT" in result.output

    def test_suggested_qty_formula(self, app):
        """qty = (reorder × 2) − current. Item with reorder=10, stock=3 → qty=17."""
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        item = InventoryItem(
            name="Test Sugar", unit="kg", department_id=dept.id,
            reorder_level=Decimal("10"),
        )
        db.session.add(item)
        db.session.flush()
        mv = StockMovement(
            item_id=item.id, change_amount=Decimal("3"),
            reason=MovementReason.PURCHASE.value,
            actor_id=_system_user_id(),
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(mv)
        db.session.commit()

        runner = app.test_cli_runner()
        runner.invoke(args=["inventory", "auto-draft"])

        pr = db.session.query(PurchaseRequest).filter_by(item_id=item.id).first()
        assert pr is not None
        assert pr.quantity == Decimal("17")


# ── Submit / Dismiss endpoint tests ──────────────────────────────────────────

class TestSubmitDraft:
    def _make_draft(self, item_id):
        pr = PurchaseRequest(
            item_id=item_id, quantity=Decimal("20"),
            status=RequestStatus.DRAFT.value,
            system_generated=True, requested_by_id=None,
        )
        db.session.add(pr)
        db.session.commit()
        return pr.id

    def test_submit_moves_draft_to_pending(self, app, client, manager_token, inv_item):
        pr_id = self._make_draft(inv_item.id)
        rv = client.post(f"/inventory/purchase-requests/{pr_id}/submit",
                         json={}, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "PENDING"

    def test_submit_allows_quantity_edit(self, app, client, manager_token, inv_item):
        pr_id = self._make_draft(inv_item.id)
        rv = client.post(f"/inventory/purchase-requests/{pr_id}/submit",
                         json={"quantity": "15"},
                         headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        assert Decimal(rv.get_json()["quantity"]) == Decimal("15")

    def test_submit_rejects_non_draft(self, app, client, manager_token, inv_item):
        from app.models.user import User
        mgr = db.session.query(User).filter_by(username="manager1").first()
        pr = PurchaseRequest(
            item_id=inv_item.id, quantity=Decimal("5"),
            status=RequestStatus.PENDING.value,
            requested_by_id=mgr.id,
        )
        db.session.add(pr)
        db.session.commit()

        rv = client.post(f"/inventory/purchase-requests/{pr.id}/submit",
                         json={}, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 400

    def test_dismiss_moves_draft_to_rejected(self, app, client, manager_token, inv_item):
        pr_id = self._make_draft(inv_item.id)
        rv = client.post(f"/inventory/purchase-requests/{pr_id}/dismiss",
                         json={}, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "REJECTED"


# ── List filter tests ────────────────────────────────────────────────────────

class TestListFilters:
    def test_filter_by_status_and_system_generated(self, app, client, manager_token, inv_item):
        pr = PurchaseRequest(
            item_id=inv_item.id, quantity=Decimal("20"),
            status=RequestStatus.DRAFT.value,
            system_generated=True, requested_by_id=None,
        )
        db.session.add(pr)
        db.session.commit()

        rv = client.get("/inventory/purchase-requests?status=DRAFT&system_generated=true",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data) == 1
        assert data[0]["system_generated"] is True
        assert data[0]["requested_by"] == "system"
        assert data[0]["unit"] == "kg"


# ── COST_VARIANCE judge tests ───────────────────────────────────────────────

class TestCostVariance:
    def _setup_recipe_and_sales(self, app, variance_factor=Decimal("1.3")):
        """Create ingredient, recipe, order item (served), and stock movements.
        variance_factor controls how much actual consumption differs from expected.
        """
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        waiter = db.session.query(User).filter_by(username="waiter1").first()

        ing = InventoryItem(
            name="CV Flour", unit="kg", department_id=dept.id,
            reorder_level=Decimal("10"), cost_per_unit=Decimal("100"),
        )
        db.session.add(ing)
        db.session.flush()

        menu_item = db.session.query(MenuItem).filter_by(name="Grilled Tilapia").first()
        rl = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=ing.id,
            quantity=Decimal("0.5"), unit="kg",
        )
        db.session.add(rl)
        db.session.flush()

        from app.models.tab import Tab
        tab = Tab(opened_by_id=waiter.id, reference="CV Test")
        db.session.add(tab)
        db.session.flush()

        now = datetime.now(timezone.utc)
        order = Order(
            tab_id=tab.id, created_by_id=waiter.id,
            status=OrderStatus.SENT.value,
            idempotency_key=str(uuid.uuid4()),
            sent_at=now - timedelta(hours=2),
        )
        db.session.add(order)
        db.session.flush()

        oi = OrderItem(
            order_id=order.id, menu_item_id=menu_item.id,
            quantity=Decimal("10"), unit_price_snapshot=Decimal("1200"),
            prep_station_snapshot="KITCHEN",
            status=OrderItemStatus.SERVED.value,
            served_at=now - timedelta(hours=1),
        )
        db.session.add(oi)
        db.session.flush()

        # Expected consumption: 10 servings × 0.5 kg = 5 kg
        # Actual consumption: 5 × variance_factor
        actual_qty = Decimal("5") * variance_factor
        mv = StockMovement(
            item_id=ing.id, change_amount=-actual_qty,
            reason=MovementReason.SALE.value,
            actor_id=waiter.id,
            idempotency_key=str(uuid.uuid4()),
            timestamp_utc=now - timedelta(minutes=30),
        )
        db.session.add(mv)
        db.session.commit()
        return ing

    def test_cost_variance_fires_high_alert(self, app):
        """30% overspend → HIGH alert (>25% threshold)."""
        self._setup_recipe_and_sales(app, variance_factor=Decimal("1.3"))
        from app.judge.engine import run_weekly
        now = datetime.now(timezone.utc)
        alerts = run_weekly(now - timedelta(days=7), now)
        assert alerts >= 1

        alert = db.session.query(JudgeAlert).filter_by(alert_type="COST_VARIANCE").first()
        assert alert is not None
        assert "overspent" in alert.description
        assert alert.severity == "HIGH"

    def test_cost_variance_fires_medium_for_small_deviation(self, app):
        """20% overspend → MEDIUM alert."""
        self._setup_recipe_and_sales(app, variance_factor=Decimal("1.2"))
        from app.judge.engine import run_weekly
        now = datetime.now(timezone.utc)
        alerts = run_weekly(now - timedelta(days=7), now)
        assert alerts >= 1

        alert = db.session.query(JudgeAlert).filter_by(alert_type="COST_VARIANCE").first()
        assert alert is not None
        assert alert.severity == "MEDIUM"

    def test_no_alert_within_threshold(self, app):
        """10% overspend → no alert (below 15% threshold)."""
        self._setup_recipe_and_sales(app, variance_factor=Decimal("1.1"))
        from app.judge.engine import run_weekly
        now = datetime.now(timezone.utc)
        run_weekly(now - timedelta(days=7), now)

        alert = db.session.query(JudgeAlert).filter_by(alert_type="COST_VARIANCE").first()
        assert alert is None

    def test_underspend_also_fires(self, app):
        """30% underspend → alert with 'underspent'."""
        self._setup_recipe_and_sales(app, variance_factor=Decimal("0.7"))
        from app.judge.engine import run_weekly
        now = datetime.now(timezone.utc)
        run_weekly(now - timedelta(days=7), now)

        alert = db.session.query(JudgeAlert).filter_by(alert_type="COST_VARIANCE").first()
        assert alert is not None
        assert "underspent" in alert.description
