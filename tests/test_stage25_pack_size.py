"""
test_stage25_pack_size.py — Stage 2.5: pack-aware inventory, recipe templates, category defaults.
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
from app.models.recipe_line import RecipeLine
from app.models.menu_item import MenuItem
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.order import Order, OrderStatus
from app.models.tab import Tab
from app.services.stock import get_current_stock


def _user_id(username="manager1"):
    return db.session.query(User).filter_by(username=username).first().id


@pytest.fixture
def spirit_item(app):
    """A pack-aware spirit: 1 bottle = 750ml, KSh 1200/bottle."""
    dept = db.session.query(Department).filter_by(name="Bar").first()
    item = InventoryItem(
        name="Kenya Cane", unit="bottle", department_id=dept.id,
        reorder_level=Decimal("2"), cost_per_unit=Decimal("1200"),
        pack_size=Decimal("750"), pack_unit="ml", category="spirit",
    )
    db.session.add(item)
    db.session.flush()
    # Stock: 5 bottles
    mv = StockMovement(
        item_id=item.id, change_amount=Decimal("5"),
        reason=MovementReason.PURCHASE.value,
        actor_id=_user_id(), idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(mv)
    db.session.commit()
    return item


@pytest.fixture
def plain_item(app):
    """A non-pack item (flour): no pack_size, recipe unit = stock unit."""
    dept = db.session.query(Department).filter_by(name="Kitchen").first()
    item = InventoryItem(
        name="Plain Flour", unit="kg", department_id=dept.id,
        reorder_level=Decimal("5"), cost_per_unit=Decimal("80"),
    )
    db.session.add(item)
    db.session.flush()
    mv = StockMovement(
        item_id=item.id, change_amount=Decimal("10"),
        reason=MovementReason.PURCHASE.value,
        actor_id=_user_id(), idempotency_key=str(uuid.uuid4()),
    )
    db.session.add(mv)
    db.session.commit()
    return item


# ── Model helper tests ───────────────────────────────────────────────────────

class TestPackConversion:
    def test_recipe_to_stock_with_pack(self, app, spirit_item):
        """50ml recipe → 50/750 = 0.0667 bottles."""
        result = spirit_item.recipe_to_stock(Decimal("50"))
        expected = Decimal("50") / Decimal("750")
        assert result == expected

    def test_recipe_to_stock_without_pack(self, app, plain_item):
        """No pack_size → recipe qty passes through unchanged."""
        result = plain_item.recipe_to_stock(Decimal("0.5"))
        assert result == Decimal("0.5")

    def test_recipe_unit_cost_with_pack(self, app, spirit_item):
        """KSh 1200/bottle ÷ 750ml = KSh 1.60/ml."""
        ruc = spirit_item.recipe_unit_cost()
        assert ruc == Decimal("1200") / Decimal("750")

    def test_recipe_unit_cost_without_pack(self, app, plain_item):
        """No pack → cost_per_unit passes through."""
        ruc = plain_item.recipe_unit_cost()
        assert ruc == Decimal("80")


# ── Food cost computation tests ──────────────────────────────────────────────

class TestFoodCostPackAware:
    def test_food_cost_mixed_ingredients(self, app, client, manager_token, spirit_item, plain_item):
        """Cocktail with 50ml KC (pack) + 0.2kg flour (plain) → correct total."""
        menu_item = db.session.query(MenuItem).filter_by(name="Grilled Tilapia").first()

        rl1 = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=spirit_item.id,
            quantity=Decimal("50"), unit="ml",
        )
        rl2 = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=plain_item.id,
            quantity=Decimal("0.2"), unit="kg",
        )
        db.session.add_all([rl1, rl2])
        db.session.commit()

        rv = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
        items = rv.get_json()
        tilapia = next(i for i in items if i["name"] == "Grilled Tilapia")

        # Expected: 50 × (1200/750) + 0.2 × 80 = 80 + 16 = 96
        assert tilapia["food_cost"] is not None
        assert Decimal(tilapia["food_cost"]) == Decimal("96.00")

    def test_in_stock_pack_aware(self, app, client, manager_token, spirit_item):
        """5 bottles in stock, recipe needs 50ml → in_stock=true."""
        menu_item = db.session.query(MenuItem).filter_by(name="Tusker Lager").first()
        rl = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=spirit_item.id,
            quantity=Decimal("50"), unit="ml",
        )
        db.session.add(rl)
        db.session.commit()

        rv = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
        tusker = next(i for i in rv.get_json() if i["name"] == "Tusker Lager")
        assert tusker["in_stock"] is True


# ── Auto-consumption pack conversion ────────────────────────────────────────

class TestConsumptionPackAware:
    def test_consumption_deducts_in_stock_units(self, app, spirit_item):
        """Order 2 cocktails with 50ml KC each → deducts 100/750 bottles from stock."""
        waiter = db.session.query(User).filter_by(username="waiter1").first()
        menu_item = db.session.query(MenuItem).filter_by(name="Grilled Tilapia").first()
        rl = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=spirit_item.id,
            quantity=Decimal("50"), unit="ml",
        )
        db.session.add(rl)
        db.session.flush()

        tab = Tab(opened_by_id=waiter.id)
        db.session.add(tab)
        db.session.flush()

        order = Order(
            tab_id=tab.id, created_by_id=waiter.id,
            status=OrderStatus.SENT.value,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(order)
        db.session.flush()

        oi = OrderItem(
            order_id=order.id, menu_item_id=menu_item.id,
            quantity=Decimal("2"), unit_price_snapshot=Decimal("1200"),
            prep_station_snapshot="KITCHEN",
            status=OrderItemStatus.RECEIVED.value,
        )
        db.session.add(oi)
        db.session.flush()

        stock_before = get_current_stock(spirit_item.id)

        from app.services.consumption import consume_order_item
        with db.session.begin_nested():
            consume_order_item(oi, waiter)
        db.session.commit()

        stock_after = get_current_stock(spirit_item.id)
        # 2 servings × 50ml ÷ 750ml/bottle ≈ 0.1333 bottles
        actual_deduction = stock_before - stock_after
        expected = Decimal("2") * Decimal("50") / Decimal("750")
        assert abs(actual_deduction - expected) < Decimal("0.0001")

    def test_consumption_plain_item_unchanged(self, app, plain_item):
        """Non-pack item: recipe 0.5kg, 1 serving → deducts 0.5kg directly."""
        waiter = db.session.query(User).filter_by(username="waiter1").first()
        menu_item = db.session.query(MenuItem).filter_by(name="Pool Access").first()
        rl = RecipeLine(
            menu_item_id=menu_item.id, inventory_item_id=plain_item.id,
            quantity=Decimal("0.5"), unit="kg",
        )
        db.session.add(rl)
        db.session.flush()

        tab = Tab(opened_by_id=waiter.id)
        db.session.add(tab)
        db.session.flush()

        order = Order(
            tab_id=tab.id, created_by_id=waiter.id,
            status=OrderStatus.SENT.value,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(order)
        db.session.flush()

        oi = OrderItem(
            order_id=order.id, menu_item_id=menu_item.id,
            quantity=Decimal("1"), unit_price_snapshot=Decimal("500"),
            prep_station_snapshot="NONE",
            status=OrderItemStatus.RECEIVED.value,
        )
        db.session.add(oi)
        db.session.flush()

        stock_before = get_current_stock(plain_item.id)

        from app.services.consumption import consume_order_item
        with db.session.begin_nested():
            consume_order_item(oi, waiter)
        db.session.commit()

        stock_after = get_current_stock(plain_item.id)
        assert stock_before - stock_after == Decimal("0.5")


# ── Recipe templates endpoint ────────────────────────────────────────────────

class TestRecipeTemplates:
    def test_get_all_templates(self, app, client, manager_token):
        rv = client.get("/menu/items/templates",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert "shot" in data["types"]
        assert "cocktail" in data["types"]
        assert "mocktail" in data["types"]

    def test_get_specific_template(self, app, client, manager_token):
        rv = client.get("/menu/items/templates?type=cocktail",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["type"] == "cocktail"
        assert len(data["lines"]) == 3
        assert data["lines"][0]["role"] == "spirit"
        assert data["lines"][0]["quantity"] == 50

    def test_shot_template(self, app, client, manager_token):
        rv = client.get("/menu/items/templates?type=shot",
                        headers={"Authorization": f"Bearer {manager_token}"})
        data = rv.get_json()
        assert len(data["lines"]) == 1
        assert data["lines"][0]["quantity"] == 30


# ── Category smart defaults ──────────────────────────────────────────────────

class TestCategoryDefaults:
    def test_spirit_category_auto_fills_pack(self, app, client, manager_token):
        dept = db.session.query(Department).filter_by(name="Bar").first()
        rv = client.post("/inventory/items", json={
            "name": "Jameson", "unit": "bottle",
            "department_id": dept.id, "category": "spirit",
        }, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201

        item = db.session.get(InventoryItem, rv.get_json()["id"])
        assert item.pack_size == Decimal("750")
        assert item.pack_unit == "ml"
        assert item.category == "spirit"

    def test_explicit_pack_overrides_default(self, app, client, manager_token):
        dept = db.session.query(Department).filter_by(name="Bar").first()
        rv = client.post("/inventory/items", json={
            "name": "Magnum Wine", "unit": "bottle",
            "department_id": dept.id, "category": "wine",
            "pack_size": 1500, "pack_unit": "ml",
        }, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201

        item = db.session.get(InventoryItem, rv.get_json()["id"])
        assert item.pack_size == Decimal("1500")

    def test_no_category_no_pack(self, app, client, manager_token):
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        rv = client.post("/inventory/items", json={
            "name": "Test Tomatoes", "unit": "kg",
            "department_id": dept.id,
        }, headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201

        item = db.session.get(InventoryItem, rv.get_json()["id"])
        assert item.pack_size is None
        assert item.category is None

    def test_category_defaults_endpoint(self, app, client, manager_token):
        rv = client.get("/inventory/items/category-defaults",
                        headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["spirit"]["pack_size"] == 750
        assert data["spirit"]["pack_unit"] == "ml"
        assert data["beer"]["pack_size"] == 1

    def test_list_items_includes_pack_fields(self, app, client, owner_token, spirit_item):
        rv = client.get("/inventory/items",
                        headers={"Authorization": f"Bearer {owner_token}"})
        items = rv.get_json()
        kc = next(i for i in items if i["name"] == "Kenya Cane")
        assert kc["pack_size"] == "750.0000"
        assert kc["pack_unit"] == "ml"
        assert kc["category"] == "spirit"
