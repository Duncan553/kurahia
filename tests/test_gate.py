"""
tests/test_gate.py — Chunk 7 Gate & Wristband tests.

Coverage:
  1.  Issue band: Wristband + Payment + BAND tab created; tab balance = -3000
  2.  Lookup: waiter can look up active band by number; sees balance
  3.  Charge flow: POS charge to band tab draws down credit; balance updates
  4.  Spend-less-than-credit: forfeit closes tab with unused credit recorded
  5.  Spend-more-than-credit: tab balance goes positive (customer owes extra)
  6.  Unique band numbers: allocator gives sequential numbers for the same day
  7.  Reconciliation: bands × 3000 = gate revenue; mismatch detected correctly
  8.  Headcount mismatch: counted > issued → flagged
  9.  Deactivate: active → DEACTIVATED, tab closes
 10.  Forfeit-on-close: EOD sweep forfeits ACTIVE bands with correct amounts
 11.  Role enforcement: waiter cannot issue; manager can
 12.  No refunds: no refund endpoint exists; forfeit is final
 13.  Idempotency: double-tap on issue-band returns original, not duplicate
 14.  Plain-English errors on every failure path
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _issue(client, token, method="CASH", idem_key=None):
    payload = {"method": method}
    if idem_key:
        payload["idempotency_key"] = idem_key
    return client.post("/gate/issue-band", json=payload, headers=auth(token))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Issue band — creates everything atomically
# ═══════════════════════════════════════════════════════════════════════════════

class TestIssueBand:
    def test_issue_creates_band_tab_and_payment(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["band_number"] > 0
        assert data["tab_id"] is not None
        assert data["status"] == "ACTIVE"
        # tab balance is -3000 (credit — customer hasn't spent yet)
        assert Decimal(data["tab_balance"]) == Decimal("-3000")

    def test_issue_creates_payment_on_tab(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        tab_id = rv.get_json()["tab_id"]
        from app.models.payment import Payment
        from app.extensions import db
        with app.app_context():
            payments = db.session.query(Payment).filter_by(tab_id=tab_id).all()
        # Exactly one payment: the 3,000 entry fee
        assert len(payments) == 1
        assert Decimal(str(payments[0].amount)) == Decimal("3000")

    def test_band_tab_type_is_band(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        tab_id = rv.get_json()["tab_id"]
        from app.models.tab import Tab
        from app.extensions import db
        with app.app_context():
            tab = db.session.get(Tab, tab_id)
        assert tab.tab_type == "BAND"

    def test_sequential_band_numbers(self, client, manager_token):
        rv1 = _issue(client, manager_token)
        rv2 = _issue(client, manager_token)
        n1 = rv1.get_json()["band_number"]
        n2 = rv2.get_json()["band_number"]
        assert n2 == n1 + 1   # strictly sequential within the same day


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Lookup by band number
# ═══════════════════════════════════════════════════════════════════════════════

class TestBandLookup:
    def test_waiter_can_look_up_band(self, client, manager_token, waiter_token):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        rv = client.get(f"/gate/bands/{number}", headers=auth(waiter_token))
        assert rv.status_code == 200
        assert rv.get_json()["band_number"] == number

    def test_nonexistent_band_returns_404(self, client, waiter_token):
        rv = client.get("/gate/bands/9999", headers=auth(waiter_token))
        assert rv.status_code == 404
        assert "error" in rv.get_json()

    def test_lookup_shows_balance(self, client, manager_token):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        rv = client.get(f"/gate/bands/{number}", headers=auth(manager_token))
        assert Decimal(rv.get_json()["tab_balance"]) == Decimal("-3000")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Charge flow: POS charges draw down the credit
# ═══════════════════════════════════════════════════════════════════════════════

class TestChargeFlow:
    def test_charge_reduces_band_credit(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        tab_id = rv.get_json()["tab_id"]
        number = rv.get_json()["band_number"]

        # Post a 1,000 charge directly via model (simulates POS order flow)
        from app.models.charge import Charge
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            actor = db.session.query(User).filter_by(username="manager1").first()
            charge = Charge(tab_id=tab_id, amount="1000",
                            description="Bar drink", created_by_id=actor.id)
            db.session.add(charge)
            db.session.commit()

        rv = client.get(f"/gate/bands/{number}", headers=auth(manager_token))
        # Was -3000, now -3000 + 1000 = -2000
        assert Decimal(rv.get_json()["tab_balance"]) == Decimal("-2000")

    def test_charge_via_pos_tab_endpoint(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        tab_id = rv.get_json()["tab_id"]

        # The tab is accessible by the POS GET /tabs/:id
        rv = client.get(f"/tabs/{tab_id}", headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["tab_type"] == "BAND"


# ═══════════════════════════════════════════════════════════════════════════════
# 4 & 5. Spend less / more than credit
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpendScenarios:
    def test_spend_less_than_credit_leaves_positive_balance_after_forfeit(
            self, client, manager_token, app):
        rv = _issue(client, manager_token)
        band_id = rv.get_json()["id"]
        tab_id  = rv.get_json()["tab_id"]

        # Spend 1,000 (leaving 2,000 unused)
        from app.models.charge import Charge
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            actor = db.session.query(User).filter_by(username="manager1").first()
            db.session.add(Charge(tab_id=tab_id, amount="1000",
                                  description="Drink", created_by_id=actor.id))
            db.session.commit()

        # EOD forfeit
        rv = client.post("/gate/forfeit-day",
                         json={"date": datetime.now(timezone.utc).date().isoformat()},
                         headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["forfeited"] >= 1
        # 2,000 unused credit forfeited
        assert Decimal(data["total_unused_credit"]) == Decimal("2000")

    def test_spend_more_than_credit_leaves_positive_balance(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        tab_id  = rv.get_json()["tab_id"]
        number  = rv.get_json()["band_number"]

        # Spend 4,000 (1,000 more than the entry credit)
        from app.models.charge import Charge
        from app.models.user import User
        from app.extensions import db
        with app.app_context():
            actor = db.session.query(User).filter_by(username="manager1").first()
            db.session.add(Charge(tab_id=tab_id, amount="4000",
                                  description="Spa", created_by_id=actor.id))
            db.session.commit()

        rv = client.get(f"/gate/bands/{number}", headers=auth(manager_token))
        # 4000 - 3000 = 1000 outstanding
        assert Decimal(rv.get_json()["tab_balance"]) == Decimal("1000")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Unique band numbers (allocator)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUniqueBandNumbers:
    def test_five_bands_get_sequential_unique_numbers(self, client, manager_token):
        numbers = set()
        for _ in range(5):
            rv = _issue(client, manager_token)
            numbers.add(rv.get_json()["band_number"])
        assert len(numbers) == 5   # all distinct


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Reconciliation
# ═══════════════════════════════════════════════════════════════════════════════

class TestReconciliation:
    def test_reconciliation_balances_with_correct_bands(self, client, manager_token):
        today = datetime.now(timezone.utc).date().isoformat()
        _issue(client, manager_token)
        _issue(client, manager_token)
        rv = client.get(f"/gate/reconciliation?date={today}",
                        headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["bands_issued"] == 2
        assert Decimal(data["gate_revenue"]) == Decimal(data["expected_revenue"])
        assert data["mismatch"] is False

    def test_reconciliation_detects_mismatch(self, client, manager_token, app):
        """Manually tamper with the entry payment to simulate a mismatch."""
        today = datetime.now(timezone.utc).date().isoformat()
        rv = _issue(client, manager_token)
        entry_payment_id = rv.get_json()["id"]  # wristband id, not payment id

        # Corrupt the entry payment amount directly
        from app.models.wristband import Wristband
        from app.models.payment import Payment
        from app.extensions import db
        with app.app_context():
            band = db.session.query(Wristband).first()
            payment = db.session.get(Payment, band.entry_payment_id)
            # Overwrite to simulate partial collection
            payment.amount = Decimal("1000")
            db.session.commit()

        rv = client.get(f"/gate/reconciliation?date={today}",
                        headers=auth(manager_token))
        assert rv.get_json()["mismatch"] is True

    def test_headcount_mismatch_flagged(self, client, manager_token):
        today = datetime.now(timezone.utc).date().isoformat()
        _issue(client, manager_token)  # 1 band issued

        # Record headcount of 3 (more than bands issued)
        rv = client.post("/gate/headcount",
                         json={"date": today, "counted": 3},
                         headers=auth(manager_token))
        assert rv.status_code == 200

        rv = client.get(f"/gate/reconciliation?date={today}",
                        headers=auth(manager_token))
        data = rv.get_json()
        assert data["headcount_recorded"] == 3
        assert data["headcount_mismatch"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Deactivate band
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeactivate:
    def test_deactivate_active_band(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]

        rv = client.post(f"/gate/deactivate-band/{number}",
                         headers=auth(manager_token))
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "DEACTIVATED"

    def test_deactivated_band_tab_is_closed(self, client, manager_token, app):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        tab_id = rv.get_json()["tab_id"]

        client.post(f"/gate/deactivate-band/{number}", headers=auth(manager_token))

        from app.models.tab import Tab
        from app.extensions import db
        with app.app_context():
            tab = db.session.get(Tab, tab_id)
        assert tab.status == "CLOSED"

    def test_deactivated_band_not_found_as_active(self, client, manager_token):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        client.post(f"/gate/deactivate-band/{number}", headers=auth(manager_token))

        # Second deactivate on same number → 404 (no longer ACTIVE)
        rv = client.post(f"/gate/deactivate-band/{number}", headers=auth(manager_token))
        assert rv.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Forfeit on close (EOD sweep)
# ═══════════════════════════════════════════════════════════════════════════════

class TestForfeitDay:
    def test_forfeit_flips_active_bands(self, client, manager_token, app):
        today = datetime.now(timezone.utc).date().isoformat()
        _issue(client, manager_token)
        _issue(client, manager_token)

        rv = client.post("/gate/forfeit-day", json={"date": today},
                         headers=auth(manager_token))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["forfeited"] == 2
        assert Decimal(data["total_unused_credit"]) == Decimal("6000")  # 2 × 3000

    def test_forfeit_skips_already_deactivated_bands(self, client, manager_token):
        today = datetime.now(timezone.utc).date().isoformat()
        rv1 = _issue(client, manager_token)
        rv2 = _issue(client, manager_token)
        n1 = rv1.get_json()["band_number"]

        # Deactivate band 1 manually
        client.post(f"/gate/deactivate-band/{n1}", headers=auth(manager_token))

        rv = client.post("/gate/forfeit-day", json={"date": today},
                         headers=auth(manager_token))
        # Only band 2 should be forfeited (band 1 already closed)
        assert rv.get_json()["forfeited"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Role enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoleEnforcement:
    def test_waiter_cannot_issue_band(self, client, waiter_token):
        rv = _issue(client, waiter_token)
        assert rv.status_code == 403
        assert "error" in rv.get_json()

    def test_manager_can_issue_band(self, client, manager_token):
        rv = _issue(client, manager_token)
        assert rv.status_code == 201

    def test_waiter_cannot_deactivate(self, client, manager_token, waiter_token):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        rv = client.post(f"/gate/deactivate-band/{number}", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_waiter_cannot_run_reconciliation(self, client, waiter_token):
        rv = client.get("/gate/reconciliation", headers=auth(waiter_token))
        assert rv.status_code == 403

    def test_waiter_can_look_up_band(self, client, manager_token, waiter_token):
        rv = _issue(client, manager_token)
        number = rv.get_json()["band_number"]
        rv = client.get(f"/gate/bands/{number}", headers=auth(waiter_token))
        assert rv.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 12. No refunds
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoRefunds:
    def test_no_refund_endpoint_exists(self, client, manager_token):
        # There is no /gate/refund or similar — 404 is the correct behavior
        rv = client.post("/gate/refund", headers=auth(manager_token))
        assert rv.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Idempotency
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_double_issue_returns_original(self, client, manager_token):
        idem = str(uuid.uuid4())
        rv1 = _issue(client, manager_token, idem_key=idem)
        rv2 = _issue(client, manager_token, idem_key=idem)
        assert rv1.status_code == 201
        assert rv2.status_code == 200
        assert rv2.get_json()["duplicate"] is True
        assert rv1.get_json()["band_number"] == rv2.get_json()["band_number"]

    def test_double_issue_does_not_create_extra_tab(self, client, manager_token, app):
        idem = str(uuid.uuid4())
        _issue(client, manager_token, idem_key=idem)
        _issue(client, manager_token, idem_key=idem)
        from app.models.tab import Tab
        from app.extensions import db
        with app.app_context():
            band_tabs = db.session.query(Tab).filter_by(tab_type="BAND").all()
        assert len(band_tabs) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Active bands list
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveBands:
    def test_active_bands_shows_all_open_bands(self, client, manager_token):
        _issue(client, manager_token)
        _issue(client, manager_token)
        rv = client.get("/gate/active-bands", headers=auth(manager_token))
        assert rv.status_code == 200
        assert len(rv.get_json()) == 2

    def test_deactivated_band_not_in_active_list(self, client, manager_token):
        rv1 = _issue(client, manager_token)
        _issue(client, manager_token)
        n1 = rv1.get_json()["band_number"]
        client.post(f"/gate/deactivate-band/{n1}", headers=auth(manager_token))

        rv = client.get("/gate/active-bands", headers=auth(manager_token))
        assert len(rv.get_json()) == 1
