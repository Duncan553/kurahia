"""
test_inventory_recipes.py — Stage 1: recipes, weighted-average cost,
computed fields (food_cost, food_cost_pct, in_stock), catalog notifications.
"""
import uuid
from decimal import Decimal
import pytest
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.recipe_line import RecipeLine
from app.models.menu_item import MenuItem
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.services.stock import get_current_stock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def inv_item(app):
    """An inventory item in General dept (where manager1 works, so it shows in their list)."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(name="Test Beef", unit="kg", department_id=dept.id, reorder_level="5")
        db.session.add(it)
        db.session.commit()
        return it.id


@pytest.fixture
def inv_item2(app):
    """A second inventory item in General dept."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="General").first()
        it = InventoryItem(name="Test Sauce", unit="litre", department_id=dept.id, reorder_level="1")
        db.session.add(it)
        db.session.commit()
        return it.id


def _buy(client, token, item_id, qty, total_cost):
    """Helper: POST a purchase for item_id with given qty and total cost."""
    return client.post("/inventory/purchases", json={
        "item_id": item_id,
        "quantity": qty,
        "actual_cost": total_cost,
        "receipt_photo_path": "receipts/test.jpg",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})


def _get_item_cost(app, item_id):
    """Read cost_per_unit from DB."""
    with app.app_context():
        it = db.session.get(InventoryItem, item_id)
        return Decimal(str(it.cost_per_unit)) if it.cost_per_unit is not None else None


# ── 1.2: Weighted-average cost on PURCHASE ────────────────────────────────────

def test_cost_per_unit_first_purchase(app, client, manager_token, inv_item):
    """First purchase sets cost_per_unit = total_cost / qty."""
    rv = _buy(client, manager_token, inv_item, qty=10, total_cost=6000)
    assert rv.status_code == 201, rv.get_json()
    cpu = _get_item_cost(app, inv_item)
    assert cpu == Decimal("600.0000"), f"Expected 600, got {cpu}"


def test_cost_weighted_average(app, client, manager_token, inv_item):
    """Second purchase uses weighted-average: (10×600 + 10×800) / 20 = 700."""
    _buy(client, manager_token, inv_item, qty=10, total_cost=6000)  # 10kg @ 600/kg
    _buy(client, manager_token, inv_item, qty=10, total_cost=8000)  # 10kg @ 800/kg
    cpu = _get_item_cost(app, inv_item)
    assert cpu == Decimal("700.0000"), f"Expected 700, got {cpu}"


def test_cost_per_unit_in_item_list(app, client, manager_token, inv_item):
    """GET /inventory/items includes cost_per_unit field."""
    _buy(client, manager_token, inv_item, qty=5, total_cost=3000)   # 5kg @ 600/kg
    rv = client.get("/inventory/items", headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    items = rv.get_json()
    match = next((i for i in items if i["id"] == inv_item), None)
    assert match is not None
    assert match["cost_per_unit"] == "600.0000"


# ── 1.4: Recipe CRUD ──────────────────────────────────────────────────────────

def test_recipe_create_and_get(app, client, manager_token, food_item_id, inv_item):
    """Manager can POST a recipe; GET returns the same lines."""
    rv = client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 201, rv.get_json()
    assert rv.get_json()["lines"] == 1

    rv2 = client.get(f"/menu/items/{food_item_id}/recipe",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv2.status_code == 200
    lines = rv2.get_json()
    assert len(lines) == 1
    assert lines[0]["quantity"] == "0.3000"
    assert lines[0]["unit"] == "kg"


def test_recipe_replace(app, client, manager_token, food_item_id, inv_item, inv_item2):
    """Second POST replaces previous recipe — old lines deactivated, new ones written."""
    client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})

    client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [
            {"inventory_item_id": inv_item,  "quantity": "0.2"},
            {"inventory_item_id": inv_item2, "quantity": "0.05"},
        ],
    }, headers={"Authorization": f"Bearer {manager_token}"})

    rv = client.get(f"/menu/items/{food_item_id}/recipe",
                    headers={"Authorization": f"Bearer {manager_token}"})
    lines = rv.get_json()
    assert len(lines) == 2  # old 0.3 line deactivated, two new lines active

    # Confirm old line is inactive in DB
    with app.app_context():
        inactive = db.session.query(RecipeLine).filter_by(
            menu_item_id=food_item_id, is_active=False
        ).count()
        assert inactive == 1


def test_recipe_auth_staff_denied(app, client, kitchen_token, food_item_id, inv_item):
    """Staff (level=1) cannot set a recipe."""
    rv = client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {kitchen_token}"})
    assert rv.status_code == 403


