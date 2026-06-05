"""
tests/test_security_category_6.py — Category 6: Human Attacks & Collusion

Scenario analysis (pre-run predictions):

6.1  PASS    — Payments are structurally append-only; no void/delete endpoint exists;
               SERVED order items are terminal; state machine blocks retroactive cancellation.

6.2  PARTIAL — Silent judge catches consumption-to-revenue ratio deviations and spoilage
               spikes. Gap: a pure off-books transaction that enters no stock movement
               and no order is undetectable. Accepted residual risk.

6.3  PARTIAL — PIN setup requires a short-lived password-login token (requires_pin_setup
               claim). PIN change requires the current PIN. Both actions audit-logged.
               Gap: a junior who willingly shares their PIN is undetectable.

6.4  PARTIAL — DEPLOY.md and backup CLI exist. Audit chain is hash-verifiable.
               Gap: key-person departure and standby-PC swap procedures are thin.

6.5  PARTIAL — Gate reconciliation detects revenue ≠ bands×fee and headcount > bands.
               Gap: a friend who enters, uses no chargeable service, and leaves is
               undetectable without physical cameras + headcount discipline.

6.6  PARTIAL — All manager overrides are audit-logged. OWNER_PRIVATE suggestions and
               is_owner_only disputes are structurally invisible to managers (query-layer).
               Gap: a junior who never uses the escape valve cannot be helped by code.
"""
import uuid
import os
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 6.1  Manager-cashier collusion — void-and-pocket
# ══════════════════════════════════════════════════════════════════════════════

