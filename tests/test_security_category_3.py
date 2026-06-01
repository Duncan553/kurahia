"""
tests/test_security_category_3.py — Category 3: Data Integrity & Concurrency

Pre-run predictions:
3.1  PASS  — app-level idem check + UNIQUE constraint
3.2  PASS  — server auto-generates UUID; two keyless requests → two distinct rows
3.3  PASS  — UNIQUE(band_number, issue_date) backstops; SQLite serialises writers
3.4  PASS  — payment_id is PK on cash_recon_payments; second link raises IntegrityError
3.5  FAIL  — check_resource_availability() is a plain SELECT (no lock); both writes succeed
3.6  FAIL  — no stock-level guard in spoilage endpoint; no JudgeAlert for negative stock
3.7  PASS  — verify_chain() re-hashes every row; tampered field breaks chain
3.8  PASS  — all flushes inside issue_band() are uncommitted; exception → rollback
3.9  PASS  — no public PATCH endpoint accepts unit_price_snapshot / base_total / expected_amount
3.10 PASS  — append-only Charge rows; get_tab_balance() is a pure SUM, no lost updates
3.11 PASS  — every migration file has a real downgrade() with op.* calls
"""
import uuid
import pytest
import importlib.util
import inspect
import os
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 3.1  Idempotency key replay — same key sent twice
# ══════════════════════════════════════════════════════════════════════════════

class TestIdempotencyReplay:
    def test_duplicate_payment_key_returns_original_row(self, app, client, manager_token):
        """Same idempotency_key → second call returns 200+duplicate=True; exactly ONE DB row."""
        from app.models.payment import Payment
        from app.extensions import db

        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]

        idem_key = str(uuid.uuid4())
        payload = {"amount": "500", "method": "CASH", "idempotency_key": idem_key}

        rv1 = client.post(f"/tabs/{tab_id}/payments", json=payload, headers=auth(manager_token))
        rv2 = client.post(f"/tabs/{tab_id}/payments", json=payload, headers=auth(manager_token))

        assert rv1.status_code == 201, f"First payment failed: {rv1.get_json()}"
        assert rv2.status_code == 200,  f"Replay should return 200, got {rv2.status_code}"
        assert rv2.get_json().get("duplicate") is True, "Missing duplicate=True on replay"

        count = db.session.query(Payment).filter_by(idempotency_key=idem_key).count()
        assert count == 1, f"Replay wrote {count} rows; UNIQUE constraint not enforced"


# ══════════════════════════════════════════════════════════════════════════════
# 3.2  No idempotency key — anti-coalescing
# ══════════════════════════════════════════════════════════════════════════════

class TestAntiCoalescing:
    def test_two_keyless_requests_produce_two_distinct_rows(self, app, client, manager_token):
        """No idempotency_key supplied → server generates a UUID each time → two distinct rows."""
        from app.models.payment import Payment
        from app.extensions import db

        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]

        before = db.session.query(Payment).filter_by(tab_id=tab_id).count()

        payload = {"amount": "300", "method": "CASH"}  # no idempotency_key
        rv1 = client.post(f"/tabs/{tab_id}/payments", json=payload, headers=auth(manager_token))
        rv2 = client.post(f"/tabs/{tab_id}/payments", json=payload, headers=auth(manager_token))

        assert rv1.status_code == 201, f"First keyless payment failed: {rv1.get_json()}"
        assert rv2.status_code == 201, f"Second keyless payment failed: {rv2.get_json()}"

        after = db.session.query(Payment).filter_by(tab_id=tab_id).count()
        assert after == before + 2, (
            f"Expected {before + 2} payment rows, got {after}. "
            "Silent coalescing occurred — two distinct payments were merged."
        )

        id1 = rv1.get_json()["payment_id"]
        id2 = rv2.get_json()["payment_id"]
        assert id1 != id2, "Two keyless requests returned the same payment_id (coalesced)"


