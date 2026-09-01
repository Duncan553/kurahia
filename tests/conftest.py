"""
conftest.py — pytest fixtures shared across all test files.
Each test gets a fresh in-memory SQLite database — no state leaks between tests.
"""
import pytest
from argon2 import PasswordHasher

import app.models.user as _user_model
from app import create_app
from app.extensions import db as _db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.models.menu_item import MenuItem, PrepStation, StockTracking

# ── Fast Argon2 for tests ONLY ───────────────────────────────────────────────
# Argon2 is SUPPOSED to be slow — that slowness is the whole security property,
# and production must keep the library defaults (t=3, 64MiB, p=4 → ~190ms/hash).
#
# But the `app` fixture below is function-scoped and seeds 9 password/PIN hashes
# for EVERY test. At production cost that is ~1.7s of pure key derivation before
# a single assertion runs: 770 tests x 1.7s ≈ 25 minutes, which was essentially
# the entire suite runtime.
#
# We swap the module-level hasher for a deliberately weak one. This is safe
# because it happens HERE, in the test harness — `app/models/user.py` is not
# modified, so there is no code path by which these parameters can reach
# production. Nothing in the suite asserts anything about KDF strength; the
# tests care that the right password verifies and the wrong one doesn't, which
# is unchanged.
#
# EXCEPT the timing-attack tests. test_security_category_4 proves you cannot
# enumerate usernames by timing /auth/login: the "no such user" path runs a
# DUMMY Argon2 verify so both paths cost the same, asserted within 30%. That
# equalisation only holds while the hash DOMINATES the request — at ~210ms it
# does; at ~1ms it does not, because DB lookup and Flask overhead become
# comparable and swamp a 30% tolerance. Those tests must run at real cost.
# Mark them @pytest.mark.production_hashing and this hook restores it.
_FAST_PH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
_PROD_PH = PasswordHasher()
_user_model._ph = _FAST_PH


def pytest_runtest_setup(item):
    """Pick the hasher per-test, BEFORE any fixture runs.

    This must be a hook, not a fixture: argon2 reads its cost parameters from
    the stored hash string, not from the verifier. So the swap has to happen
    before the `app` fixture seeds its users — otherwise verify() would replay
    the cheap parameters baked into a weak seed hash and the timing test would
    still measure ~1ms. A fixture cannot reliably order itself ahead of `app`;
    pytest_runtest_setup always runs first.

    These tests are also skipped under pytest-xdist. They MEASURE elapsed time,
    and Argon2 runs at parallelism=4: with 4 xdist workers that is up to 16
    threads competing for 8 cores, so the numbers become noise and the 30%
    tolerance fails at random. Verified: `pytest -m production_hashing` passes
    4/4 serially and fails 2/4 under `-n 4`, same code both times. Skipping is
    honest — a timing assertion measured under contention proves nothing.
    Run them in the serial pass; see pytest.ini for the two-command workflow.
    """
    if item.get_closest_marker("production_hashing"):
        if hasattr(item.config, "workerinput"):   # set by xdist inside a worker
            pytest.skip("timing-sensitive: run serially, not under xdist -n")
        _user_model._ph = _PROD_PH
    else:
        _user_model._ph = _FAST_PH


@pytest.fixture(scope="function")
def app():
    """Fresh app + in-memory DB for each test. Config is baked in at creation time."""
    _app = create_app("testing")  # TestingConfig sets sqlite:///:memory: before engine is built

    with _app.app_context():
        _db.create_all()
        _seed_test_db(_app)
        from app.models.system_setting import SystemSetting
        _db.session.add(SystemSetting(key="business_day_start_hour", value="0"))
        _db.session.add(SystemSetting(key="business_day_timezone", value="UTC"))
        _db.session.commit()
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

    # Head chef — authors the food and the juices. Role NAME matters here:
    # menu.py gates on MENU_AUTHOR_ROLES = {"head_chef"}, not on level, because
    # front_desk and gate_lead share level 3 and must not price the menu.
    chef_role = _db.session.query(Role).filter_by(name="head_chef").first()
    if not chef_role:
        chef_role = Role(name="head_chef", level=3)
        _db.session.add(chef_role)
        _db.session.flush()
    chef = User(username="chef1", role_id=chef_role.id, department_id=kitchen_dept.id)
    chef.set_password("ChefPass1!")
    chef.set_pin("6666")

    _db.session.add_all([owner, manager, staff, kitchen_staff, waiter, chef])
    _db.session.flush()

    # Seed representative menu items — CLASSIFIED, because an unclassified item
    # cannot be sold and a fixture that ignores that is not representative.
    #
    # These were all left on the UNTRACKED model default, which was fine while
    # nothing enforced the rule on the sale path. It is enforced now, so a
    # seeded item has to say how it moves stock, exactly like a real one:
    #
    #   food    RECIPE  — a dish assembled from ingredients. The recipe lines
    #                     live in the tests that care about deduction; what
    #                     matters here is that it is DECLARED as a recipe dish.
    #   drink   DIRECT   — one sale, one bottle. Linked per-test where the link
    #                     matters, since the seed holds no inventory rows.
    #   service SERVICE  — a pool pass genuinely consumes nothing. That is a
    #                     positive claim, which is the whole point of SERVICE.
    food = MenuItem(name="Grilled Tilapia",   price="1200", category="Mains",
                    prep_station=PrepStation.KITCHEN.value, department_id=general_dept.id,
                    stock_tracking=StockTracking.RECIPE.value)
    drink = MenuItem(name="Tusker Lager",     price="300",  category="Beer",
                    prep_station=PrepStation.BAR.value,     department_id=general_dept.id,
                    stock_tracking=StockTracking.SERVICE.value)
    service = MenuItem(name="Pool Access",    price="500",  category="Activities",
                    prep_station=PrepStation.NONE.value,    department_id=general_dept.id,
                    stock_tracking=StockTracking.SERVICE.value)

    _db.session.add_all([food, drink, service])
    _db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


