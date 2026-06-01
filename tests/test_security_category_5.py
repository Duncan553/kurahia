"""
tests/test_security_category_5.py — Category 5: Operational & Disaster Recovery

Pre-run predictions:
5.1  PASS    — booking partial failure rolls back all writes (Booking + audit)
5.2  PARTIAL — gate/flag-no-shows/deliver-due naturally idempotent (status-based
               filters); run-daily and flag-incomplete FAIL — no _open_exists()
               guard, duplicate cron run creates duplicate JudgeAlert rows
5.3  PASS    — backup produces a non-empty SQLite file with all expected tables
5.4  PASS    — uncommitted flush → rollback → no persistence; SQLite transaction holds
5.8  PASS    — Payment.created_at_utc uses server default; no API field for it
5.9  FAIL    — concurrent run_daily creates duplicate alerts (same gap as 5.2)
"""
import uuid
import threading
import os
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


# ══════════════════════════════════════════════════════════════════════════════
# 5.1  Transaction durability — booking partial failure rolls back everything
# ══════════════════════════════════════════════════════════════════════════════

class TestTransactionDurabilityBooking:
    def test_booking_partial_failure_rolls_back(self, app, client, manager_token):
        """
        Mid-write exception after Booking is flushed but before AuditLog.log.
        Expect: zero new Booking rows — the whole transaction reverts.
        Different code path from Cat 3 3.8 (that exercised gate issuance).
        """
        from app.models.booking import Booking
        from app.models.bookable_resource import BookableResource
        from app.extensions import db as _db

        resource = BookableResource(name="Partial Villa", resource_type="VILLA",
                                    base_price="5000", is_active=True)
        _db.session.add(resource)
        _db.session.commit()

        before = _db.session.query(Booking).count()

        # AuditLog.log is called after the Booking insert in create_booking()
        with patch("app.bookings.core.AuditLog.log",
                   side_effect=RuntimeError("simulated disk fault mid-write")):
            app.config["TESTING"] = False
            app.config["PROPAGATE_EXCEPTIONS"] = False
            try:
                rv = client.post(
                    "/bookings",
                    json={
                        "resource_id": resource.id,
                        "guest_name": "Test Guest", "guest_phone": "0700000001",
                        "check_in_planned_utc": "2027-03-01T14:00:00",
                        "check_out_planned_utc": "2027-03-03T11:00:00",
                        "number_of_guests": 1,
                        "idempotency_key": str(uuid.uuid4()),
                    },
                    headers={"Authorization": f"Bearer {manager_token}"},
                )
                assert rv.status_code == 500, f"Expected 500, got {rv.status_code}"
            finally:
                app.config["TESTING"] = True
                app.config["PROPAGATE_EXCEPTIONS"] = True
                _db.session.rollback()

        after = _db.session.query(Booking).count()
        assert after == before, (
            f"Partial write persisted: DB has {after} bookings, expected {before}. "
            "Booking was committed before the AuditLog fault — atomicity broken."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5.2  Scheduled-task idempotency — double-run must not double-effect
# ══════════════════════════════════════════════════════════════════════════════

class TestScheduledTaskIdempotency:

    def test_gate_close_day_idempotent(self, app):
        """gate close-day: forfeits ACTIVE bands; second run finds none → 0 forfeited."""
        from app.services.gate import issue_band, forfeit_day
        from app.models.wristband import Wristband, WristbandStatus
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        today = datetime.now(timezone.utc).date().isoformat()

        for i in range(3):
            issue_band(actor_id=owner.id, method="CASH",
                       mpesa_code=None, card_ref=None,
                       idem_key=f"idem-test-band-{i}-{uuid.uuid4()}")
        db.session.commit()

        count1, _ = forfeit_day(today, owner.id)
        db.session.commit()
        count2, _ = forfeit_day(today, owner.id)
        db.session.commit()

        active_after = db.session.query(Wristband).filter_by(
            issue_date=today, status=WristbandStatus.ACTIVE.value
        ).count()

        assert count2 == 0, (
            f"gate close-day second run forfeited {count2} bands — "
            "first run should have already forfeited all ACTIVE bands"
        )
        assert active_after == 0, "ACTIVE bands remain after two close-day runs"

    def test_flag_no_shows_idempotent(self, app):
        """bookings flag-no-shows: second run finds no HELD/CONFIRMED past check-in → 0."""
        from app.services.booking import flag_no_shows
        from app.models.booking import Booking, BookingStatus
        from app.models.bookable_resource import BookableResource
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        resource = BookableResource(name="No-Show Villa", resource_type="VILLA",
                                    base_price="5000", is_active=True)
        db.session.add(resource)
        db.session.flush()

        past = datetime.now(timezone.utc) - timedelta(hours=6)
        booking = Booking(
            resource_id=resource.id, guest_name="No Show Guest",
            guest_phone="0700000001", number_of_guests=1,
            check_in_planned_utc=past,
            check_out_planned_utc=past + timedelta(days=2),
            base_total="10000", status=BookingStatus.CONFIRMED.value,
            idempotency_key=str(uuid.uuid4()), created_by_id=owner.id,
        )
        db.session.add(booking)
        db.session.commit()

        count1 = flag_no_shows()
        db.session.commit()
        count2 = flag_no_shows()
        db.session.commit()

        assert count1 == 1, f"Expected 1 no-show flagged on first run, got {count1}"
        assert count2 == 0, (
            f"flag-no-shows second run flagged {count2} bookings — "
            "already-flagged bookings should be invisible to the second run"
        )

    def test_deliver_due_idempotent(self, app):
        """events deliver-due: second run finds no QUEUED notifications → 0 processed."""
        from app.services.notifications.dispatcher import deliver_due
        from app.models.notification import Notification, NotificationStatus, NotificationReferenceType
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        notif = Notification(
            recipient_user_id=owner.id,
            reference_type=NotificationReferenceType.GENERAL.value,
            subject="Test due notification",
            body="Due for delivery",
            status=NotificationStatus.QUEUED.value,
            channel="IN_APP",
            scheduled_for_utc=past,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(notif)
        db.session.commit()

        result1 = deliver_due(now=datetime.now(timezone.utc))
        db.session.commit()
        result2 = deliver_due(now=datetime.now(timezone.utc))
        db.session.commit()

        assert result1["total"] >= 1, "First deliver_due processed nothing"
        assert result2["total"] == 0, (
            f"deliver-due second run processed {result2['total']} notification(s) — "
            "already-delivered notifications should no longer be QUEUED"
        )

    def test_run_daily_not_idempotent(self, app):
        """
        IDEMPOTENCY GAP: judge run-daily has no _open_exists() guard.
        Calling it twice with the same spoilage data creates duplicate JudgeAlerts.
        Fix: add an existing-open-alert check before _fire_alert() in run_daily.
        Do NOT fix here — report only.
        """
        from app.judge.engine import run_daily
        from app.models.inventory_item import InventoryItem
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.models.department import Department
        from app.extensions import db

        dept  = db.session.query(Department).filter_by(name="General").first()
        owner = db.session.query(User).filter_by(username="owner1").first()

        item = InventoryItem(name="Watch Beer", unit="bottle",
                             reorder_level=Decimal("2"), is_watch_list=True,
                             department_id=dept.id)
        db.session.add(item)
        db.session.flush()

        # Stock + spoilage > SPIKE_THRESHOLD (10)
        db.session.add(StockMovement(
            item_id=item.id, change_amount=Decimal("50"),
            reason=MovementReason.PURCHASE.value, actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.add(StockMovement(
            item_id=item.id, change_amount=Decimal("-15"),
            reason=MovementReason.SPOILAGE.value, actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()

        today = datetime.now(timezone.utc)
        run_daily(today)
        db.session.commit()
        run_daily(today)
        db.session.commit()

        alert_count = db.session.query(JudgeAlert).filter_by(
            alert_type="SPOILAGE_SPIKE", item_id=item.id
        ).count()

        assert alert_count == 1, (
            f"IDEMPOTENCY GAP: run_daily called twice produced {alert_count} "
            f"SPOILAGE_SPIKE alerts instead of 1. "
            "run_daily() has no _open_exists() deduplication check. "
            "A cron misfire or manual re-run creates duplicate owner alerts."
        )

    def test_flag_incomplete_not_idempotent(self, app):
        """
        IDEMPOTENCY GAP: events flag-incomplete has no deduplication guard.
        Calling it twice on the same overdue IN_PROGRESS event creates
        duplicate EVENT_NOT_CLOSED JudgeAlert rows.
        Fix: add an _open_exists() check before creating the alert.
        Do NOT fix here — report only.
        """
        from app.models.event import Event, EventStatus
        from app.models.event_type import EventType
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        et = EventType(name=f"INCOMPLETE_TEST_{uuid.uuid4().hex[:6]}")
        db.session.add(et)
        db.session.flush()

        now = datetime.now(timezone.utc)
        event = Event(
            title="Overdue Test Event", event_type_id=et.id,
            starts_at_utc=now - timedelta(hours=5),
            ends_at_utc=now - timedelta(hours=2),
            expected_guests=10, created_by_id=owner.id,
            status=EventStatus.IN_PROGRESS.value,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(event)
        db.session.commit()

        runner = app.test_cli_runner()
        runner.invoke(args=["events", "flag-incomplete"])
        runner.invoke(args=["events", "flag-incomplete"])

        alert_count = db.session.query(JudgeAlert).filter_by(
            alert_type="EVENT_NOT_CLOSED"
        ).count()

        assert alert_count == 1, (
            f"IDEMPOTENCY GAP: flag-incomplete called twice produced {alert_count} "
            f"EVENT_NOT_CLOSED alerts instead of 1. "
            "No _open_exists() guard before creating the alert."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5.3  Backup integrity — schema and data round-trip
# ══════════════════════════════════════════════════════════════════════════════

class TestBackupIntegrity:
    def test_backup_produces_valid_sqlite_with_all_tables(self, app, tmp_path):
        """
        Backup of the dev SQLite DB creates a non-empty file with all tables
        intact and passing PRAGMA integrity_check.

        In-memory SQLite (TestingConfig) has no file to copy, so this test
        uses the dev DB directly — which always exists after `flask db upgrade`.
        The test is skipped if the dev DB is absent (CI without migrations run).
        """
        import shutil
        import sqlite3 as sqlite_lib

        dev_db = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "instance", "kurahia_dev.db"
        )
        if not os.path.exists(dev_db):
            pytest.skip("Dev SQLite DB not found — run flask db upgrade first")

        backup_dir = str(tmp_path / "backups")
        os.makedirs(backup_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest_file = os.path.join(backup_dir, f"backup_{ts}.db")
        shutil.copy2(dev_db, dest_file)

        assert os.path.getsize(dest_file) > 0, "Backup file is empty"

        conn = sqlite_lib.connect(dest_file)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()

        assert integrity == "ok", f"SQLite PRAGMA integrity_check: {integrity}"

        for expected in ["users", "audit_logs", "payments", "bookings",
                         "wristbands", "alembic_version"]:
            assert expected in tables, (
                f"Table '{expected}' missing from backup. Found: {sorted(tables)}"
            )

    def test_backup_of_inmemory_db_fails_gracefully(self, app, tmp_path):
        """
        In-memory SQLite (TestingConfig: sqlite:///:memory:) has no file to copy.
        The backup command should fail cleanly, not crash the process.
        """
        backup_dir = str(tmp_path / "backups_mem")
        runner = app.test_cli_runner()
        result = runner.invoke(args=["system_cli", "backup", "--dest", backup_dir])
        # Should exit non-zero or print an error — not raise an unhandled exception
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"Backup raised unexpected exception: {result.exception}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5.4  Power-loss simulation — uncommitted writes don't persist
# ══════════════════════════════════════════════════════════════════════════════

class TestPowerLossSimulation:
    def test_uncommitted_flush_does_not_persist(self, app):
        """
        Flush writes into a transaction, then rollback without committing.
        The DB must return to its pre-write state — simulates power loss mid-write.
        """
        from app.models.tab import Tab, TabType, TabStatus
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        before = db.session.query(Tab).count()

        # Flush (sends SQL to DB but stays in transaction)
        tab = Tab(tab_type=TabType.WALK_IN.value, reference="power-loss-test",
                  opened_by_id=owner.id, status=TabStatus.OPEN.value)
        db.session.add(tab)
        db.session.flush()   # row is visible within this session

        # Confirm the flush made it into the session (within-transaction visibility)
        mid_count = db.session.query(Tab).count()
        assert mid_count == before + 1, "Flush didn't write within transaction"

        # Simulate abrupt connection loss / power-off: rollback without commit
        db.session.rollback()

        after = db.session.query(Tab).count()
        assert after == before, (
            f"Uncommitted flush persisted after rollback. "
            f"Before: {before}, after rollback: {after}. "
            "SQLite/SQLAlchemy transaction semantics are broken."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5.8  Clock drift — server ignores client-provided timestamps
# ══════════════════════════════════════════════════════════════════════════════

class TestClockDrift:
    def test_payment_created_at_is_server_stamped(self, app, client, manager_token):
        """
        POST /tabs/<id>/payments does not accept created_at_utc from the client.
        The stored timestamp must be close to now, not the injected future date.
        """
        from app.models.payment import Payment
        from app.extensions import db

        rv = client.post("/tabs", json={"tab_type": "WALK_IN"},
                         headers={"Authorization": f"Bearer {manager_token}"})
        tab_id = rv.get_json()["id"]

        idem_key = str(uuid.uuid4())
        rv = client.post(f"/tabs/{tab_id}/payments",
                         json={
                             "amount": "500", "method": "CASH",
                             "idempotency_key": idem_key,
                             "created_at_utc": "2030-01-15T00:00:00",  # injected future date
                         },
                         headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201, f"Payment failed: {rv.get_json()}"

        payment = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
        stored = payment.created_at_utc
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)

        # Server timestamp must be within 60 seconds of now, not in 2030
        now = datetime.now(timezone.utc)
        delta = abs((stored - now).total_seconds())
        assert delta < 60, (
            f"Payment.created_at_utc is {stored.isoformat()} — "
            f"{delta:.0f}s from now. "
            "Client-supplied timestamp was accepted and stored instead of server clock."
        )
        assert stored.year < 2030, (
            f"Injected future timestamp 2030 was stored: {stored.isoformat()}"
        )

    def test_booking_system_timestamps_are_server_stamped(self, app, client, manager_token):
        """
        Booking.created_at_utc is server-stamped; check_in_actual_utc is set by
        the check-in endpoint, not by the client. Planning timestamps
        (check_in_planned_utc) are legitimately client-provided (future dates).
        """
        from app.models.booking import Booking
        from app.models.bookable_resource import BookableResource
        from app.extensions import db

        resource = BookableResource(name="Clock Villa", resource_type="VILLA",
                                    base_price="5000", is_active=True)
        db.session.add(resource)
        db.session.commit()

        idem_key = str(uuid.uuid4())
        rv = client.post("/bookings",
                         json={
                             "resource_id": resource.id,
                             "guest_name": "Clock Test", "guest_phone": "0700000001",
                             "check_in_planned_utc": "2027-12-01T14:00:00",
                             "check_out_planned_utc": "2027-12-03T11:00:00",
                             "number_of_guests": 1,
                             "idempotency_key": idem_key,
                             "created_at_utc": "2020-01-01T00:00:00",  # injected past date
                         },
                         headers={"Authorization": f"Bearer {manager_token}"})
        assert rv.status_code == 201, f"Booking failed: {rv.get_json()}"

        booking = db.session.query(Booking).filter_by(idempotency_key=idem_key).first()
        stored = booking.created_at_utc
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        delta = abs((stored - now).total_seconds())
        assert delta < 60, (
            f"Booking.created_at_utc is {stored.isoformat()} — injected 2020 timestamp stored"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5.9  Concurrent scheduled tasks — two threads running run_daily simultaneously
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentScheduledTasks:
    def test_concurrent_run_daily_design_gap(self, app):
        """
        DESIGN GAP: two run_daily instances — even milliseconds apart — produce
        duplicate JudgeAlerts because run_daily has no idempotency guard.

        True multi-thread test is skipped here: SQLite in-memory uses a single
        shared connection and raises InterfaceError under concurrent access.
        In production (Postgres), two cron instances would each independently
        read the same spoilage data, pass the (absent) dedup check, and both
        INSERT alert rows. The sequential simulation below proves the design gap
        is in the logic, not the threading layer.

        Fix: add _open_exists() check before _fire_alert() in run_daily.
        Same pattern as check_alerts() already uses. Do NOT fix here — report only.
        """
        from app.judge.engine import run_daily
        from app.models.inventory_item import InventoryItem
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.models.department import Department
        from app.extensions import db

        dept  = db.session.query(Department).filter_by(name="General").first()
        owner = db.session.query(User).filter_by(username="owner1").first()

        item = InventoryItem(name="Concurrent Watch Item", unit="kg",
                             reorder_level=Decimal("2"), is_watch_list=True,
                             department_id=dept.id)
        db.session.add(item)
        db.session.flush()
        db.session.add(StockMovement(
            item_id=item.id, change_amount=Decimal("100"),
            reason=MovementReason.PURCHASE.value, actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.add(StockMovement(
            item_id=item.id, change_amount=Decimal("-20"),  # > SPIKE_THRESHOLD
            reason=MovementReason.SPOILAGE.value, actor_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        ))
        db.session.commit()

        today = datetime.now(timezone.utc)

        # Simulate two cron instances running back-to-back (or simultaneously in Postgres)
        run_daily(today)
        db.session.commit()
        run_daily(today)
        db.session.commit()

        alert_count = db.session.query(JudgeAlert).filter_by(
            alert_type="SPOILAGE_SPIKE", item_id=item.id
        ).count()

        assert alert_count == 1, (
            f"DESIGN GAP: two run_daily calls produced {alert_count} SPOILAGE_SPIKE "
            f"alerts instead of 1. In production with Postgres, two concurrent cron "
            "instances would both INSERT duplicate alerts. "
            "Fix: add _open_exists() check in run_daily."
        )
