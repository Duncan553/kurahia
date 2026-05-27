"""
conftest.py — pytest fixtures shared across all test files.
Each test gets a fresh in-memory SQLite database — no state leaks between tests.
"""
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User


@pytest.fixture(scope="function")
def app():
    """Fresh app + in-memory DB for each test. Config is baked in at creation time."""
    _app = create_app("testing")  # TestingConfig sets sqlite:///:memory: before engine is built

    with _app.app_context():
        _db.create_all()
        _seed_test_db(_app)
        yield _app
        _db.session.remove()
        _db.drop_all()


def _seed_test_db(app):
    """Minimal seed: 3 roles, 1 department, 1 user per role."""
    dept = Department(name="General")
    _db.session.add(dept)
    _db.session.flush()

    owner_role   = Role(name="owner",   level=10)
    manager_role = Role(name="manager", level=5)
    staff_role   = Role(name="staff",   level=1)
    _db.session.add_all([owner_role, manager_role, staff_role])
    _db.session.flush()

    owner = User(username="owner1", role_id=owner_role.id, department_id=dept.id)
    owner.set_password("OwnerPass1!")
    owner.set_pin("1111")

    manager = User(username="manager1", role_id=manager_role.id, department_id=dept.id)
    manager.set_password("ManagerPass1!")
    manager.set_pin("2222")

    staff = User(username="staff1", role_id=staff_role.id, department_id=dept.id)
    staff.set_pin("3333")

    _db.session.add_all([owner, manager, staff])
    _db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def owner_token(client):
    """JWT access token for owner1."""
    rv = client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
    return rv.get_json()["access_token"]


@pytest.fixture
def manager_token(client):
    rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
    return rv.get_json()["access_token"]
