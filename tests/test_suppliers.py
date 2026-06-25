"""
tests/test_suppliers.py — Supplier CRUD tests.

Coverage:
  - GET    /suppliers: manager+ lists active (and optionally disabled) suppliers
  - POST   /suppliers: manager+ creates supplier, duplicate name rejected
  - PATCH  /suppliers/:id: manager+ edits supplier fields, name uniqueness enforced
  - POST   /suppliers/:id/disable: manager+ soft-deletes supplier
  - Auth/role enforcement for each endpoint
  - Validation: missing name, empty name on edit, duplicate name
"""
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def supplier_id(client, manager_token):
    """Create a supplier and return its id."""
    rv = client.post("/suppliers", json={
        "name": "Nairobi Fresh Produce",
        "contact_person": "James Mwangi",
        "phone": "+254722000001",
        "email": "james@nfp.co.ke",
        "items_supplied": "vegetables, fruits",
        "payment_terms": "Net 30",
        "notes": "Delivers on Tuesdays",
    }, headers=auth(manager_token))
    assert rv.status_code == 201
    return rv.get_json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
# 1. POST /suppliers — create supplier (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateSupplier:
    def test_manager_creates_supplier(self, client, manager_token):
        """Manager creates supplier with all fields → 201."""
        rv = client.post("/suppliers", json={
            "name": "Lake Fish Ltd",
            "contact_person": "Otieno",
            "phone": "+254733000001",
            "items_supplied": "tilapia, nile perch",
            "payment_terms": "COD",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["name"] == "Lake Fish Ltd"
        assert data["contact_person"] == "Otieno"
        assert data["is_active"] is True

    def test_owner_creates_supplier(self, client, owner_token):
        """Owner (level 10) can also create → 201."""
        rv = client.post("/suppliers", json={
            "name": "Mombasa Spirits",
        }, headers=auth(owner_token))
        assert rv.status_code == 201

    def test_minimal_fields(self, client, manager_token):
        """Only name is required → 201."""
        rv = client.post("/suppliers", json={
            "name": "Quick Dairy",
        }, headers=auth(manager_token))
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["name"] == "Quick Dairy"
        assert data["contact_person"] is None

    def test_missing_name_rejected(self, client, manager_token):
        """No name → 400."""
        rv = client.post("/suppliers", json={
            "contact_person": "Ghost",
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "name" in rv.get_json()["error"]

    def test_empty_name_rejected(self, client, manager_token):
        """Whitespace-only name → 400."""
        rv = client.post("/suppliers", json={
            "name": "   ",
        }, headers=auth(manager_token))
        assert rv.status_code == 400

    def test_duplicate_name_rejected(self, client, manager_token, supplier_id):
        """Same name (case-insensitive) → 409."""
        rv = client.post("/suppliers", json={
            "name": "nairobi fresh produce",  # lowercase version of existing
        }, headers=auth(manager_token))
        assert rv.status_code == 409
        assert "already exists" in rv.get_json()["error"]

    def test_staff_cannot_create(self, client, waiter_token):
        """Staff (level 1) blocked → 403."""
        rv = client.post("/suppliers", json={
            "name": "Blocked Supplier",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_no_auth_rejected(self, client):
        """No token → 401."""
        rv = client.post("/suppliers", json={"name": "Anon"})
        assert rv.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 2. GET /suppliers — list suppliers (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestListSuppliers:
    def test_manager_lists_active(self, client, manager_token, supplier_id):
        """Manager sees active suppliers → 200."""
        rv = client.get("/suppliers", headers=auth(manager_token))
        assert rv.status_code == 200
        suppliers = rv.get_json()
        assert isinstance(suppliers, list)
        assert len(suppliers) >= 1
        names = [s["name"] for s in suppliers]
        assert "Nairobi Fresh Produce" in names

    def test_disabled_supplier_hidden_by_default(self, client, manager_token, supplier_id):
        """Disabled supplier is excluded from default listing."""
        # Disable it first
        client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        rv = client.get("/suppliers", headers=auth(manager_token))
        ids = [s["id"] for s in rv.get_json()]
        assert supplier_id not in ids

    def test_include_disabled(self, client, manager_token, supplier_id):
        """?include_disabled=true shows disabled suppliers too."""
        client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        rv = client.get("/suppliers?include_disabled=true", headers=auth(manager_token))
        ids = [s["id"] for s in rv.get_json()]
        assert supplier_id in ids

    def test_staff_cannot_list(self, client, waiter_token):
        """Staff (level 1) blocked → 403."""
        rv = client.get("/suppliers", headers=auth(waiter_token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 3. PATCH /suppliers/:id — edit supplier (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestEditSupplier:
    def test_manager_edits_fields(self, client, manager_token, supplier_id):
        """Manager updates contact info → 200."""
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "contact_person": "Peter Kamau",
            "phone": "+254755000001",
            "notes": "Now delivers Mon and Thu",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["contact_person"] == "Peter Kamau"
        assert data["phone"] == "+254755000001"
        assert data["notes"] == "Now delivers Mon and Thu"

    def test_rename_supplier(self, client, manager_token, supplier_id):
        """Manager renames supplier → 200."""
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "name": "Nairobi Fresh Produce Ltd",
        }, headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["name"] == "Nairobi Fresh Produce Ltd"

    def test_rename_to_empty_rejected(self, client, manager_token, supplier_id):
        """Empty name on rename → 400."""
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "name": "",
        }, headers=auth(manager_token))
        assert rv.status_code == 400
        assert "name" in rv.get_json()["error"]

    def test_rename_to_duplicate_rejected(self, client, manager_token, supplier_id):
        """Rename to a name that already exists → 409."""
        # Create a second supplier
        client.post("/suppliers", json={"name": "Rival Supplier"}, headers=auth(manager_token))
        # Try renaming the first to match the second
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "name": "rival supplier",
        }, headers=auth(manager_token))
        assert rv.status_code == 409

    def test_edit_nonexistent_404(self, client, manager_token):
        """PATCH on non-existent id → 404."""
        rv = client.patch("/suppliers/no-such-id", json={
            "notes": "ghost",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_edit_disabled_supplier_404(self, client, manager_token, supplier_id):
        """Editing a disabled supplier → 404 (treated as not found)."""
        client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "notes": "Still here?",
        }, headers=auth(manager_token))
        assert rv.status_code == 404

    def test_staff_cannot_edit(self, client, waiter_token, supplier_id):
        """Staff (level 1) blocked → 403."""
        rv = client.patch(f"/suppliers/{supplier_id}", json={
            "notes": "nope",
        }, headers=auth(waiter_token))
        assert rv.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 4. POST /suppliers/:id/disable — soft-delete (manager+)
# ══════════════════════════════════════════════════════════════════════════════

class TestDisableSupplier:
    def test_manager_disables_supplier(self, client, manager_token, supplier_id):
        """Disable → 200 with is_active=False."""
        rv = client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["is_active"] is False

    def test_disable_nonexistent_404(self, client, manager_token):
        """Disable non-existent id → 404."""
        rv = client.post("/suppliers/no-such-id/disable", headers=auth(manager_token))
        assert rv.status_code == 404

    def test_disable_already_disabled(self, client, manager_token, supplier_id):
        """Disabling an already-disabled supplier still succeeds (idempotent)."""
        client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        rv = client.post(f"/suppliers/{supplier_id}/disable", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is False

    def test_staff_cannot_disable(self, client, waiter_token, supplier_id):
        """Staff (level 1) blocked → 403."""
        rv = client.post(f"/suppliers/{supplier_id}/disable", headers=auth(waiter_token))
        assert rv.status_code == 403
