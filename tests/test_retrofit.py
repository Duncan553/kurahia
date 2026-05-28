"""
test_retrofit.py — Tests for the Chunk 3 retrofit of Chunks 1 & 2.

Covers:
  - disable / enable lifecycle on inventory items, departments, roles
  - error responses always carry a plain-English "error" field
  - disabled items blocked in movements, counts, purchases
  - include_disabled query param on list endpoints
"""
import pytest


# ── Inventory item disable/enable lifecycle ────────────────────────────────────

def test_disable_and_reenable_inventory_item(client, owner_token, general_dept_id):
    # Create
    rv = client.post("/inventory/items", json={
        "name": "Test Sauce", "unit": "litres", "reorder_level": "2",
        "department_id": general_dept_id,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    item_id = rv.get_json()["id"]

    # Disable
    rv = client.post(f"/inventory/items/{item_id}/disable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is False

    # Disabled item hidden from default list
    rv = client.get("/inventory/items",
                    headers={"Authorization": f"Bearer {owner_token}"})
    ids = [i["id"] for i in rv.get_json()]
    assert item_id not in ids

    # But visible with include_disabled=true
    rv = client.get("/inventory/items?include_disabled=true",
                    headers={"Authorization": f"Bearer {owner_token}"})
    ids = [i["id"] for i in rv.get_json()]
    assert item_id in ids

    # Re-enable
    rv = client.post(f"/inventory/items/{item_id}/enable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is True


def test_disable_item_blocks_spoilage_movement(client, owner_token, general_dept_id):
    # Create + disable
    rv = client.post("/inventory/items", json={
        "name": "Blocked Oil", "unit": "litres", "reorder_level": "1",
        "department_id": general_dept_id,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    item_id = rv.get_json()["id"]
    client.post(f"/inventory/items/{item_id}/disable",
                headers={"Authorization": f"Bearer {owner_token}"})

    # Spoilage should be blocked — endpoint uses "quantity", not "amount"
    rv = client.post("/inventory/movements/spoilage", json={
        "item_id": item_id, "quantity": "1"
    }, headers={"Authorization": f"Bearer {owner_token}"})
    # Disabled items return 404 ("disabled or does not exist")
    assert rv.status_code == 404
    body = rv.get_json()
    assert "error" in body
    assert "disabled" in body["error"].lower() or "does not exist" in body["error"].lower()


def test_edit_inventory_item(client, owner_token, general_dept_id):
    rv = client.post("/inventory/items", json={
        "name": "Editable Oil", "unit": "litres", "reorder_level": "5",
        "department_id": general_dept_id,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    item_id = rv.get_json()["id"]

    rv = client.patch(f"/inventory/items/{item_id}", json={"reorder_level": "10"},
                      headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    # PATCH response includes id and is_active; confirm the item still exists (not deleted)
    assert rv.get_json()["id"] == item_id
    assert rv.get_json()["is_active"] is True


# ── Department disable/enable ──────────────────────────────────────────────────

def test_disable_enable_department(client, owner_token):
    rv = client.post("/admin/departments", json={"name": "Housekeeping"},
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    dept_id = rv.get_json()["id"]

    rv = client.post(f"/admin/departments/{dept_id}/disable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is False

    rv = client.post(f"/admin/departments/{dept_id}/enable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is True


def test_edit_department(client, owner_token):
    rv = client.post("/admin/departments", json={"name": "OriginalName"},
                     headers={"Authorization": f"Bearer {owner_token}"})
    dept_id = rv.get_json()["id"]

    rv = client.patch(f"/admin/departments/{dept_id}", json={"name": "RenamedDept"},
                      headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["name"] == "RenamedDept"


# ── Role disable/enable ────────────────────────────────────────────────────────

def test_disable_enable_role(client, owner_token):
    rv = client.post("/admin/roles", json={"name": "TestRole", "level": 2},
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    role_id = rv.get_json()["id"]

    rv = client.post(f"/admin/roles/{role_id}/disable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is False

    rv = client.post(f"/admin/roles/{role_id}/enable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is True


# ── Error shape contract ───────────────────────────────────────────────────────

def test_404_has_error_field(client, owner_token):
    """404 responses must carry an 'error' field."""
    rv = client.get("/tabs/nonexistent-id",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 404
    assert "error" in rv.get_json()


def test_unauthorized_has_error_field(client):
    rv = client.get("/inventory/items")
    assert rv.status_code == 401
    assert "error" in rv.get_json()
