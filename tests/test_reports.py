"""
test_reports.py — PDF report endpoint tests.

Tests cover: status codes, role gates, and error responses for bad input.
We do NOT inspect PDF content — just that the right status + Content-Type comes back.

Endpoints:
  GET /reports/receipt/<tab_id>                        — front_desk+ (level 3+)
  GET /reports/daily-summary?date=YYYY-MM-DD           — owner only (level 10)
  GET /reports/occupancy?from=YYYY-MM-DD&to=YYYY-MM-DD — owner only (level 10)
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from app.extensions import db as _db


# ── Auth helper ───────────────────────────────────────────────────────────────

def auth(token):
    """Wrap a JWT token into an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def closed_tab(app):
    """
    Seed a CLOSED Tab into the test DB and return its id.
    Returns the id (string) rather than the ORM object because the
    SQLAlchemy session closes when we leave the app_context block.
    """
    with app.app_context():
        from app.models.tab import Tab, TabStatus
        from app.models.user import User

        # Use the seeded waiter as the opener (any valid user works)
        user = _db.session.query(User).filter_by(username="waiter1").first()
        now = datetime.now(timezone.utc)
        tab = Tab(
            opened_by_id=user.id,
            status=TabStatus.CLOSED.value,
            tab_type="WALK_IN",
            reference="Table 1",
            opened_at_utc=now - timedelta(hours=1),
            closed_at_utc=now,
        )
        _db.session.add(tab)
        _db.session.commit()
        return tab.id  # plain string — safe to use after session closes


@pytest.fixture
def open_tab(app):
    """Seed an OPEN Tab and return its id."""
    with app.app_context():
        from app.models.tab import Tab, TabStatus
        from app.models.user import User

        user = _db.session.query(User).filter_by(username="waiter1").first()
        tab = Tab(
            opened_by_id=user.id,
            status=TabStatus.OPEN.value,
            tab_type="WALK_IN",
            reference="Table 2",
        )
        _db.session.add(tab)
        _db.session.commit()
        return tab.id


@pytest.fixture
def villa_resource(app):
    """
    Seed an active VILLA BookableResource and return its id.
    The occupancy happy-path test needs at least one villa to exist.
    """
    with app.app_context():
        from app.models.bookable_resource import BookableResource, ResourceType

        villa = BookableResource(
            name="Beachfront Villa 1",
            resource_type=ResourceType.VILLA.value,
            base_price="25000",
            is_active=True,
        )
        _db.session.add(villa)
        _db.session.commit()
        return villa.id


# ── /reports/receipt/<tab_id> ─────────────────────────────────────────────────

def test_receipt_happy_path(client, manager_token, closed_tab):
    """Manager (level 5 ≥ front_desk 3) gets PDF for a closed tab."""
    r = client.get(f"/reports/receipt/{closed_tab}", headers=auth(manager_token))
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert len(r.data) > 100  # non-empty PDF bytes


def test_receipt_waiter_forbidden(client, waiter_token, closed_tab):
    """Waiter (level 1 < 3) gets 403."""
    r = client.get(f"/reports/receipt/{closed_tab}", headers=auth(waiter_token))
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_receipt_nonexistent_tab(client, manager_token):
    """Non-existent tab_id returns 404."""
    r = client.get("/reports/receipt/no-such-tab-id", headers=auth(manager_token))
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_receipt_open_tab_returns_400(client, manager_token, open_tab):
    """Receipt is only available for CLOSED tabs — OPEN tab returns 400."""
    r = client.get(f"/reports/receipt/{open_tab}", headers=auth(manager_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


# ── /reports/daily-summary ────────────────────────────────────────────────────

def test_daily_summary_happy_path(client, owner_token):
    """Owner with today's date gets a PDF."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = client.get(f"/reports/daily-summary?date={today}", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert len(r.data) > 100


def test_daily_summary_manager_forbidden(client, manager_token):
    """Manager (level 5 < 10) gets 403."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = client.get(f"/reports/daily-summary?date={today}", headers=auth(manager_token))
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_daily_summary_waiter_forbidden(client, waiter_token):
    """Waiter (level 1 < 10) gets 403."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = client.get(f"/reports/daily-summary?date={today}", headers=auth(waiter_token))
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_daily_summary_no_date_param(client, owner_token):
    """Omitting the date param returns 400 — route requires an explicit date."""
    r = client.get("/reports/daily-summary", headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_daily_summary_invalid_date_format(client, owner_token):
    """A badly-formatted date string returns 400."""
    r = client.get("/reports/daily-summary?date=25-06-2026", headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


# ── /reports/occupancy ────────────────────────────────────────────────────────

def test_occupancy_happy_path(client, owner_token, villa_resource):
    """Owner with a valid range and at least one active villa gets a PDF."""
    from_date = "2026-06-01"
    to_date   = "2026-06-07"
    r = client.get(
        f"/reports/occupancy?from={from_date}&to={to_date}",
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert len(r.data) > 100


def test_occupancy_manager_forbidden(client, manager_token, villa_resource):
    """Manager (level 5 < 10) gets 403."""
    r = client.get(
        "/reports/occupancy?from=2026-06-01&to=2026-06-07",
        headers=auth(manager_token),
    )
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_occupancy_waiter_forbidden(client, waiter_token, villa_resource):
    """Waiter (level 1 < 10) gets 403."""
    r = client.get(
        "/reports/occupancy?from=2026-06-01&to=2026-06-07",
        headers=auth(waiter_token),
    )
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_occupancy_no_params(client, owner_token):
    """Omitting both date params returns 400."""
    r = client.get("/reports/occupancy", headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_occupancy_to_before_from(client, owner_token, villa_resource):
    """'to' date before 'from' date returns 400."""
    r = client.get(
        "/reports/occupancy?from=2026-06-10&to=2026-06-01",
        headers=auth(owner_token),
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_occupancy_range_over_90_days(client, owner_token, villa_resource):
    """Range exceeding 90 days is rejected with 400."""
    r = client.get(
        "/reports/occupancy?from=2026-01-01&to=2026-06-01",
        headers=auth(owner_token),
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_occupancy_no_villas_returns_404(client, owner_token):
    """If no active villa resources exist the route returns 404."""
    # Do NOT use the villa_resource fixture — DB has no villas by default
    r = client.get(
        "/reports/occupancy?from=2026-06-01&to=2026-06-07",
        headers=auth(owner_token),
    )
    assert r.status_code == 404
    assert "error" in r.get_json()
