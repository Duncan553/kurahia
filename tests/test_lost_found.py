"""
tests/test_lost_found.py — Lost & Found module tests.

Coverage:
  - POST /lost-found: any staff logs a found item
  - GET  /lost-found: manager+ lists items (with optional status filter)
  - PATCH /lost-found/:id: manager+ updates item (status, notes, claim)
  - Auth/role enforcement for each endpoint
  - Validation: missing required fields, invalid status, claim without name
"""
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. POST /lost-found — log a found item
# ══════════════════════════════════════════════════════════════════════════════

class TestLogFoundItem:
    def test_staff_can_log_item(self, client, waiter_token):
        """Any staff (level 1+) can log a found item → 201."""
        rv = client.post("/lost-found", json={
            "description": "Black wallet with KCB card",
            "found_location": "Pool deck, chair 3",
            "notes": "Handed to reception",
        }, headers=auth(waiter_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["description"] == "Black wallet with KCB card"
        assert data["found_location"] == "Pool deck, chair 3"
        assert data["status"] == "UNCLAIMED"
        assert data["is_active"] is True
        assert data["notes"] == "Handed to reception"

    def test_manager_can_log_item(self, client, manager_token):
        """Manager (level 5) can also log → 201."""
        rv = client.post("/lost-found", json={
            "description": "Samsung phone",
            "found_location": "Restaurant table 7",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        assert rv.get_json()["description"] == "Samsung phone"

    def test_missing_description_rejected(self, client, waiter_token):
        """No description → 400."""
        rv = client.post("/lost-found", json={
            "found_location": "Lobby",
        }, headers=auth(waiter_token))
        assert rv.status_code == 400
        assert "description" in rv.get_json()["error"]

    def test_missing_found_location_rejected(self, client, waiter_token):
        """No found_location → 400."""
        rv = client.post("/lost-found", json={
            "description": "Sunglasses",
        }, headers=auth(waiter_token))
        assert rv.status_code == 400
        assert "found_location" in rv.get_json()["error"]

    def test_empty_strings_rejected(self, client, waiter_token):
        """Whitespace-only fields → 400 (stripped to empty)."""
        rv = client.post("/lost-found", json={
            "description": "   ",
            "found_location": "  ",
        }, headers=auth(waiter_token))
        assert rv.status_code == 400

    def test_no_auth_rejected(self, client):
        """No token → 401."""
        rv = client.post("/lost-found", json={
            "description": "Hat",
            "found_location": "Beach",
        })
        assert rv.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 2. GET /lost-found — list items (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestListLostFound:
    def test_manager_lists_items(self, client, manager_token, waiter_token):
        """Manager sees all active items → 200 with list."""
        # Staff logs an item first
        client.post("/lost-found", json={
            "description": "Umbrella",
            "found_location": "Gate",
        }, headers=auth(waiter_token))

        rv = client.get("/lost-found", headers=auth(manager_token))
        assert rv.status_code == 200
        items = rv.get_json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert items[0]["description"] == "Umbrella"

    def test_staff_cannot_list(self, client, waiter_token):
        """Staff (level 1) blocked from listing → 403."""
        rv = client.get("/lost-found", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_filter_by_status(self, client, manager_token, waiter_token):
        """?status=UNCLAIMED filters results."""
        # Log an item
        client.post("/lost-found", json={
            "description": "Flip flops",
            "found_location": "Pool",
        }, headers=auth(waiter_token))

        rv = client.get("/lost-found?status=UNCLAIMED", headers=auth(manager_token))
        assert rv.status_code == 200
        items = rv.get_json()
        assert all(i["status"] == "UNCLAIMED" for i in items)

    def test_invalid_status_filter_ignored(self, client, manager_token, waiter_token):
        """?status=BOGUS is ignored (returns all active items)."""
        client.post("/lost-found", json={
            "description": "Towel",
            "found_location": "Sauna",
        }, headers=auth(waiter_token))

        rv = client.get("/lost-found?status=BOGUS", headers=auth(manager_token))
        assert rv.status_code == 200
        # Still returns items — filter just doesn't apply
        assert isinstance(rv.get_json(), list)


# ══════════════════════════════════════════════════════════════════════════════
# 3. PATCH /lost-found/:id — update item (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateLostFound:
    @pytest.fixture
    def item_id(self, client, waiter_token):
        """Create an item and return its id."""
        rv = client.post("/lost-found", json={
            "description": "Car keys",
            "found_location": "Parking lot",
        }, headers=auth(waiter_token))
        return rv.get_json()["id"]

    def test_manager_updates_notes(self, client, manager_token, item_id):
        """Manager can update notes → 200."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "notes": "Guest called about this",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["notes"] == "Guest called about this"

    def test_manager_marks_claimed(self, client, manager_token, item_id):
        """Mark as CLAIMED with claimed_by_name → 200."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "CLAIMED",
            "claimed_by_name": "John Doe",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "CLAIMED"
        assert data["claimed_by_name"] == "John Doe"
        assert data["claimed_at"] is not None

    def test_claim_without_name_rejected(self, client, manager_token, item_id):
        """CLAIMED status without claimed_by_name → 400."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "CLAIMED",
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "claimed_by_name" in rv.get_json()["error"]

    def test_claim_with_empty_name_rejected(self, client, manager_token, item_id):
        """CLAIMED with whitespace-only name → 400."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "CLAIMED",
            "claimed_by_name": "   ",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_manager_marks_disposed(self, client, manager_token, item_id):
        """Mark as DISPOSED (no claimed_by_name needed) → 200."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "DISPOSED",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "DISPOSED"

    def test_invalid_status_rejected(self, client, manager_token, item_id):
        """Invalid status value → 400."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "RETURNED",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_staff_cannot_update(self, client, waiter_token, item_id):
        """Staff (level 1) blocked from updating → 403."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "notes": "Trying to edit",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_update_nonexistent_item_404(self, client, manager_token):
        """PATCH on a non-existent id → 404."""
        rv = client.patch("/lost-found/no-such-id", json={
            "notes": "Ghost item",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_update_description_and_location(self, client, manager_token, item_id):
        """Manager can update description and found_location."""
        rv = client.patch(f"/lost-found/{item_id}", json={
            "description": "Toyota car keys (3 keys on ring)",
            "found_location": "VIP parking lot",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["description"] == "Toyota car keys (3 keys on ring)"
        assert data["found_location"] == "VIP parking lot"


# ══════════════════════════════════════════════════════════════════════════════
# 5. The desk/manager split — who may LOOK vs who may RELEASE
# ══════════════════════════════════════════════════════════════════════════════
#
# The list was manager-only while logging was open to everyone, so the one
# person the feature exists for could not use it: a guest walks up to the desk
# and asks whether anyone handed in a blue jacket. Front desk could log the
# jacket and never see it again; the manager is not standing at the desk when
# that question is asked.
#
# Reading dropped to level 3. Releasing the property did NOT — "yes, that
# iPhone is mine" is where the risk lives, and that still wants a manager.
# These two tests are the whole rule: the door opened, and only that door.

@pytest.fixture
def front_desk_token(client, app):
    """A real level-3 front_desk user. No conftest fixture exists for this
    role — the seed only builds owner/manager/staff/kitchen/waiter/chef."""
    from app.extensions import db
    from app.models.user import User
    from app.models.role import Role
    from app.models.department import Department

    with app.app_context():
        role = db.session.query(Role).filter_by(name="front_desk").first()
        if not role:
            role = Role(name="front_desk", level=3)
            db.session.add(role)
            db.session.flush()
        # Any department will do; the gate reads role.level, not the department.
        dept = db.session.query(Department).first()
        desk = User(username="desk1", role_id=role.id, department_id=dept.id)
        desk.set_password("DeskPass1!")
        desk.set_pin("7001")
        db.session.add(desk)
        db.session.commit()

    rv = client.post("/auth/login", json={
        "username": "desk1", "password": "DeskPass1!",
    })
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["access_token"]


class TestFrontDeskMayLookButNotRelease:

    def test_front_desk_can_list_items(self, client, front_desk_token, waiter_token):
        """The guest asks at the desk, so the desk must be able to answer."""
        client.post("/lost-found", json={
            "description": "Blue jacket",
            "found_location": "Poolside lounger",
        }, headers=auth(waiter_token))

        rv = client.get("/lost-found", headers=auth(front_desk_token))
        assert rv.status_code == 200, rv.get_json()
        assert any(i["description"] == "Blue jacket" for i in rv.get_json())

    def test_front_desk_cannot_release_an_item(self, client, front_desk_token,
                                               manager_token):
        """Handing the property over is still a manager's signature."""
        created = client.post("/lost-found", json={
            "description": "iPhone 13",
            "found_location": "Villa 4 bathroom",
        }, headers=auth(manager_token))
        item_id = created.get_json()["id"]

        rv = client.patch(f"/lost-found/{item_id}", json={
            "status": "CLAIMED", "claimed_by_name": "Anyone At All",
        }, headers=auth(front_desk_token))
        assert rv.status_code == 403
        assert "manager" in rv.get_json()["error"].lower()
