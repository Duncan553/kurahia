"""
tests/test_housekeeping.py — Housekeeping module tests.

Coverage:
  1.  Assign: manager assigns housekeeper → 200, assigned_to set + audit log
  2.  Assign: waiter cannot assign → 403
  3.  Assign: missing cleaning_id → 400
  4.  Assign: missing housekeeper_id → 400
  5.  Assign: non-existent cleaning_id → 404
  6.  Start: assigned housekeeper starts → 200, status = CLEANING
  7.  Start: non-assigned staff cannot start → 403
  8.  Start: manager can start without being assigned → 200
  9.  Start: illegal transition (CLEAN → CLEANING) → 400
  10. Complete: housekeeper completes → 200, status = CLEAN, completed_at set
  11. Complete: non-assigned staff cannot complete → 403
  12. Complete: notes saved when provided
  13. Complete: illegal transition (DIRTY → CLEAN) → 400
  14. Complete: audit log written
  15. Inspect: manager inspects CLEAN room → 200, status = INSPECTED, inspected_by set
  16. Inspect: waiter cannot inspect → 403
  17. Inspect: cannot inspect DIRTY room → 400 (skips CLEANING + CLEAN)
  18. Flag: housekeeper flags with reason → 200, is_flagged = True + audit log
  19. Flag: missing reason → 400
  20. Flag: waiter (Front-of-House) cannot flag → 403
  21. Status: manager gets all rooms → 200, list returned
  22. Status: housekeeping dept staff can view → 200
  23. Status: waiter cannot view → 403
  24. Happy path: DIRTY → assign → start → complete → inspect (all audit logs present)
"""
import pytest
from datetime import datetime, timezone

from app.extensions import db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.models.bookable_resource import BookableResource, ResourceType
from app.models.cleaning_status import CleaningStatus, CleaningStatusEnum
from app.models.audit_log import AuditLog


