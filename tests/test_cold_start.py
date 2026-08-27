"""
Cold start: can a real person build this resort from an empty database?

In production nobody runs a seed script for business data. Someone provisions
the app, logs in, and types everything in. Every other test in this suite leans
on `_seed_test_db`, so that path has NEVER been exercised — which means "it
works" has only ever been proven for a database that arrived pre-populated.

This test starts from nothing and follows the agreed operating model:

    owner    provisions roles, departments and staff
    head chef  owns what the resort MAKES — kitchen dishes, bar drinks, their
               recipes, their ingredients, and their prices
    manager    owns what the resort OFFERS — spa, water and other services,
               and their prices
    nothing sells until someone has said how it moves stock

Where reality diverges from that model, the test says so explicitly rather than
quietly working around it. Those divergences are the findings.
"""
import uuid
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def cold_app():
    """An app with a schema and NOTHING else. No roles, no departments, no users."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        # deliberately no _seed_test_db()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def cold_client(cold_app):
    return cold_app.test_client()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, username, password="ColdStart1!"):
    rv = client.post("/auth/login", json={"username": username, "password": password})
    assert rv.status_code == 200, f"login failed for {username}: {rv.get_json()}"
    return rv.get_json()["access_token"]


# ── Provisioning: the part that legitimately is not "seed data" ──────────────

def _provision_roles_and_departments():
    """What `flask seed roles-depts` does — provisioning, not business data."""
    from app.models.role import Role
    from app.models.department import Department

    # Call the REAL provisioning command's logic, not a copy — otherwise this
    # test proves only that the copy works.
    from app.cli.seed import provision_roles_and_departments
    provision_roles_and_departments()


def _make_user(username, role_name, dept_name):
    from app.models.role import Role
    from app.models.department import Department
    from app.models.user import User

    role = _db.session.query(Role).filter_by(name=role_name).first()
    assert role is not None, f"role {role_name!r} does not exist on a cold start"
    dept = _db.session.query(Department).filter_by(name=dept_name).first()
    u = User(username=username, role_id=role.id, department_id=dept.id)
    u.set_password("ColdStart1!")
    _db.session.add(u)
    _db.session.commit()
    return u.id


# ── FINDING 1 ────────────────────────────────────────────────────────────────

def test_FINDING_head_chef_role_does_not_exist_on_a_cold_start(cold_app):
    """
    The agreed model gives the head chef ownership of the kitchen and bar menu.

    But `flask seed roles-depts` creates only owner(10), manager(5) and staff(1).
    There is no head_chef role, and `MENU_AUTHOR_ROLES = {"head_chef"}` matches by
    NAME — so on a freshly provisioned resort nobody can be a head chef and the
    agreed ownership split cannot be expressed at all.

    Same for every other role the system's own logic depends on: bar_lead,
    front_desk, gate_lead, spa_attendant, water_lead, housekeeping. The dev
    database has them because they were added by hand.
    """
    from app.models.role import Role

    _provision_roles_and_departments()
    names = {r.name for r in _db.session.query(Role).all()}

    expected_by_logic = {
        "head_chef",     # app/pos/menu.py MENU_AUTHOR_ROLES
        "front_desk",    # FRONT_DESK_LEVEL checks across bookings/receipts
        "gate_lead",     # gate issuing
    }
    missing = expected_by_logic - names
    assert not missing, (
        f"roles the application logic depends on are not created on a cold "
        f"start: {sorted(missing)}. `flask seed roles-depts` makes only "
        f"{sorted(names)}."
    )


# ── FINDING 2 ────────────────────────────────────────────────────────────────

def test_FINDING_departments_do_not_match_the_departments_the_app_uses(cold_app):
    """
    Prep stations and department names have to line up: `_can_operate_station`
    matches `actor.department.name.upper()` against the prep station, and the
    agreed model talks about a Spa department.

    Provisioning creates "Pool & Water Activities" and no Spa at all, so a spa
    therapist cannot be given a department that matches the services they sell.
    """
    from app.models.department import Department

    _provision_roles_and_departments()
    names = {d.name for d in _db.session.query(Department).all()}
    assert "Spa" in names or "Spa & Gym" in names, (
        f"the agreed model has a Spa department; cold start creates {sorted(names)}"
    )


# ── The part that DOES work: build a tracked kitchen item from nothing ───────

def test_a_manager_can_build_a_tracked_kitchen_item_from_an_empty_database(cold_app, cold_client):
    """
    The core cold-start path, using manager because head_chef cannot exist yet
    (Finding 1). Ingredient -> menu item -> recipe -> on sale.
    """
    _provision_roles_and_departments()
    _make_user("cold_manager", "manager", "Kitchen")
    token = _login(cold_client, "cold_manager")

    from app.models.department import Department
    kitchen = _db.session.query(Department).filter_by(name="Kitchen").first().id

    # 1. an ingredient — the resort owns nothing yet
    rv = cold_client.post("/inventory/items", json={
        "name": "Tilapia Fillet", "unit": "kg", "department_id": kitchen,
        "cost_per_unit": "600", "reorder_level": "5",
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(token))
    assert rv.status_code == 201, rv.get_json()
    ingredient_id = rv.get_json()["id"]

    # 2. a dish
    rv = cold_client.post("/menu/items", json={
        "name": "Grilled Tilapia", "price": "1800", "category": "Mains",
        "prep_station": "KITCHEN", "department_id": kitchen,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(token))
    assert rv.status_code == 201, rv.get_json()
    item_id = rv.get_json()["id"]

    # 3. the recipe — this is what makes the sale deduct stock
    rv = cold_client.post(f"/menu/items/{item_id}/recipe", json={
        "lines": [{"inventory_item_id": ingredient_id, "quantity": "0.3"}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(token))
    assert rv.status_code in (200, 201), rv.get_json()

    # 4. and it is now tracked, so it may be sold
    from app.models.menu_item import MenuItem, StockTracking
    item = _db.session.get(MenuItem, item_id)
    assert item.stock_tracking != StockTracking.UNTRACKED.value, (
        "an item with a recipe must not still read as UNTRACKED — the tracking "
        "state has to follow the recipe being written, or every newly built item "
        "is blocked from sale despite being correctly configured"
    )


def test_a_manager_can_build_a_SERVICE_from_an_empty_database(cold_app, cold_client):
    """The manager's half of the agreed model: a service that consumes nothing."""
    _provision_roles_and_departments()
    _make_user("cold_manager2", "manager", "General")
    token = _login(cold_client, "cold_manager2")

    from app.models.department import Department
    dept = _db.session.query(Department).filter_by(name="Water Activities").first().id

    rv = cold_client.post("/menu/items", json={
        "name": "Swimming Pool Day Pass", "price": "1000", "category": "Water",
        "prep_station": "NONE", "department_id": dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(token))
    assert rv.status_code == 201, rv.get_json()
    item_id = rv.get_json()["id"]

    rv = cold_client.patch(f"/menu/items/{item_id}", json={"stock_tracking": "SERVICE"},
                           headers=_auth(token))
    assert rv.status_code == 200, rv.get_json()

    from app.models.menu_item import MenuItem, StockTracking
    assert _db.session.get(MenuItem, item_id).stock_tracking == StockTracking.SERVICE.value


def test_an_untracked_item_built_from_scratch_still_cannot_be_sold(cold_app, cold_client):
    """The block has to hold for freshly created items, not just legacy ones."""
    _provision_roles_and_departments()
    _make_user("cold_manager3", "manager", "General")
    token = _login(cold_client, "cold_manager3")

    from app.models.department import Department
    dept = _db.session.query(Department).filter_by(name="General").first().id

    rv = cold_client.post("/menu/items", json={
        "name": "Unclassified New Thing", "price": "500", "category": "Misc",
        "prep_station": "NONE", "department_id": dept,
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(token))
    item_id = rv.get_json()["id"]

    cold_client.post(f"/menu/items/{item_id}/disable", headers=_auth(token))
    rv = cold_client.post(f"/menu/items/{item_id}/enable", headers=_auth(token))
    assert rv.status_code == 400
    assert "stock tracking" in rv.get_json()["error"].lower()


# ── Onboarding: register -> activate -> assign a real role ───────────────────

def test_a_new_registrant_gets_the_named_staff_role_not_an_arbitrary_one(cold_app, cold_client):
    """
    Registration used to pick `Role.query.filter_by(level=1).first()` — "the
    first row that happens to be level 1". There are now four level-1 roles
    (waiter, housekeeping, grounds, staff), so which one a new employee got
    depended on row order. It is chosen by NAME now.
    """
    _provision_roles_and_departments()
    from app.models.department import Department
    from app.models.user import User

    dept = _db.session.query(Department).filter_by(name="Kitchen").first().id
    rv = cold_client.post("/auth/register", json={
        "username": "newhire", "password": "ColdStart1!",
        "full_name": "New Hire", "phone": "+254700111222",
        "department_id": dept, "pin": "4321",
    })
    assert rv.status_code in (200, 201), rv.get_json()

    u = _db.session.query(User).filter_by(username="newhire").first()
    assert u.role.name == "staff", (
        f"a new registrant must get the generic 'staff' role, got {u.role.name!r} — "
        f"guessing here hands out station permissions nobody granted"
    )
    assert u.is_active is False, "a new registrant must wait for approval"


def test_a_manager_can_promote_a_new_hire_to_head_chef(cold_app, cold_client):
    """
    The whole point. Backend always supported PATCH /auth/users/<id> with
    role_id; it was never reachable from any dashboard, so every employee was
    stuck on the level-1 role registration handed out and a head chef could
    never actually be made a head chef.
    """
    _provision_roles_and_departments()
    _make_user("cold_mgr", "manager", "Management")
    token = _login(cold_client, "cold_mgr")

    from app.models.department import Department
    from app.models.role import Role
    from app.models.user import User

    kitchen = _db.session.query(Department).filter_by(name="Kitchen").first().id
    cold_client.post("/auth/register", json={
        "username": "promote_me", "password": "ColdStart1!",
        "full_name": "Promote Me", "phone": "+254700333444",
        "department_id": kitchen, "pin": "5678",
    })
    target = _db.session.query(User).filter_by(username="promote_me").first()
    chef_role = _db.session.query(Role).filter_by(name="head_chef").first()

    rv = cold_client.patch(f"/auth/users/{target.id}",
                           json={"role_id": chef_role.id},
                           headers=_auth(token))
    assert rv.status_code == 200, rv.get_json()

    _db.session.refresh(target)
    assert target.role.name == "head_chef"


def test_a_manager_cannot_promote_someone_to_their_own_level_or_above(cold_app, cold_client):
    """The escalation guard: a manager must not be able to mint another manager."""
    _provision_roles_and_departments()
    _make_user("cold_mgr2", "manager", "Management")
    token = _login(cold_client, "cold_mgr2")

    from app.models.department import Department
    from app.models.role import Role
    from app.models.user import User

    dept = _db.session.query(Department).filter_by(name="Kitchen").first().id
    cold_client.post("/auth/register", json={
        "username": "climber", "password": "ColdStart1!",
        "full_name": "Climber", "phone": "+254700555666",
        "department_id": dept, "pin": "1122",
    })
    target = _db.session.query(User).filter_by(username="climber").first()

    for role_name in ("manager", "owner"):
        role = _db.session.query(Role).filter_by(name=role_name).first()
        rv = cold_client.patch(f"/auth/users/{target.id}", json={"role_id": role.id},
                               headers=_auth(token))
        assert rv.status_code == 403, f"a manager must not be able to assign {role_name}"


def test_the_assignable_role_list_never_offers_an_escalation(cold_app, cold_client):
    """
    /auth/users/meta drives the dropdown, so it must not even OFFER a role the
    server would refuse — otherwise the UI invites an action that always fails.
    """
    _provision_roles_and_departments()
    _make_user("cold_mgr3", "manager", "Management")
    token = _login(cold_client, "cold_mgr3")

    rv = cold_client.get("/auth/users/meta", headers=_auth(token))
    assert rv.status_code == 200
    names = {r["name"] for r in rv.get_json()["roles"]}

    assert "head_chef" in names, "a manager must be able to appoint a head chef"
    assert "manager" not in names and "owner" not in names, (
        "the dropdown must not offer roles at or above the actor's own level"
    )