class TestVoidAndPocketCollusion:
    def test_no_payment_delete_or_void_endpoint(self, client, manager_token, app):
        """
        ATTACK: Manager voids a recorded payment after cash was pocketed.
        DEFENCE: No DELETE or PATCH endpoint exists on payments. The only
                 payment endpoint is POST /<tab_id>/payments (append-only).
        Verify: DELETE returns 405 (method not allowed) — the route simply
                does not exist, so Flask returns 404 or 405.
        """
        from app.models.tab import Tab, TabType, TabStatus
        from app.models.user import User
        from app.models.payment import Payment, PaymentMethod
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()
        tab = Tab(tab_type=TabType.WALK_IN.value, reference="Void Attack Tab",
                  opened_by_id=owner.id, status=TabStatus.OPEN.value)
        db.session.add(tab)
        db.session.flush()
        payment = Payment(
            tab_id=tab.id, amount=Decimal("500"),
            method=PaymentMethod.CASH.value,
            received_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(payment)
        db.session.commit()

        # Attempt to DELETE the payment
        rv = client.delete(f"/tabs/{tab.id}/payments/{payment.id}",
                           headers=auth(manager_token))
        assert rv.status_code in (404, 405), (
            f"DELETE on a payment returned {rv.status_code} — "
            "payments must be append-only with no delete route."
        )

        # Attempt to PATCH the payment amount (retroactive edit)
        rv = client.patch(f"/tabs/{tab.id}/payments/{payment.id}",
                          json={"amount": "0"},
                          headers=auth(manager_token))
        assert rv.status_code in (404, 405), (
            f"PATCH on a payment returned {rv.status_code} — "
            "payment amounts must be frozen at write time."
        )

    def test_payment_model_has_no_soft_delete_columns(self, app):
        """
        Structural: Payment model has no is_voided, is_active, or cancelled_at column.
        Append-only is enforced at the schema level — no toggle to hide a payment.
        """
        from app.models.payment import Payment
        columns = {c.name for c in Payment.__table__.columns}
        for forbidden in ("is_voided", "is_active", "cancelled_at", "voided_at", "deleted_at"):
            assert forbidden not in columns, (
                f"Payment model has a '{forbidden}' column — this creates a payment-void path. "
                "Payments must be append-only with no soft-delete mechanism."
            )

    def test_served_order_item_cannot_be_retroactively_cancelled(self, app):
        """
        SERVED is a terminal state. State machine blocks any attempt to cancel
        it — even by a manager. Verified at the transition dict level.
        (Complements Cat 1 1.2 which tests the API response.)
        """
        from app.models.order_item import VALID_TRANSITIONS, OrderItemStatus
        served_transitions = VALID_TRANSITIONS.get(OrderItemStatus.SERVED, set())
        assert len(served_transitions) == 0, (
            f"SERVED has valid next transitions: {served_transitions}. "
            "It must be terminal — no route to CANCELLED."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.2  Off-books sale — silent judge detection paths
# ══════════════════════════════════════════════════════════════════════════════

class TestOffBooksSaleDetection:
    def test_consumption_ratio_baseline_detection_wired(self, app):
        """
        ATTACK: Bartender serves drinks, pockets cash, never enters into system.
        DEFENCE: run_weekly() computes consumption/revenue ratio per inventory item.
                 If consumption exceeds the baseline tolerance, a RATIO alert fires.
        Verify: with a tight baseline and high spoilage logged, run_weekly fires an alert.
        (Detection path exists and reaches the JudgeAlert table.)
        """
        from app.judge.engine import run_weekly
        from app.models.inventory_item import InventoryItem
        from app.models.judge_baseline import JudgeBaseline
        from app.models.stock_movement import StockMovement, MovementReason
        from app.models.payment import Payment, PaymentMethod
        from app.models.judge_alert import JudgeAlert
        from app.models.user import User
        from app.extensions import db

        owner = db.session.query(User).filter_by(username="owner1").first()

        # Inventory item with a tight baseline
        item = InventoryItem(
            name="OffBooks Whisky", unit="cl", department_id=owner.department_id,
            is_active=True, is_staff_food=False, is_watch_list=True,
            reorder_level="0",
        )
        db.session.add(item)
        db.session.flush()

        # Baseline: 1 cl per 100 KSh revenue, 10% tolerance (very tight)
        baseline = JudgeBaseline(
            item_id=item.id, business_driver="restaurant_revenue",
            expected_ratio=Decimal("100"),   # 100 cl per 10,000 KSh
            driver_unit="cl", tolerance_percent=Decimal("10"),
        )
        db.session.add(baseline)

        # Record 500 KSh in payments (low revenue)
        payment = Payment(
            amount=Decimal("500"), method=PaymentMethod.CASH.value,
            received_by_id=owner.id, idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(payment)

        now = datetime.now(timezone.utc)
        # Record massive consumption — 1000 cl consumed vs ~5 cl expected (500/10000×100)
        movement = StockMovement(
            item_id=item.id, change_amount=Decimal("-1000"),
            reason=MovementReason.SALE_PLACEHOLDER.value,
            actor_id=owner.id, idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(movement)
        db.session.commit()

        period_start = now - timedelta(days=1)
        period_end   = now + timedelta(hours=1)

        alerts_before = db.session.query(JudgeAlert).filter_by(
            alert_type="RATIO", item_id=item.id
        ).count()

        fired = run_weekly(period_start, period_end)

        assert fired >= 1, (
            "run_weekly should fire a RATIO alert when consumption massively exceeds "
            "the expected ratio. Detection path is broken."
        )
        alerts_after = db.session.query(JudgeAlert).filter_by(
            alert_type="RATIO", item_id=item.id
        ).count()
        assert alerts_after > alerts_before, "RATIO JudgeAlert must be written to DB"

    def test_pure_off_books_zero_trace_is_documented_gap(self):
        """
        ACCEPTED GAP: If a bartender serves a drink from stock that was never
        entered into the inventory system, there is zero trace. The judge can
        only detect anomalies in data that was entered. A sale that bypasses
        data entry entirely is invisible to the system.
        Human control required: unannounced owner stock counts, bar spot-checks.
        """
        gap_acknowledged = True
        assert gap_acknowledged, (
            "Pure off-books sales with no inventory trace are undetectable by code. "
            "Mitigation: unannounced owner stock audits at irregular intervals."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.3  PIN social engineering
# ══════════════════════════════════════════════════════════════════════════════

class TestPINSocialEngineering:
    def test_pin_setup_rejected_without_setup_claim(self, client, manager_token):
        """
        ATTACK: Senior staff obtains a junior's credentials and tries to reset
                their PIN using a normal JWT (not the short-lived setup token).
        DEFENCE: POST /auth/set-pin checks for requires_pin_setup claim in JWT.
                 A normal manager token lacks this claim → 400.
        """
        rv = client.post("/auth/set-pin",
                         json={"pin": "9999"},
                         headers=auth(manager_token))
        assert rv.status_code == 400, (
            f"set-pin with a normal JWT returned {rv.status_code}. "
            "It must require the requires_pin_setup claim from password login."
        )
        assert "error" in rv.get_json()

    def test_change_pin_wrong_current_pin_rejected(self, client, manager_token):
        """
        ATTACK: Someone who knows the username tries to change a PIN without
                knowing the current one (shoulder-surf partial — saw pin once).
        DEFENCE: POST /auth/change-pin requires correct current_pin → 401 if wrong.
        """
        rv = client.post("/auth/change-pin",
                         json={"current_pin": "0000", "new_pin": "9999"},
                         headers=auth(manager_token))
        assert rv.status_code == 401, (
            f"change-pin with wrong current_pin returned {rv.status_code}. "
            "Must reject wrong current PIN."
        )
        assert "error" in rv.get_json()

    def test_change_pin_writes_audit_log(self, client, app):
        """
        PIN changes are audit-logged so the owner can spot unexpected PIN
        rotations — a signal that a PIN was shared and then changed.
        """
        from app.models.audit_log import AuditLog
        from app.extensions import db

        # Log in as manager (password known), get a token
        rv = client.post("/auth/login",
                         json={"username": "manager1", "password": "ManagerPass1!"})
        assert rv.status_code == 200
        token = rv.get_json()["access_token"]

        before = db.session.query(AuditLog).filter_by(action="pin.changed").count()

        rv = client.post("/auth/change-pin",
                         json={"current_pin": "2222", "new_pin": "8888"},
                         headers=auth(token))
        assert rv.status_code == 200, f"change-pin failed: {rv.get_json()}"

        after = db.session.query(AuditLog).filter_by(action="pin.changed").count()
        assert after == before + 1, "PIN change must write an audit log entry"

        # Restore PIN for other tests
        rv = client.post("/auth/change-pin",
                         json={"current_pin": "8888", "new_pin": "2222"},
                         headers=auth(token))
        assert rv.status_code == 200

    def test_willing_pin_sharing_is_undetectable_gap(self):
        """
        ACCEPTED GAP: If a junior willingly tells their PIN to a senior, there
        is no technical signal — both actors authenticate as the junior. The
        system cannot distinguish a shared credential from the real user.
        Human control: separate accounts, zero-tolerance PIN-sharing policy,
        audit log spot-checks for unusual login times/locations.
        """
        gap_acknowledged = True
        assert gap_acknowledged, (
            "Willing PIN sharing is a social engineering gap that code cannot close. "
            "Mitigation: strict account-per-person policy, regular audit log reviews."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.4  Owner disaster scenarios
# ══════════════════════════════════════════════════════════════════════════════

class TestOwnerDisasterScenarios:
    def test_deploy_md_exists_and_has_content(self):
        """
        DEPLOY.md is the owner's operational runbook. Its existence is a
        minimum bar — if it's missing, the system has no documented recovery path.
        """
        deploy_path = os.path.join(os.path.dirname(__file__), "..", "DEPLOY.md")
        assert os.path.exists(deploy_path), "DEPLOY.md must exist"
        content = open(deploy_path).read()
        assert len(content) > 200, "DEPLOY.md appears empty or too short to be useful"
        # Must mention backup
        assert "backup" in content.lower(), "DEPLOY.md must document backup procedure"

    def test_audit_chain_is_hash_verifiable(self, app):
        """
        The audit log is hash-chained. Even if an attacker gains DB access,
        any row deletion or edit breaks the chain — detectable by verify_chain().
        Verify the chain is intact after the test suite's writes.
        """
        from app.models.audit_log import AuditLog
        ok, message = AuditLog.verify_chain()
        assert ok, f"Audit chain integrity check failed: {message}"

    def test_key_person_runbook_gap_is_documented(self):
        """
        ACCEPTED GAP: DEPLOY.md documents server operations but does not
        currently cover: manager quits without handover, standby PC swap,
        or owner unavailable for days. These are procedural gaps, not code gaps.
        Human control: HUMAN_THREATS.md owner checklist covers these scenarios.
        """
        gap_acknowledged = True
        assert gap_acknowledged, (
            "Key-person departure and hardware-swap procedures need a written owner checklist. "
            "See HUMAN_THREATS.md — Owner Checklist section."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.5  Gate "friend let in free"
# ══════════════════════════════════════════════════════════════════════════════

class TestGateFriendLetIn:
    def test_gate_reconciliation_detects_revenue_mismatch(self, app):
        """
        ATTACK: Gate staff issues a band but accepts less than the entry fee
                (or logs a reduced payment for a friend).
        DEFENCE: get_reconciliation() computes bands_issued × ENTRY_FEE vs
                 sum(entry_payments). A discrepancy sets mismatch=True.
        """
        from app.models.wristband import Wristband, WristbandStatus
        from app.models.payment import Payment, PaymentMethod
        from app.models.user import User
        from app.services.gate import ENTRY_FEE, get_reconciliation
        from app.extensions import db

        from app.models.tab import Tab, TabType, TabStatus
        owner = db.session.query(User).filter_by(username="owner1").first()
        today = datetime.now(timezone.utc).date().isoformat()

        # A wristband needs a tab — create a minimal one
        tab = Tab(tab_type=TabType.WALK_IN.value, reference=f"band-recon-test-{uuid.uuid4()}",
                  opened_by_id=owner.id, status=TabStatus.OPEN.value)
        db.session.add(tab)
        db.session.flush()

        # Create an entry payment with LESS than the full ENTRY_FEE
        reduced_payment = Payment(
            tab_id=tab.id,
            amount=Decimal("500"),           # should be 3000 — friend discount
            method=PaymentMethod.CASH.value,
            received_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(reduced_payment)
        db.session.flush()

        # Create a wristband linked to the reduced payment
        band = Wristband(
            band_number=9001,
            issue_date=today,
            issued_by_id=owner.id,
            entry_payment_id=reduced_payment.id,
            tab_id=tab.id,
            status=WristbandStatus.ACTIVE.value,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(band)
        db.session.commit()

        recon = get_reconciliation(today)
        assert recon["mismatch"] is True, (
            f"Expected mismatch=True (500 collected vs {ENTRY_FEE} expected) "
            f"but got: {recon}"
        )
        assert Decimal(recon["gate_revenue"]) < Decimal(recon["expected_revenue"]), (
            "Gate revenue should be less than expected when a friend discount was given."
        )

    def test_headcount_mismatch_flags_excess_guests(self, app, client, manager_token):
        """
        ATTACK: Gate staff lets extra people through after recording headcount,
                or physical count shows more people than bands issued.
        DEFENCE: If recorded headcount > bands issued, headcount_mismatch=True
                 in the reconciliation response.
        """
        from app.services.gate import get_reconciliation
        from app.models.gate_headcount import GateHeadcount
        from app.extensions import db

        today = datetime.now(timezone.utc).date().isoformat()

        # Record a headcount HIGHER than any bands issued today
        # (we're not issuing real bands — the discrepancy is the point)
        hc = db.session.query(GateHeadcount).filter_by(count_date=today).first()
        if hc:
            hc.counted = 9999
        else:
            from app.models.user import User
            owner = db.session.query(User).filter_by(username="owner1").first()
            hc = GateHeadcount(count_date=today, counted=9999,
                               recorded_by_id=owner.id)
            db.session.add(hc)
        db.session.commit()

        recon = get_reconciliation(today)
        assert recon["headcount_mismatch"] is True, (
            f"Expected headcount_mismatch=True (9999 counted vs "
            f"{recon['bands_issued']} bands issued) but got: {recon}"
        )

    def test_ghost_guest_with_no_service_is_documented_gap(self):
        """
        ACCEPTED GAP: A friend who enters the resort, sits by the pool, consumes
        nothing chargeable, and leaves is completely invisible to the system.
        The wristband-for-everything defence only works for guests who USE services.
        Human control: camera coverage at gate, random manager headcount walks,
        consistent physical counting discipline.
        """
        gap_acknowledged = True
        assert gap_acknowledged, (
            "Guests who use no chargeable service leave zero system trace. "
            "Mitigation: gate camera, consistent physical headcounts, spot audits."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.6  Senior coercing junior
# ══════════════════════════════════════════════════════════════════════════════

class TestSeniorCoercingJunior:
    def test_owner_private_suggestion_invisible_to_manager(
            self, client, owner_token, manager_token):
        """
        ATTACK: Manager pressures a junior. Junior wants to report it to the
                owner but fears the manager will see and retaliate.
        DEFENCE: OWNER_PRIVATE suggestions are filtered at the query layer —
                 managers get only MANAGEMENT suggestions. The row simply does
                 not appear for them.
        """
        # Submit an OWNER_PRIVATE suggestion (anonymous — junior protecting themselves)
        rv = client.post("/suggestions",
                         json={
                             "subject": "Manager misconduct",
                             "body": "Manager asked me to skip the reconciliation check",
                             "category": "OWNER_PRIVATE",
                             "anonymous": True,
                             "idempotency_key": str(uuid.uuid4()),
                         },
                         headers=auth(owner_token))
        assert rv.status_code == 201
        suggestion_id = rv.get_json()["id"]

        # Manager lists suggestions — must NOT see the OWNER_PRIVATE one
        rv = client.get("/suggestions", headers=auth(manager_token))
        assert rv.status_code == 200
        ids = [s["id"] for s in rv.get_json()]
        assert suggestion_id not in ids, (
            "OWNER_PRIVATE suggestion is visible to a manager — "
            "the query-layer filter is broken."
        )

        # Owner CAN see it
        rv = client.get("/suggestions", headers=auth(owner_token))
        assert rv.status_code == 200
        ids = [s["id"] for s in rv.get_json()]
        assert suggestion_id in ids, "Owner must be able to see OWNER_PRIVATE suggestions"

    def test_owner_only_dispute_invisible_to_manager(
            self, client, waiter_token, owner_token, manager_token, waiter_profile):
        """
        ATTACK: Junior files a formal dispute against a manager.
                Manager learns about it and retaliates.
        DEFENCE: is_owner_only disputes are filtered at query layer — manager
                 cannot list or find them.
        waiter_profile fixture ensures the waiter has an employee profile
        (required by the dispute endpoint).
        """
        # File an owner-only dispute as the junior (waiter has an employee profile)
        rv = client.post("/disputes",
                         json={
                             "description": "On 2026-06-01 the manager told me to skip reconciliation",
                             "category": "CONDUCT_VIOLATION",
                             "is_owner_only": True,
                             "idempotency_key": str(uuid.uuid4()),
                         },
                         headers=auth(waiter_token))
        assert rv.status_code == 201
        dispute_id = rv.get_json()["id"]

        # Manager lists disputes — must NOT see this one
        rv = client.get("/disputes", headers=auth(manager_token))
        assert rv.status_code == 200
        ids = [d["id"] for d in rv.get_json()]
        assert dispute_id not in ids, (
            "is_owner_only dispute is visible to a manager — "
            "the query-layer filter is broken."
        )

        # Owner CAN see it
        rv = client.get("/disputes", headers=auth(owner_token))
        assert rv.status_code == 200
        ids = [d["id"] for d in rv.get_json()]
        assert dispute_id in ids, "Owner must be able to see is_owner_only disputes"

    @pytest.mark.skip(
        reason="Covered by tests/test_security_category_1.py::"
               "TestManualOverrideAbuse::test_override_of_another_writes_audit_log; "
               "kept here for Cat 6 mapping completeness"
    )
    def test_manager_override_leaves_permanent_audit_trail(
            self, client, manager_token, app):
        """
        ATTACK: Manager coerces a waiter to approve something the waiter
                wouldn't normally approve. The act is recorded.
        DEFENCE: Every manual clock override writes an audit log entry with the
                 manager's identity. Override cannot be erased from the chain.
        """
        from app.models.audit_log import AuditLog
        from app.models.employee_profile import EmployeeProfile
        from app.models.user import User
        from app.extensions import db

        # Get a staff member who can be overridden
        waiter = db.session.query(User).filter_by(username="waiter1").first()
        profile = db.session.query(EmployeeProfile).filter_by(
            user_id=waiter.id
        ).first()
        if not profile:
            pytest.skip("No waiter employee profile — create one to test this")

        count_before = db.session.query(AuditLog).filter_by(
            action="hr.manual_override"
        ).count()

        rv = client.post("/hr/clock-events/manual",
                         json={
                             "employee_id": profile.id,
                             "event_type": "CLOCK_IN",
                             "reason": "Coerced test — should appear in audit log",
                             "idempotency_key": str(uuid.uuid4()),
                         },
                         headers=auth(manager_token))
        assert rv.status_code == 201

        count_after = db.session.query(AuditLog).filter_by(
            action="hr.manual_override"
        ).count()
        assert count_after == count_before + 1, (
            "Manual override must write to the audit log — "
            "evidence of coercion must be permanently recorded."
        )

    def test_coercion_without_report_is_documented_gap(self):
        """
        ACCEPTED GAP: If a junior complies with coercion and never files a
                      suggestion or dispute, the system has no signal. The
                      escape valve only works if the junior uses it.
        Human control: anonymous reporting culture, owner direct conversations,
        clear non-retaliation policy visible to all staff.
        """
        gap_acknowledged = True
        assert gap_acknowledged, (
            "Silent coercion is a cultural problem, not a code problem. "
            "Mitigation: anonymous OWNER_PRIVATE channel exists — "
            "owner must actively invite staff to use it."
        )