def auth(token):
    """Build Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ── Local fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def hk_user_id(app):
    """
    Create a 'Housekeeping' department + housekeeper1 user (level-1 staff).
    Returns the user's ID string.
    """
    dept = Department(name="Housekeeping")
    db.session.add(dept)
    db.session.flush()

    # Reuse the existing staff role (level 1) seeded by conftest
    staff_role = db.session.query(Role).filter_by(level=1).first()

    user = User(username="housekeeper1", role_id=staff_role.id, department_id=dept.id)
    user.set_password("HkPass1!")
    user.set_pin("6666")
    db.session.add(user)
    db.session.commit()
    return user.id


@pytest.fixture
def hk_token(client, hk_user_id):
    """JWT access token for housekeeper1 (Housekeeping dept, level 1)."""
    rv = client.post("/auth/login", json={"username": "housekeeper1", "password": "HkPass1!"})
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["access_token"]


@pytest.fixture
def villa_id(app):
    """Create one active villa resource. Returns its ID string."""
    resource = BookableResource(
        name="Villa Sunset",
        resource_type=ResourceType.VILLA.value,
        base_price="5000",
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource.id


@pytest.fixture
def dirty_id(app, villa_id):
    """DIRTY CleaningStatus for Villa Sunset (not yet assigned). Returns record ID."""
    record = CleaningStatus(
        resource_id=villa_id,
        status=CleaningStatusEnum.DIRTY.value,
    )
    db.session.add(record)
    db.session.commit()
    return record.id


@pytest.fixture
def assigned_id(app, dirty_id, hk_user_id):
    """DIRTY record already assigned to housekeeper1. Returns record ID."""
    record = db.session.get(CleaningStatus, dirty_id)
    record.assigned_to_id = hk_user_id
    record.assigned_at = datetime.now(timezone.utc)
    db.session.commit()
    return dirty_id


@pytest.fixture
def cleaning_id(app, assigned_id):
    """Record in CLEANING state (assigned to housekeeper1). Returns record ID."""
    record = db.session.get(CleaningStatus, assigned_id)
    record.status = CleaningStatusEnum.CLEANING.value
    db.session.commit()
    return assigned_id


@pytest.fixture
def clean_id(app, cleaning_id):
    """Record in CLEAN state (housekeeper done, awaits inspection). Returns record ID."""
    record = db.session.get(CleaningStatus, cleaning_id)
    record.status = CleaningStatusEnum.CLEAN.value
    record.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return cleaning_id


# ═══════════════════════════════════════════════════════════════════════════════
# POST /housekeeping/assign
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssign:

    def test_manager_assigns_housekeeper(self, client, manager_token, dirty_id, hk_user_id, app):
        rv = client.post("/housekeeping/assign", json={
            "cleaning_id": dirty_id,
            "housekeeper_id": hk_user_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["assigned_to_id"] == hk_user_id
        assert data["assigned_at"] is not None
        # Audit log must be written
        with app.app_context():
            log = db.session.query(AuditLog).filter_by(action="housekeeping.assign").first()
            assert log is not None

    def test_waiter_cannot_assign(self, client, waiter_token, dirty_id, hk_user_id):
        rv = client.post("/housekeeping/assign", json={
            "cleaning_id": dirty_id,
            "housekeeper_id": hk_user_id,
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_missing_cleaning_id_returns_400(self, client, manager_token, hk_user_id):
        rv = client.post("/housekeeping/assign", json={
            "housekeeper_id": hk_user_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_missing_housekeeper_id_returns_400(self, client, manager_token, dirty_id):
        rv = client.post("/housekeeping/assign", json={
            "cleaning_id": dirty_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_nonexistent_cleaning_id_returns_404(self, client, manager_token, hk_user_id):
        rv = client.post("/housekeeping/assign", json={
            "cleaning_id": "00000000-0000-0000-0000-000000000000",
            "housekeeper_id": hk_user_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# POST /housekeeping/<id>/start
# ═══════════════════════════════════════════════════════════════════════════════

class TestStart:

    def test_assigned_housekeeper_starts(self, client, hk_token, assigned_id):
        rv = client.post(f"/housekeeping/{assigned_id}/start", headers=auth(hk_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == CleaningStatusEnum.CLEANING.value

    def test_non_assigned_staff_cannot_start(self, client, waiter_token, assigned_id):
        """waiter1 is not the assigned housekeeper and is not a manager → 403."""
        rv = client.post(f"/housekeeping/{assigned_id}/start", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_manager_can_start_even_if_not_assigned(self, client, manager_token, assigned_id):
        """Manager is never blocked by the assignment check."""
        rv = client.post(f"/housekeeping/{assigned_id}/start", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == CleaningStatusEnum.CLEANING.value

    def test_illegal_transition_clean_to_cleaning(self, client, manager_token, clean_id):
        """CLEAN → CLEANING is not in the state machine → 400 with error message."""
        rv = client.post(f"/housekeeping/{clean_id}/start", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# POST /housekeeping/<id>/complete
# ═══════════════════════════════════════════════════════════════════════════════

class TestComplete:

    def test_housekeeper_completes(self, client, hk_token, cleaning_id):
        rv = client.post(f"/housekeeping/{cleaning_id}/complete", headers=auth(hk_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == CleaningStatusEnum.CLEAN.value
        assert data["completed_at"] is not None

    def test_non_assigned_staff_cannot_complete(self, client, waiter_token, cleaning_id):
        rv = client.post(f"/housekeeping/{cleaning_id}/complete", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_notes_saved_when_provided(self, client, hk_token, cleaning_id):
        rv = client.post(f"/housekeeping/{cleaning_id}/complete",
                         json={"notes": "Extra towels replaced"},
                         headers=auth(hk_token))
        assert rv.status_code == 200
        assert rv.get_json()["notes"] == "Extra towels replaced"

    def test_illegal_transition_dirty_to_clean(self, client, manager_token, assigned_id):
        """DIRTY → CLEAN skips CLEANING — not a valid transition → 400."""
        rv = client.post(f"/housekeeping/{assigned_id}/complete", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_audit_log_written(self, client, hk_token, cleaning_id, app):
        client.post(f"/housekeeping/{cleaning_id}/complete", headers=auth(hk_token))
        with app.app_context():
            log = db.session.query(AuditLog).filter_by(action="housekeeping.complete").first()
            assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# POST /housekeeping/<id>/inspect
# ═══════════════════════════════════════════════════════════════════════════════

class TestInspect:

    def test_manager_inspects_clean_room(self, client, manager_token, clean_id, app):
        rv = client.post(f"/housekeeping/{clean_id}/inspect", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == CleaningStatusEnum.INSPECTED.value
        assert data["inspected_by_id"] is not None
        assert data["inspected_at"] is not None
        # Audit log
        with app.app_context():
            log = db.session.query(AuditLog).filter_by(action="housekeeping.inspect").first()
            assert log is not None

    def test_waiter_cannot_inspect(self, client, waiter_token, clean_id):
        rv = client.post(f"/housekeeping/{clean_id}/inspect", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_cannot_inspect_dirty_room(self, client, manager_token, dirty_id):
        """DIRTY → INSPECTED is not in the state machine → 400."""
        rv = client.post(f"/housekeeping/{dirty_id}/inspect", headers=auth(manager_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# POST /housekeeping/<id>/flag
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlag:

    def test_housekeeper_flags_with_reason(self, client, hk_token, dirty_id, app):
        rv = client.post(f"/housekeeping/{dirty_id}/flag",
                         json={"reason": "Broken shower head"},
                         headers=auth(hk_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["is_flagged"] is True
        assert data["flag_reason"] == "Broken shower head"
        # Audit log
        with app.app_context():
            log = db.session.query(AuditLog).filter_by(action="housekeeping.flag").first()
            assert log is not None

    def test_missing_reason_returns_400(self, client, hk_token, dirty_id):
        rv = client.post(f"/housekeeping/{dirty_id}/flag",
                         json={},
                         headers=auth(hk_token))
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_waiter_cannot_flag(self, client, waiter_token, dirty_id):
        """waiter1 is in Front-of-House, not housekeeping/villa dept → 403."""
        rv = client.post(f"/housekeeping/{dirty_id}/flag",
                         json={"reason": "Broken AC"},
                         headers=auth(waiter_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# GET /housekeeping/status
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatus:

    def test_manager_sees_all_rooms(self, client, manager_token, dirty_id):
        """Manager gets a list with at least the seeded villa."""
        rv = client.get("/housekeeping/status", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_hk_staff_can_view_status(self, client, hk_token, dirty_id):
        """Housekeeping dept staff (level 1) can also view the status list."""
        rv = client.get("/housekeeping/status", headers=auth(hk_token))
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_waiter_cannot_view_status(self, client, waiter_token):
        """Front-of-House staff are not housekeeping dept → 403."""
        rv = client.get("/housekeeping/status", headers=auth(waiter_token))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# Full happy path: DIRTY → assign → start → complete → inspect
# ═══════════════════════════════════════════════════════════════════════════════

class TestHappyPath:

    def test_full_cleaning_lifecycle(self, client, manager_token, hk_token,
                                     hk_user_id, dirty_id, app):
        """Walk every state-machine transition via the API and verify each step."""

        # 1. Assign housekeeper1 to the DIRTY record
        rv = client.post("/housekeeping/assign", json={
            "cleaning_id": dirty_id,
            "housekeeper_id": hk_user_id,
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["assigned_to_id"] == hk_user_id

        # 2. Housekeeper starts cleaning: DIRTY → CLEANING
        rv = client.post(f"/housekeeping/{dirty_id}/start", headers=auth(hk_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "CLEANING"

        # 3. Housekeeper marks done with notes: CLEANING → CLEAN
        rv = client.post(f"/housekeeping/{dirty_id}/complete",
                         json={"notes": "Deep-cleaned, towels replaced"},
                         headers=auth(hk_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "CLEAN"
        assert data["completed_at"] is not None
        assert data["notes"] == "Deep-cleaned, towels replaced"

        # 4. Manager inspects: CLEAN → INSPECTED
        rv = client.post(f"/housekeeping/{dirty_id}/inspect", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "INSPECTED"
        assert data["inspected_by"] == "manager1"

        # Verify all four audit log entries were written
        with app.app_context():
            for action in [
                "housekeeping.assign",
                "housekeeping.start",
                "housekeeping.complete",
                "housekeeping.inspect",
            ]:
                log = db.session.query(AuditLog).filter_by(action=action).first()
                assert log is not None, f"Missing audit log entry for action={action!r}"
