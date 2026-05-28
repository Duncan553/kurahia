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
from app.models.menu_item import MenuItem, PrepStation


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
    """Minimal seed: roles, departments, users per role, and base menu items."""
    general_dept = Department(name="General")
    kitchen_dept = Department(name="Kitchen")
    bar_dept     = Department(name="Bar")
    foh_dept     = Department(name="Front-of-House")
    _db.session.add_all([general_dept, kitchen_dept, bar_dept, foh_dept])
    _db.session.flush()

    owner_role   = Role(name="owner",   level=10)
    manager_role = Role(name="manager", level=5)
    staff_role   = Role(name="staff",   level=1)
    _db.session.add_all([owner_role, manager_role, staff_role])
    _db.session.flush()

    owner = User(username="owner1", role_id=owner_role.id, department_id=general_dept.id)
    owner.set_password("OwnerPass1!")
    owner.set_pin("1111")

    manager = User(username="manager1", role_id=manager_role.id, department_id=general_dept.id)
    manager.set_password("ManagerPass1!")
    manager.set_pin("2222")

    staff = User(username="staff1", role_id=staff_role.id, department_id=general_dept.id)
    staff.set_pin("3333")

    # Kitchen staff — can receive/ready kitchen items, cannot create orders
    kitchen_staff = User(username="kitchen1", role_id=staff_role.id, department_id=kitchen_dept.id)
    kitchen_staff.set_password("KitchenPass1!")
    kitchen_staff.set_pin("4444")

    # Waiter (Front-of-House) — creates orders, serves items
    waiter = User(username="waiter1", role_id=staff_role.id, department_id=foh_dept.id)
    waiter.set_password("WaiterPass1!")
    waiter.set_pin("5555")

    _db.session.add_all([owner, manager, staff, kitchen_staff, waiter])
    _db.session.flush()

    # Seed representative menu items
    food = MenuItem(name="Grilled Tilapia",   price="1200", category="Mains",
                    prep_station=PrepStation.KITCHEN.value, department_id=general_dept.id)
    drink = MenuItem(name="Tusker Lager",     price="300",  category="Beer",
                    prep_station=PrepStation.BAR.value,     department_id=general_dept.id)
    service = MenuItem(name="Pool Access",    price="500",  category="Activities",
                    prep_station=PrepStation.NONE.value,    department_id=general_dept.id)

    _db.session.add_all([food, drink, service])
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


@pytest.fixture
def kitchen_token(client):
    rv = client.post("/auth/login", json={"username": "kitchen1", "password": "KitchenPass1!"})
    return rv.get_json()["access_token"]


@pytest.fixture
def waiter_token(client):
    rv = client.post("/auth/login", json={"username": "waiter1", "password": "WaiterPass1!"})
    return rv.get_json()["access_token"]


@pytest.fixture
def food_item_id(app):
    """ID of the Grilled Tilapia menu item seeded by _seed_test_db."""
    mi = _db.session.query(MenuItem).filter_by(name="Grilled Tilapia").first()
    return mi.id


@pytest.fixture
def drink_item_id(app):
    mi = _db.session.query(MenuItem).filter_by(name="Tusker Lager").first()
    return mi.id


@pytest.fixture
def service_item_id(app):
    mi = _db.session.query(MenuItem).filter_by(name="Pool Access").first()
    return mi.id


@pytest.fixture
def general_dept_id(app):
    """ID of the General department seeded by _seed_test_db."""
    from app.models.department import Department
    dept = _db.session.query(Department).filter_by(name="General").first()
    return dept.id


# ── HR fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def wifi_allowed(app):
    """Add 127.0.0.0/8 to WiFiAllowList so test client (127.0.0.1) can clock in."""
    from app.models.wifi_allow_list import WiFiAllowList
    entry = WiFiAllowList(ssid="staff-dev-net", ip_cidr="127.0.0.0/8", label="Dev")
    _db.session.add(entry)
    _db.session.commit()
    return entry


@pytest.fixture
def waiter_profile(app):
    """EmployeeProfile for waiter1."""
    from app.models.employee_profile import EmployeeProfile
    from app.models.user import User
    user = _db.session.query(User).filter_by(username="waiter1").first()
    profile = EmployeeProfile(user_id=user.id, full_name="Test Waiter", phone="+254700000001")
    _db.session.add(profile)
    _db.session.commit()
    return profile


@pytest.fixture
def manager_profile(app):
    """EmployeeProfile for manager1."""
    from app.models.employee_profile import EmployeeProfile
    from app.models.user import User
    user = _db.session.query(User).filter_by(username="manager1").first()
    profile = EmployeeProfile(user_id=user.id, full_name="Test Manager", phone="+254700000002")
    _db.session.add(profile)
    _db.session.commit()
    return profile


@pytest.fixture
def sample_shift(app, waiter_profile):
    """A SCHEDULED shift for waiter_profile starting 1 hour from now."""
    import uuid
    from datetime import datetime, timezone, timedelta
    from app.models.shift import Shift, ShiftStatus
    from app.models.user import User
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    creator = _db.session.query(User).filter_by(username="manager1").first()
    shift = Shift(
        employee_id=waiter_profile.id,
        scheduled_start_utc=now + timedelta(hours=1),
        scheduled_end_utc=now + timedelta(hours=9),
        status=ShiftStatus.SCHEDULED.value,
        created_by_id=creator.id,
        idempotency_key=str(uuid.uuid4()),
    )
    _db.session.add(shift)
    _db.session.commit()
    return shift
