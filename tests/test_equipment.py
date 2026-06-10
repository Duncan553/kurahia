"""
test_equipment.py — Structured 5-item safety checklist tests (Q-3.2).

Tests:
  1. Rejected if a required item is missing from check_items
  2. Rejected if an item is present but checked=False
  3. Succeeds when all 5 items are checked=True, row persists
  4. Template endpoint returns correct items for jetski
  5. Template endpoint returns 404 for unknown equipment type
"""
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def jetski(client, manager_token):
    """Create a Jetski equipment record and return its id."""
    rv = client.post("/equipment", json={
        "name": "Test Jetski",
        "equipment_type": "Jetski",
        "service_interval_days": 30,
    }, headers=auth(manager_token))
    assert rv.status_code == 201
    return rv.get_json()["id"]


FULL_JETSKI_CHECKLIST = {
    "life_jackets_on_board":       {"checked": True, "note": ""},
    "engine_oil_level_checked":    {"checked": True, "note": ""},
    "fuel_level_ok":               {"checked": True, "note": ""},
    "kill_switch_lanyard_present": {"checked": True, "note": ""},
    "guest_waiver_confirmed":      {"checked": True, "note": ""},
}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_safety_check_rejected_with_missing_item(client, jetski, manager_token):
    """4 of 5 items submitted (fuel_level_ok missing) → 400 with unchecked_items list."""
    items = {k: v for k, v in FULL_JETSKI_CHECKLIST.items() if k != "fuel_level_ok"}
    rv = client.post(f"/equipment/{jetski}/safety-check",
                     json={"check_items": items},
                     headers=auth(manager_token))
    assert rv.status_code == 400
    body = rv.get_json()
    # Item names now surface in unchecked_items list, not in the error string
    assert "unchecked_items" in body
    assert "fuel_level_ok" in body["unchecked_items"]
    assert "Safety check failed" in body["error"]


def test_safety_check_rejected_with_unchecked_item(client, jetski, manager_token):
    """All 5 items present but life_jackets_on_board has checked=False → 400."""
    items = dict(FULL_JETSKI_CHECKLIST)
    items["life_jackets_on_board"] = {"checked": False, "note": "Missing jackets"}
    rv = client.post(f"/equipment/{jetski}/safety-check",
                     json={"check_items": items},
                     headers=auth(manager_token))
    assert rv.status_code == 400
    body = rv.get_json()
    assert "unchecked_items" in body
    assert "life_jackets_on_board" in body["unchecked_items"]


def test_safety_check_succeeds_with_all_items_checked(client, jetski, manager_token, app):
    """All 5 items checked=True → 201, SafetyCheck row persists with check_items."""
    rv = client.post(f"/equipment/{jetski}/safety-check",
                     json={"check_items": FULL_JETSKI_CHECKLIST},
                     headers=auth(manager_token))
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["passed"] is True

    from app.extensions import db
    from app.models.equipment import SafetyCheck
    with app.app_context():
        check = db.session.query(SafetyCheck).filter_by(equipment_id=jetski).first()
        assert check is not None
        assert check.passed is True
        assert check.check_items is not None
        assert "life_jackets_on_board" in check.check_items


def test_safety_check_template_endpoint_returns_correct_items(client, manager_token):
    """GET /equipment/checklist-templates/jetski returns 5 items."""
    rv = client.get("/equipment/checklist-templates/jetski",
                    headers=auth(manager_token))
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["count"] == 5
    assert "life_jackets_on_board" in data["items"]
    assert "guest_waiver_confirmed" in data["items"]


def test_safety_check_template_endpoint_404_for_unknown_type(client, manager_token):
    """GET /equipment/checklist-templates/hovercraft → 404."""
    rv = client.get("/equipment/checklist-templates/hovercraft",
                    headers=auth(manager_token))
    assert rv.status_code == 404
    assert "hovercraft" in rv.get_json()["error"]