# ══════════════════════════════════════════════════════════════════════════════
# 3.3  Concurrent band issuance — unique numbers
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentBandIssuance:
    def test_ten_sequential_bands_all_unique(self, app, manager_token, client):
        """
        10 band issues in fast succession all get unique band numbers.
        True threading is avoided here: SQLite in-memory + StaticPool requires
        check_same_thread=False for shared access, which is not in TestingConfig.
        The allocator (SELECT FOR UPDATE + flush) and UNIQUE(band_number, issue_date)
        both enforce uniqueness — tested here at the service layer.
        """
        band_numbers = []
        for _ in range(10):
            rv = client.post("/gate/issue-band",
                             json={"method": "CASH", "idempotency_key": str(uuid.uuid4())},
                             headers=auth(manager_token))
            assert rv.status_code == 201, f"Band issuance failed: {rv.get_json()}"
            band_numbers.append(rv.get_json()["band_number"])

        assert len(set(band_numbers)) == 10, (
            f"Duplicate band numbers issued: {sorted(band_numbers)}. "
            "allocate_band_number() or UNIQUE constraint failed."
        )
        assert band_numbers == list(range(1, 11)), (
            f"Expected sequential 1–10, got: {band_numbers}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.4  Double reconciliation — PK on cash_recon_payments.payment_id
# ══════════════════════════════════════════════════════════════════════════════

class TestDoubleReconciliationRace:
    def test_payment_cannot_be_swept_into_two_reconciliations(self, app, client, manager_token):
        """
        payment_id is the PRIMARY KEY of cash_recon_payments.
        Inserting the same payment_id twice must raise IntegrityError.
        """
        from app.models.payment import Payment
        from app.models.tab import Tab, TabType, TabStatus
        from app.models.cash_reconciliation import (
            CashReconciliation, ReconciliationStatus, cash_recon_payments
        )
        from app.models.user import User
        from app.extensions import db
        from sqlalchemy.exc import IntegrityError

        manager = db.session.query(User).filter_by(username="manager1").first()

        tab = Tab(tab_type=TabType.WALK_IN.value, reference="recon-test",
                  opened_by_id=manager.id, status=TabStatus.OPEN.value)
        db.session.add(tab)
        db.session.flush()

        payment = Payment(tab_id=tab.id, amount="500", method="CASH",
                          received_by_id=manager.id,
                          idempotency_key=str(uuid.uuid4()))
        db.session.add(payment)
        db.session.flush()

        def _make_recon():
            r = CashReconciliation(
                staff_id=manager.id, reconciled_by_id=manager.id,
                expected_amount="500", actual_amount="500", difference="0",
                period_start_utc=datetime.now(timezone.utc),
                period_end_utc=datetime.now(timezone.utc),
                status=ReconciliationStatus.BALANCED.value,
                idempotency_key=str(uuid.uuid4()),
            )
            db.session.add(r)
            db.session.flush()
            return r

        recon1 = _make_recon()
        db.session.execute(
            cash_recon_payments.insert().values(recon_id=recon1.id, payment_id=payment.id)
        )
        db.session.commit()

        recon2 = _make_recon()
        with pytest.raises(IntegrityError):
            db.session.execute(
                cash_recon_payments.insert().values(recon_id=recon2.id, payment_id=payment.id)
            )
            db.session.commit()
        db.session.rollback()

    def test_second_reconcile_call_finds_no_pending_after_first(self, app, client, manager_token):
        """
        App-level guard: get_staff_pending_cash() excludes already-reconciled payments.
        A second reconciliation attempt finds zero pending → no double-sweep at HTTP level.
        """
        from app.models.user import User
        from app.extensions import db

        manager = db.session.query(User).filter_by(username="manager1").first()

        # Record a CASH payment by the manager
        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]
        client.post(f"/tabs/{tab_id}/payments",
                    json={"amount": "500", "method": "CASH",
                          "idempotency_key": str(uuid.uuid4())},
                    headers=auth(manager_token))

        # First reconciliation sweeps the payment
        rv1 = client.post("/finance/cash/reconcile",
                          json={"staff_id": manager.id, "actual_amount": "500",
                                "idempotency_key": str(uuid.uuid4())},
                          headers=auth(manager_token))
        assert rv1.status_code == 201
        assert rv1.get_json()["payments_swept"] == 1

        # Second reconciliation finds nothing left to sweep
        rv2 = client.post("/finance/cash/reconcile",
                          json={"staff_id": manager.id, "actual_amount": "0",
                                "idempotency_key": str(uuid.uuid4())},
                          headers=auth(manager_token))
        assert rv2.status_code == 201
        assert rv2.get_json()["payments_swept"] == 0, (
            "Second reconciliation swept already-reconciled payments — double-sweep bug"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.5  Concurrent booking — overlapping dates, no SELECT FOR UPDATE
# PREDICTION: FAIL — design gap
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentBookingOverlap:
    def test_overlapping_bookings_no_db_constraint(self, app, client, manager_token):
        """
        DESIGN GAP: check_resource_availability() is a plain SELECT — no row lock.
        Two concurrent transactions can both pass the availability check and both commit.
        This test bypasses the HTTP layer to show the DB has no constraint that prevents it.

        Fix options:
          A) SELECT FOR UPDATE on the resource row inside check_resource_availability()
          B) Postgres EXCLUDE USING gist(resource_id, tsrange(check_in, check_out))
          C) Daily conflict-sweep CLI command as a detective control

        Do NOT fix here — report only.
        """
        from app.models.booking import Booking, BookingStatus
        from app.models.bookable_resource import BookableResource
        from app.models.user import User
        from app.extensions import db
        from app.services.booking import check_resource_availability

        resource = BookableResource(name="Race Villa", resource_type="VILLA",
                                    base_price="10000", is_active=True)
        db.session.add(resource)
        db.session.flush()

        owner = db.session.query(User).filter_by(username="owner1").first()
        check_in  = datetime(2026, 7, 1, tzinfo=timezone.utc)
        check_out = datetime(2026, 7, 3, tzinfo=timezone.utc)

        # Both threads see no overlap before either commits — this is the race window
        avail_a, _ = check_resource_availability(resource.id, check_in, check_out)
        avail_b, _ = check_resource_availability(resource.id, check_in, check_out)
        assert avail_a and avail_b, "Both availability reads must return True to model the race"

        # Thread A commits
        booking_a = Booking(
            resource_id=resource.id, guest_name="Guest A", guest_phone="0700000001",
            check_in_planned_utc=check_in, check_out_planned_utc=check_out,
            base_total="20000", number_of_guests=1,
            status=BookingStatus.CONFIRMED.value, created_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(booking_a)
        db.session.commit()

        # Thread B also commits — DB should block but has no constraint to do so
        booking_b = Booking(
            resource_id=resource.id, guest_name="Guest B", guest_phone="0700000002",
            check_in_planned_utc=check_in, check_out_planned_utc=check_out,
            base_total="20000", number_of_guests=1,
            status=BookingStatus.CONFIRMED.value, created_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(booking_b)
        db.session.commit()

        count = db.session.query(Booking).filter(
            Booking.resource_id == resource.id,
            Booking.status == BookingStatus.CONFIRMED.value,
        ).count()

        assert count == 1, (
            f"DESIGN GAP: {count} overlapping CONFIRMED bookings committed for the same villa "
            f"on {check_in.date()} – {check_out.date()}. "
            "check_resource_availability() has no row lock — concurrent transactions both pass "
            "the SELECT before either commits. Mitigation required (see options in docstring)."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.6  Negative stock — no guard, no alert
# PREDICTION: FAIL — design gap
# ══════════════════════════════════════════════════════════════════════════════

class TestNegativeStock:
    def test_spoilage_beyond_stock_rejected_or_alerted(self, app, client, manager_token):
        """
        Stock = 5 units. Spoilage of 10 requested.
        Expected (secure): 400 rejection OR 201 + JudgeAlert for negative stock.
        Actual (gap):      201 accepted silently, stock = -5, no alert.

        Do NOT fix here — report only.
        """
        from app.models.inventory_item import InventoryItem
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.models.department import Department
        from app.services.stock import get_current_stock
        from app.extensions import db

        dept = db.session.query(Department).filter_by(name="General").first()
        owner = db.session.query(User).filter_by(username="owner1").first()

        item = InventoryItem(name="Test Beef", unit="kg",
                             reorder_level=Decimal("2"), department_id=dept.id)
        db.session.add(item)
        db.session.flush()

        # Stock in 5 units
        db.session.add(StockMovement(
            item_id=item.id, change_amount=Decimal("5"),
            reason=MovementReason.PURCHASE.value, actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()

        assert get_current_stock(item.id) == Decimal("5")

        # Request spoilage of 10 (would take stock to -5)
        rv = client.post("/inventory/movements/spoilage",
                         json={"item_id": item.id, "quantity": "10",
                               "idempotency_key": str(uuid.uuid4())},
                         headers=auth(manager_token))

        if rv.status_code in (400, 409):
            # System correctly rejected — test passes
            return

        # Movement was accepted. Check for compensating JudgeAlert
        assert rv.status_code == 201, f"Unexpected status: {rv.status_code} {rv.get_json()}"

        db.session.expire_all()
        stock_after = get_current_stock(item.id)
        alert = db.session.query(JudgeAlert).filter(
            JudgeAlert.description.like(f"%{item.name}%")
        ).first()

        assert stock_after >= Decimal("0") or alert is not None, (
            f"DESIGN GAP: spoilage of 10 on stock=5 was accepted (201). "
            f"Stock is now {stock_after} and no JudgeAlert was raised. "
            "The spoilage endpoint (_write_movement) writes whatever negative amount is requested "
            "without checking get_current_stock(). Mitigation: add stock-check guard in "
            "_write_movement or in the endpoint, OR fire NEGATIVE_STOCK JudgeAlert post-write."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.7  Audit log tampering detection
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditLogTamper:
    def test_verify_chain_detects_tampered_row(self, app, client, manager_token):
        """
        Modify a committed audit row via ORM (simulates bad actor with DB access).
        verify_chain() must return False and name the tampered row.
        Restores original value before asserting so test teardown stays clean
        (though each test already gets a fresh DB; this is belt-and-braces).
        """
        from app.models.audit_log import AuditLog
        from app.extensions import db

        # Generate real audit entries via a login
        client.post("/auth/login",
                    json={"username": "manager1", "password": "ManagerPass1!"})

        ok, msg = AuditLog.verify_chain()
        assert ok, f"Chain was already broken before tampering — setup issue: {msg}"

        row = db.session.query(AuditLog).order_by(AuditLog.timestamp.asc()).first()
        assert row is not None, "No audit rows to tamper with"

        original_actor  = row.actor
        original_hash   = row.entry_hash

        # Tamper: change the actor field (simulating direct-DB edit by a bad actor)
        row.actor = "__tampered__"
        db.session.commit()

        ok, reason = AuditLog.verify_chain()

        # Restore BEFORE asserting so a test failure doesn't leave a dirty chain
        row.actor = original_actor
        db.session.commit()

        assert not ok, (
            "verify_chain() returned True after tampering — hash check is not working"
        )
        assert row.id in reason or "tampered" in reason.lower() or "broken" in reason.lower(), (
            f"verify_chain() returned False but didn't identify the tampered row. "
            f"Reason: {reason!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.8  Transaction atomicity — partial failure rolls back everything
# ══════════════════════════════════════════════════════════════════════════════

class TestTransactionAtomicity:
    def test_band_issuance_failure_rolls_back_all_writes(self, app, client, manager_token):
        """
        Mock open_band_tab to raise after allocate_band_number() has already flushed
        a WristbandCounter row. The unhandled exception causes Flask-SQLAlchemy to
        roll back the whole transaction on request teardown.
        Expected: zero new Wristband, Tab, Payment, WristbandCounter rows.
        """
        from app.models.wristband import Wristband
        from app.models.tab import Tab
        from app.models.payment import Payment
        from app.models.wristband_counter import WristbandCounter
        from app.extensions import db

        before_bands    = db.session.query(Wristband).count()
        before_tabs     = db.session.query(Tab).count()
        before_payments = db.session.query(Payment).count()
        before_counters = db.session.query(WristbandCounter).count()

        # Flask TESTING=True re-raises unhandled exceptions to the test client.
        # The outer app_context (from the `app` fixture) survives the request,
        # so db.session.remove() doesn't auto-run here the way it would in production.
        # We explicitly rollback to mirror what production teardown does on a 500.
        from app.extensions import db as _db
        try:
            with patch("app.services.gate.open_band_tab",
                       side_effect=RuntimeError("Simulated mid-issuance failure")):
                client.post("/gate/issue-band",
                            json={"method": "CASH",
                                  "idempotency_key": str(uuid.uuid4())},
                            headers=auth(manager_token))
        except RuntimeError:
            _db.session.rollback()  # simulate production app-context teardown on 500

        # Full rollback: every table should be unchanged
        assert db.session.query(Wristband).count()       == before_bands,    "Wristband row not rolled back"
        assert db.session.query(Tab).count()             == before_tabs,     "Tab row not rolled back"
        assert db.session.query(Payment).count()         == before_payments, "Payment row not rolled back"
        assert db.session.query(WristbandCounter).count() == before_counters, "WristbandCounter not rolled back"


# ══════════════════════════════════════════════════════════════════════════════
# 3.9  Frozen field immutability
# ══════════════════════════════════════════════════════════════════════════════

class TestFrozenFields:
    def test_unit_price_snapshot_no_patch_endpoint(self, app, client, manager_token, food_item_id):
        """unit_price_snapshot is set once at order time; no PATCH endpoint accepts it."""
        from app.models.order import Order
        from app.extensions import db

        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]

        rv = client.post("/orders",
                         json={"tab_id": tab_id,
                               "items": [{"menu_item_id": food_item_id, "quantity": 1}]},
                         headers=auth(manager_token))
        assert rv.status_code == 201, f"Order create failed: {rv.get_json()}"
        order_id = rv.get_json()["id"]

        order = db.session.get(Order, order_id)
        item  = order.items[0]
        original_snapshot = Decimal(str(item.unit_price_snapshot))

        # Probe the would-be PATCH endpoint (status transitions use /order-items/<id>/receive etc.)
        rv = client.patch(f"/order-items/{item.id}",
                          json={"unit_price_snapshot": "1"},
                          headers=auth(manager_token))
        assert rv.status_code in (404, 405), (
            f"PATCH /order-items/<id> returned {rv.status_code} — "
            "an edit endpoint may exist for a frozen field"
        )

        db.session.expire(item)
        assert Decimal(str(item.unit_price_snapshot)) == original_snapshot, (
            f"unit_price_snapshot changed from {original_snapshot} to {item.unit_price_snapshot}"
        )

    def test_booking_base_total_not_accepted_on_confirm(self, app, client, manager_token):
        """Confirm endpoint changes status only; base_total sent in body is ignored."""
        from app.models.bookable_resource import BookableResource
        from app.models.booking import Booking, BookingStatus
        from app.models.user import User
        from app.extensions import db

        resource = BookableResource(name="Frozen Villa", resource_type="VILLA",
                                    base_price="5000", is_active=True)
        db.session.add(resource)
        db.session.flush()

        owner = db.session.query(User).filter_by(username="owner1").first()
        booking = Booking(
            resource_id=resource.id,
            guest_name="Test Guest", guest_phone="0700000001",
            check_in_planned_utc=datetime(2027, 1, 1, tzinfo=timezone.utc),
            check_out_planned_utc=datetime(2027, 1, 3, tzinfo=timezone.utc),
            base_total="10000", number_of_guests=1,
            status=BookingStatus.HELD.value, created_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(booking)
        db.session.commit()

        # Confirm with a fake base_total in the body
        rv = client.post(f"/bookings/{booking.id}/confirm",
                         json={"base_total": "1"},
                         headers=auth(manager_token))
        # Confirm returns 200 for status transition; base_total must be unchanged
        assert rv.status_code in (200, 400), f"Confirm returned {rv.status_code}: {rv.get_json()}"

        db.session.expire(booking)
        assert Decimal(str(booking.base_total)) == Decimal("10000"), (
            f"base_total changed to {booking.base_total} via confirm endpoint — frozen field is mutable"
        )

    def test_cash_recon_no_edit_endpoint_exists(self, app, client, manager_token):
        """CashReconciliation is append-only; no PATCH/PUT endpoint should exist."""
        fake_id = str(uuid.uuid4())
        rv = client.patch(f"/finance/cash/reconcile/{fake_id}",
                          json={"expected_amount": "1"},
                          headers=auth(manager_token))
        assert rv.status_code in (404, 405), (
            f"PATCH /finance/cash/reconcile/<id> returned {rv.status_code} — "
            "an edit endpoint exists for a frozen reconciliation record"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.10  Concurrent charges on same tab — append-only, no lost updates
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentCharges:
    def test_ten_charges_all_recorded_and_sum_correctly(self, app, client, manager_token):
        """
        10 charges added to the same tab (rapid sequential, same invariant as concurrent).
        Append-only design: no shared mutable cell, so no lost updates possible.
        All 10 rows must exist; get_tab_balance() must equal the exact sum.

        Note: true threading not used here (SQLite in-memory shares a single connection
        but requires StaticPool + check_same_thread=False for thread safety, not set in
        TestingConfig). The append-only invariant holds regardless of call ordering.
        """
        from app.models.charge import Charge
        from app.models.user import User
        from app.services.tab import get_tab_balance
        from app.extensions import db

        rv = client.post("/tabs", json={"tab_type": "WALK_IN"}, headers=auth(manager_token))
        tab_id = rv.get_json()["id"]

        manager = db.session.query(User).filter_by(username="manager1").first()
        charge_amount = Decimal("100")

        for i in range(10):
            charge = Charge(
                tab_id=tab_id,
                amount=charge_amount,
                description=f"test-charge-{i}",
                created_by_id=manager.id,
            )
            db.session.add(charge)
        db.session.commit()

        count = db.session.query(Charge).filter_by(tab_id=tab_id).count()
        assert count == 10, f"Expected 10 charge rows, got {count} — some were lost"

        balance = get_tab_balance(tab_id)
        assert balance == Decimal("1000"), (
            f"Expected balance of 1000, got {balance} — SUM is wrong or rows are missing"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.11  Migration reversibility — all migrations have real downgrade()
# ══════════════════════════════════════════════════════════════════════════════

class TestMigrationReversibility:
    def test_all_migrations_have_real_downgrade(self, app):
        """
        Every migration must define a downgrade() that contains at least one op.* call.
        A stub downgrade (empty body or just 'pass') means the migration cannot be
        rolled back — a production disaster if a bad deploy needs reverting.
        """
        versions_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations", "versions",
        )
        stubs = []

        for fname in sorted(os.listdir(versions_dir)):
            if not fname.endswith(".py") or fname.startswith("__"):
                continue
            path = os.path.join(versions_dir, fname)
            spec = importlib.util.spec_from_file_location("_migration", path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            fn = getattr(mod, "downgrade", None)
            if fn is None:
                stubs.append(f"{fname}: missing downgrade() entirely")
                continue

            src = inspect.getsource(fn)
            if "op." not in src:
                stubs.append(f"{fname}: downgrade() has no op.* calls (stub or empty)")

        assert not stubs, (
            "Migrations without a real downgrade() — cannot roll back safely:\n"
            + "\n".join(f"  • {s}" for s in stubs)
        )
