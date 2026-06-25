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
