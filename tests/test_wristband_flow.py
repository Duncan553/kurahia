"""
test_wristband_flow.py — End-to-end wristband money flow.
Issue band → charge via tab → balance decreases → forfeit unused credit.
"""
import uuid
from decimal import Decimal
import pytest
from app.extensions import db
from app.models.user import User
from app.models.wristband import Wristband, WristbandStatus
from app.models.tab import Tab
from app.models.payment import Payment
from app.services.stock import get_current_stock
from app.services.tab import get_tab_balance


class TestWristbandFlow:
    def _get_gate_token(self, client):
        """Login as a gate-level user (owner has gate+ access)."""
        rv = client.post("/auth/login", json={"username": "owner1", "password": "OwnerPass1!"})
        return rv.get_json()["access_token"]

    def _issue_band(self, client, token):
        rv = client.post("/gate/issue-band", json={
            "method": "CASH", "idempotency_key": str(uuid.uuid4()),
        }, headers={"Authorization": f"Bearer {token}"})
        assert rv.status_code in (200, 201)
        return rv.get_json()

    def test_issue_creates_tab_with_credit(self, app, client):
        """Issuing a band creates a tab with -3000 balance (credit)."""
        token = self._get_gate_token(client)
        data = self._issue_band(client, token)

        assert data["status"] == "ACTIVE"
        assert data["band_number"] >= 1

        tab_balance = get_tab_balance(data["tab_id"])
        assert tab_balance == Decimal("-3000")

    def test_charge_reduces_credit(self, app, client):
        """Charging the tab reduces the credit balance."""
        token = self._get_gate_token(client)
        data = self._issue_band(client, token)
        tab_id = data["tab_id"]

        # Place an order on the band's tab
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": self._food_id(app), "quantity": 1}],
        }, headers={"Authorization": f"Bearer {token}"})
        assert rv.status_code == 201
        order_id = rv.get_json()["id"]

        # Send it (creates charges)
        rv = client.post(f"/orders/{order_id}/send",
                         headers={"Authorization": f"Bearer {token}"})
        assert rv.status_code == 200

        # Balance should be less negative (some credit used)
        new_balance = get_tab_balance(tab_id)
        assert new_balance > Decimal("-3000")

    def test_forfeit_sweeps_unused_credit(self, app, client):
        """EOD forfeit marks active bands as FORFEITED."""
        token = self._get_gate_token(client)
        data = self._issue_band(client, token)
        today = data["issue_date"]

        # Forfeit the day
        rv = client.post("/gate/forfeit-day", json={"date": today},
                         headers={"Authorization": f"Bearer {token}"})
        assert rv.status_code == 200
        result = rv.get_json()
        assert result["forfeited"] >= 1

        # Band should now be FORFEITED
        band = db.session.get(Wristband, data["id"])
        assert band.status == WristbandStatus.FORFEITED.value

    def test_idempotent_issue(self, app, client):
        """Same idempotency key returns same band, no duplicate."""
        token = self._get_gate_token(client)
        idem = str(uuid.uuid4())
        r1 = client.post("/gate/issue-band", json={"method": "CASH", "idempotency_key": idem},
                         headers={"Authorization": f"Bearer {token}"})
        r2 = client.post("/gate/issue-band", json={"method": "CASH", "idempotency_key": idem},
                         headers={"Authorization": f"Bearer {token}"})
        assert r1.get_json()["band_number"] == r2.get_json()["band_number"]
        assert r2.get_json().get("duplicate") is True

    def _food_id(self, app):
        from app.models.menu_item import MenuItem
        return db.session.query(MenuItem).filter_by(name="Grilled Tilapia").first().id
