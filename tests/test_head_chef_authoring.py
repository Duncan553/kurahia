"""
The head chef owns the menu: the dishes, what goes into them, and what they cost.

This was previously manager-only (level 5), and head_chef is level 3 — so the
person who actually designs the food could not add a dish, write a recipe, or
define an ingredient. Recipes matter most: a recipe is what makes a sale deduct
the right stock, so leaving it to someone who does not cook is how items end up
untracked.

These are ROLE checks, not level checks, and that distinction is the point:
head_chef shares level 3 with front_desk and gate_lead, who must not be able to
reprice the menu.
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User


def _login(client, username, password):
    rv = client.post("/auth/login", json={"username": username, "password": password})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["access_token"]


def _make_user(username: str, role_name: str, level: int, dept_name: str = "Kitchen") -> None:
    role = db.session.query(Role).filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, level=level)
        db.session.add(role)
        db.session.flush()
    dept = db.session.query(Department).filter_by(name=dept_name).first()
    u = User(username=username, role_id=role.id, department_id=dept.id)
    u.set_password("ChefPass1!")
    db.session.add(u)
    db.session.commit()


@pytest.fixture
def chef_token(app, client):
    """A head chef: level 3, and the person who designs the food."""
    _make_user("chef_test", "head_chef", 3, "Kitchen")
    return _login(client, "chef_test", "ChefPass1!")


@pytest.fixture
def gate_token(app, client):
    """Gate lead: ALSO level 3, and must not be able to touch the menu."""
    _make_user("gate_test", "gate_lead", 3, "General")
    return _login(client, "gate_test", "ChefPass1!")


@pytest.fixture
def general_dept(app):
    return db.session.query(Department).filter_by(name="General").first().id


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Menu authoring ────────────────────────────────────────────────────────────

def test_head_chef_can_create_a_menu_item_with_a_price(app, client, chef_token, general_dept):
    rv = client.post("/menu/items", json={
        "name": "Chef Special Tilapia", "price": "2200", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    assert rv.status_code == 201, rv.get_json()
    assert Decimal(rv.get_json()["price"]) == Decimal("2200")


def test_head_chef_can_reprice_a_dish(app, client, chef_token, general_dept):
    rv = client.post("/menu/items", json={
        "name": "Repriced Dish", "price": "1000", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    item_id = rv.get_json()["id"]

    rv = client.patch(f"/menu/items/{item_id}", json={"price": "1350"}, headers=_auth(chef_token))
    assert rv.status_code == 200, rv.get_json()
    assert Decimal(rv.get_json()["price"]) == Decimal("1350")


def test_head_chef_owns_the_BAR_menu_too(app, client, chef_token, general_dept):
    """Cocktails and juices are recipes like any other — same author."""
    rv = client.post("/menu/items", json={
        "name": "Dawa Cocktail", "price": "650", "category": "Cocktail",
        "prep_station": "BAR", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    assert rv.status_code == 201, rv.get_json()


# ── Recipes: the thing that makes stock deduct ────────────────────────────────

def test_head_chef_can_write_the_recipe(app, client, chef_token, general_dept):
    from app.models.inventory_item import InventoryItem

    rv = client.post("/menu/items", json={
        "name": "Recipe Owner Dish", "price": "900", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    item_id = rv.get_json()["id"]

    ing = InventoryItem(name="Chef Test Flour", unit="kg",
                        department_id=general_dept, cost_per_unit=Decimal("120"))
    db.session.add(ing)
    db.session.commit()

    rv = client.post(f"/menu/items/{item_id}/recipe", json={
        "lines": [{"inventory_item_id": ing.id, "quantity": "0.25"}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    assert rv.status_code in (200, 201), rv.get_json()


def test_head_chef_can_define_an_ingredient(app, client, chef_token, general_dept):
    """A recipe cannot be written until its ingredients exist as stock items."""
    rv = client.post("/inventory/items", json={
        "name": "Chef Test Saffron", "unit": "g", "department_id": general_dept,
        "cost_per_unit": "900", "reorder_level": "10",
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(chef_token))
    assert rv.status_code == 201, rv.get_json()


# ── The boundary: same level, no business here ────────────────────────────────

def test_gate_lead_at_the_same_level_cannot_touch_the_menu(app, client, gate_token, general_dept):
    """
    This is why the check is by ROLE and not by level. gate_lead is also level 3;
    a `level >= 3` gate would have handed menu pricing to the gate staff.
    """
    rv = client.post("/menu/items", json={
        "name": "Gate Should Not Add This", "price": "100", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(gate_token))
    assert rv.status_code == 403
    assert "error" in rv.get_json()


def test_gate_lead_cannot_define_ingredients(app, client, gate_token, general_dept):
    rv = client.post("/inventory/items", json={
        "name": "Gate Should Not Add This Either", "unit": "kg",
        "department_id": general_dept, "cost_per_unit": "10",
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(gate_token))
    assert rv.status_code == 403


def test_a_waiter_still_cannot_reprice_anything(app, client, waiter_token, general_dept):
    rv = client.post("/menu/items", json={
        "name": "Waiter Should Not Add This", "price": "100", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": general_dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(waiter_token))
    assert rv.status_code == 403