def test_head_chef_recipe_access(app, client, food_item_id, inv_item):
    """A level-5 user in Kitchen dept (head chef) can also set recipes."""
    with app.app_context():
        from app.models.department import Department
        from app.models.role import Role
        kitchen = db.session.query(Department).filter_by(name="Kitchen").first()
        mgr_role = db.session.query(Role).filter_by(level=5).first()
        head_chef = __import__('app.models.user', fromlist=['User']).User(
            username="head_chef_test", role_id=mgr_role.id, department_id=kitchen.id
        )
        head_chef.set_password("ChefPass1!")
        head_chef.set_pin("9999")
        db.session.add(head_chef)
        db.session.commit()

    rv = client.post("/auth/login", json={"username": "head_chef_test", "password": "ChefPass1!"})
    chef_token = rv.get_json()["access_token"]

    rv2 = client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.25"}],
    }, headers={"Authorization": f"Bearer {chef_token}"})
    assert rv2.status_code == 201, rv2.get_json()


def test_recipe_audit_log(app, client, manager_token, food_item_id, inv_item):
    """Setting a recipe writes an audit log entry."""
    client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})
    with app.app_context():
        log = db.session.query(AuditLog).filter_by(action="menu.recipe.set").first()
        assert log is not None


def test_recipe_unknown_menu_item(app, client, manager_token, inv_item):
    """POST recipe to non-existent menu item → 404."""
    rv = client.post(f"/menu/items/{uuid.uuid4()}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "1"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 404


# ── 1.5: Computed fields on GET /menu/items ───────────────────────────────────

def test_food_cost_computed(app, client, manager_token, food_item_id, inv_item):
    """After adding recipe + purchase, food_cost and food_cost_pct appear correctly."""
    # Set recipe: 0.3 kg per dish
    client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})
    # Set cost: 10kg total cost 6000 → KSh 600/kg
    _buy(client, manager_token, inv_item, qty=10, total_cost=6000)

    rv = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
    items = rv.get_json()
    food = next(i for i in items if i["id"] == food_item_id)

    # food_cost = 0.3 kg × KSh 600/kg = KSh 180
    # Grilled Tilapia price = KSh 1200 → food_cost_pct = 180/1200 × 100 = 15%
    assert food["food_cost"] == "180.00"
    assert food["gross_margin"] == "1020.00"
    assert food["food_cost_pct"] == "15.00"


def test_menu_item_no_recipe_null_food_cost(app, client, manager_token, food_item_id):
    """Menu item without a recipe returns null food_cost fields."""
    rv = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
    items = rv.get_json()
    food = next(i for i in items if i["id"] == food_item_id)
    assert food["food_cost"] is None
    assert food["in_stock"] is None


def test_in_stock_reflects_actual_stock(app, client, manager_token, food_item_id, inv_item):
    """in_stock=True when stock >= qty; in_stock=False when stock < qty."""
    # Set recipe: 0.3 kg per dish
    client.post(f"/menu/items/{food_item_id}/recipe", json={
        "lines": [{"inventory_item_id": inv_item, "quantity": "0.3"}],
    }, headers={"Authorization": f"Bearer {manager_token}"})

    # No stock yet → in_stock=False
    rv = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
    food = next(i for i in rv.get_json() if i["id"] == food_item_id)
    assert food["in_stock"] is False

    # Buy stock
    _buy(client, manager_token, inv_item, qty=1, total_cost=600)

    rv2 = client.get("/menu/items", headers={"Authorization": f"Bearer {manager_token}"})
    food2 = next(i for i in rv2.get_json() if i["id"] == food_item_id)
    assert food2["in_stock"] is True


# ── 1.6: Catalog notifications ────────────────────────────────────────────────

def test_catalog_notification_on_create(app, client, manager_token):
    """Creating an inventory item queues a notification to the owner."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="Kitchen").first()
        dept_id = dept.id

    rv = client.post("/inventory/items", json={
        "name": "New Special Item",
        "unit": "piece",
        "department_id": dept_id,
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 201, rv.get_json()

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.body.contains("New Special Item")
        ).first()
        assert notif is not None
        assert "added" in notif.body
        assert notif.status == "QUEUED"


def test_catalog_notification_on_disable(app, client, manager_token, inv_item):
    """Disabling an inventory item queues an owner notification."""
    rv = client.post(f"/inventory/items/{inv_item}/disable",
                     headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200

    with app.app_context():
        notif = db.session.query(Notification).filter(
            Notification.body.contains("Test Beef"),
            Notification.body.contains("deactivated"),
        ).first()
        assert notif is not None


def test_catalog_notification_owner_only(app, client, manager_token):
    """Notification goes to owner (level 10), not to the manager themselves."""
    with app.app_context():
        from app.models.department import Department
        dept = db.session.query(Department).filter_by(name="Bar").first()
        dept_id = dept.id

    client.post("/inventory/items", json={
        "name": "Owner-notif Test Item",
        "unit": "bottle",
        "department_id": dept_id,
    }, headers={"Authorization": f"Bearer {manager_token}"})

    with app.app_context():
        from app.models.user import User
        from app.models.role import Role
        owner = db.session.query(User).join(User.role).filter(Role.level >= 10).first()
        notif = db.session.query(Notification).filter_by(
            recipient_user_id=owner.id
        ).filter(Notification.body.contains("Owner-notif Test Item")).first()
        assert notif is not None