def _get_or_create_profile(username, full_name, phone):
    """Idempotent — several fixtures/tests independently want an EmployeeProfile
    for the same shared user (owner1/manager1/waiter1). Whichever runs first
    creates it; everyone else just gets the same row back, so fixture request
    order never causes a duplicate-insert IntegrityError on the unique
    EmployeeProfile.user_id constraint."""
    from app.models.employee_profile import EmployeeProfile
    user = _db.session.query(User).filter_by(username=username).first()
    profile = _db.session.query(EmployeeProfile).filter_by(user_id=user.id).first()
    if not profile:
        profile = EmployeeProfile(user_id=user.id, full_name=full_name, phone=phone)
        _db.session.add(profile)
        _db.session.commit()
    return profile


def _clock_in(profile):
    """Write a CLOCK_IN event directly (bypassing the WiFi-allow-list check
    that only applies inside the real /hr/clock-in endpoint) so the actor
    passes require_clocked_in. ClockEvent is append-only — adding one here is
    harmless even if a test later adds its own events for the same profile.
    occurred_at_utc and idempotency_key have no model-level default (app/hr/
    clock.py always passes both explicitly) — omitting them here was a
    NOT NULL constraint violation."""
    import uuid
    from datetime import datetime, timezone
    from app.models.clock_event import ClockEvent, ClockEventType
    _db.session.add(ClockEvent(
        employee_id=profile.id, event_type=ClockEventType.CLOCK_IN.value,
        occurred_at_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    ))
    _db.session.commit()


@pytest.fixture
def owner_token(client):
    """JWT access token for owner1. Also gives owner1 a profile + clocks them
    in — POS/tabs/payments (require_clocked_in) started requiring both once
    the RBAC-hardening pass added that decorator; these fixtures predate it."""
    rv = client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
    token = rv.get_json()["access_token"]
    _clock_in(_get_or_create_profile("owner1", "Test Owner", "+254700000099"))
    return token


@pytest.fixture
def manager_token(client):
    rv = client.post("/auth/login", json={"username": "manager1", "password": "ManagerPass1!"})
    token = rv.get_json()["access_token"]
    _clock_in(_get_or_create_profile("manager1", "Test Manager", "+254700000002"))
    return token


@pytest.fixture
def kitchen_token(client):
    rv = client.post("/auth/login", json={"username": "kitchen1", "password": "KitchenPass1!"})
    token = rv.get_json()["access_token"]
    _clock_in(_get_or_create_profile("kitchen1", "Test Kitchen", "+254700000003"))
    return token


@pytest.fixture
def chef_token(client):
    rv = client.post("/auth/login", json={"username": "chef1", "password": "ChefPass1!"})
    token = rv.get_json()["access_token"]
    _clock_in(_get_or_create_profile("chef1", "Test Chef", "+254700000006"))
    return token


@pytest.fixture
def waiter_token(client):
    rv = client.post("/auth/login", json={"username": "waiter1", "password": "WaiterPass1!"})
    token = rv.get_json()["access_token"]
    _clock_in(_get_or_create_profile("waiter1", "Test Waiter", "+254700000001"))
    return token


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
    """EmployeeProfile for waiter1. Same name/phone as owner_token & co. use
    via _get_or_create_profile — whichever fixture runs first for a given
    test wins, the other just gets the same row back."""
    return _get_or_create_profile("waiter1", "Test Waiter", "+254700000001")


@pytest.fixture
def manager_profile(app):
    """EmployeeProfile for manager1."""
    return _get_or_create_profile("manager1", "Test Manager", "+254700000002")


@pytest.fixture
def sample_shift(app, waiter_profile):
    """A SCHEDULED shift for waiter_profile on TODAY'S business day.

    It used to be flatly "now + 1 hour", which was a time bomb. The attendance
    board lists shifts whose START falls inside today's business-day window, so
    for the last hour before the rollover "now + 1 hour" landed in TOMORROW and
    the shift disappeared off the board. Three attendance tests failed every
    night for that one hour and passed the other twenty-three — the kind of red
    that gets blamed on whatever was committed most recently.

    Still upcoming when there is room for it, because "rostered but not yet
    clocked in" is what absent_no_notice means. Pulled back inside the window
    when there is not.
    """
    import uuid
    from datetime import datetime, timezone, timedelta
    from app.models.shift import Shift, ShiftStatus
    from app.models.user import User
    from app.services.business_day import business_day_bounds_today

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _day_start, day_end = business_day_bounds_today()
    day_end = day_end.replace(tzinfo=None)

    start = now + timedelta(hours=1)
    if start >= day_end:                 # too close to the rollover
        start = now - timedelta(hours=1)  # already begun, still today

    creator = _db.session.query(User).filter_by(username="manager1").first()
    shift = Shift(
        employee_id=waiter_profile.id,
        scheduled_start_utc=start,
        scheduled_end_utc=start + timedelta(hours=8),
        status=ShiftStatus.SCHEDULED.value,
        created_by_id=creator.id,
        idempotency_key=str(uuid.uuid4()),
    )
    _db.session.add(shift)
    _db.session.commit()
    return shift
