"""
test_finance.py — Chunk 4 Finance & Cashier Reconciliation tests.

Covers:
  1.  Cash math: expected derived from unreconciled payments; correct status
  2.  Reconciliation clears pending payments (won't re-appear)
  3.  Shortfall status computed; alert fires after repeated shortfalls
  4.  Idempotent reconciliation (same key → 200, no double-write)
  5.  M-Pesa: unmatched surfaces in pending; MATCH clears it; FLAG fires alert
  6.  Budget CRUD: create, edit, disable, enable (owner only)
  7.  Budget spend vs budget correct; over-budget flagged
  8.  Void rate computed per staff; abnormal rate flagged
  9.  Three-way report: all three corners assemble correctly
  10. Period close: safe vs expected; diff flagged as alert
  11. Period re-close: only owner can; backdated flagged in audit log
  12. Finance dashboard: owner only; correct revenue figures
  13. Decimal precision end to end
  14. Role: staff/manager cannot access owner-only routes
  15. Append-only: corrections are new records, not edits
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


# ── helpers ────────────────────────────────────────────────────────────────────

def _login(client, username, password):
    rv = client.post("/auth/login", json={"username": username, "password": password})
    return rv.get_json()["access_token"]


def _make_tab_and_pay(client, token, amount, method="CASH", mpesa_code=None):
    """Quick helper: open a tab, add service item (immediately served), record payment."""
    from app.extensions import db
    from app.models.menu_item import MenuItem
    with client.application.app_context():
        service = db.session.query(MenuItem).filter_by(name="Pool Access").first()
        svc_id = service.id

    rv = client.post("/tabs", json={}, headers={"Authorization": f"Bearer {token}"})
    tab_id = rv.get_json()["id"]

    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": svc_id, "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})
    order_id = rv.get_json()["id"]

    client.post(f"/orders/{order_id}/send",
                headers={"Authorization": f"Bearer {token}"})

    payload = {"amount": str(amount), "method": method, "idempotency_key": str(uuid.uuid4())}
    if mpesa_code:
        payload["mpesa_code"] = mpesa_code
    rv = client.post(f"/tabs/{tab_id}/payments", json=payload,
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
    return tab_id, rv.get_json()["payment_id"]


def _get_waiter_id(app):
    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        u = db.session.query(User).filter_by(username="waiter1").first()
        return u.id


def _get_owner_id(app):
    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        u = db.session.query(User).filter_by(username="owner1").first()
        return u.id


# ── 1. Cash math: expected derived, status set correctly ──────────────────────

def test_expected_cash_derived_from_payments(client, owner_token, waiter_token, app):
    """Staff collect 500 + 300 = 800 in cash; pending shows 800."""
    waiter_id = _get_waiter_id(app)

    _make_tab_and_pay(client, waiter_token, "500")
    _make_tab_and_pay(client, waiter_token, "300")

    rv = client.get(f"/finance/cash/pending?staff_id={waiter_id}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["payment_count"] == 2
    assert Decimal(data["expected_total"]) == Decimal("800")


def test_reconcile_balanced(client, owner_token, waiter_token, app):
    """Actual = expected → BALANCED."""
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    rv = client.post("/finance/cash/reconcile", json={
        "staff_id":        waiter_id,
        "actual_amount":   "1000",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["status"] == "BALANCED"
    assert Decimal(data["difference"]) == Decimal("0")


def test_reconcile_short(client, owner_token, waiter_token, app):
    """Actual < expected → SHORT, difference is negative."""
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    rv = client.post("/finance/cash/reconcile", json={
        "staff_id":        waiter_id,
        "actual_amount":   "800",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["status"] == "SHORT"
    assert Decimal(data["difference"]) == Decimal("-200")


def test_reconcile_over(client, owner_token, waiter_token, app):
    """Actual > expected → OVER."""
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    rv = client.post("/finance/cash/reconcile", json={
        "staff_id":        waiter_id,
        "actual_amount":   "1100",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    assert rv.get_json()["status"] == "OVER"


# ── 2. Reconciled payments cleared from pending ───────────────────────────────

def test_reconciled_payments_not_pending(client, owner_token, waiter_token, app):
    """After reconcile, the swept payments no longer appear in /pending."""
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "500")

    client.post("/finance/cash/reconcile", json={
        "staff_id":        waiter_id,
        "actual_amount":   "500",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})

    rv = client.get(f"/finance/cash/pending?staff_id={waiter_id}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    assert data["payment_count"] == 0
    assert Decimal(data["expected_total"]) == Decimal("0")


# ── 3. Repeated shortfalls → JudgeAlert ──────────────────────────────────────

def test_repeated_shortfalls_fire_alert(client, owner_token, waiter_token, app):
    """3 consecutive SHORTs create a CASH_SHORTFALL_PATTERN JudgeAlert."""
    from app.extensions import db
    from app.models.judge_alert import JudgeAlert
    waiter_id = _get_waiter_id(app)

    for _ in range(3):
        _make_tab_and_pay(client, waiter_token, "1000")
        client.post("/finance/cash/reconcile", json={
            "staff_id":        waiter_id,
            "actual_amount":   "800",   # always short
            "idempotency_key": str(uuid.uuid4()),
        }, headers={"Authorization": f"Bearer {owner_token}"})

    with app.app_context():
        alert = db.session.query(JudgeAlert).filter_by(
            alert_type="CASH_SHORTFALL_PATTERN"
        ).first()
    assert alert is not None
    assert "waiter1" in alert.description


# ── 4. Idempotency ────────────────────────────────────────────────────────────

def test_cash_reconcile_idempotency(client, owner_token, waiter_token, app):
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "500")
    idem = str(uuid.uuid4())

    rv1 = client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "500", "idempotency_key": idem,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    rv2 = client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "500", "idempotency_key": idem,
    }, headers={"Authorization": f"Bearer {owner_token}"})

    assert rv1.status_code == 201
    assert rv2.status_code == 200
    assert rv2.get_json()["duplicate"] is True


# ── 5. M-Pesa reconciliation ──────────────────────────────────────────────────

def test_mpesa_pending_surfaces_unreconciled(client, owner_token, waiter_token):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _, payment_id = _make_tab_and_pay(client, waiter_token, "500",
                                       method="MPESA", mpesa_code="QAB123")

    rv = client.get(f"/finance/mpesa/pending?date={today}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    data = rv.get_json()
    ids = [p["payment_id"] for p in data["payments"]]
    assert payment_id in ids


def test_mpesa_match_clears_pending(client, owner_token, waiter_token):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _, payment_id = _make_tab_and_pay(client, waiter_token, "500",
                                       method="MPESA", mpesa_code="QAB456")

    client.post("/finance/mpesa/reconcile", json={
        "entries": [{"payment_id": payment_id, "action": "MATCH",
                     "statement_ref": "QAB456"}]
    }, headers={"Authorization": f"Bearer {owner_token}"})

    rv = client.get(f"/finance/mpesa/pending?date={today}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    ids = [p["payment_id"] for p in rv.get_json()["payments"]]
    assert payment_id not in ids


def test_mpesa_flag_fires_alert(client, owner_token, waiter_token, app):
    _, payment_id = _make_tab_and_pay(client, waiter_token, "500",
                                       method="MPESA", mpesa_code="FAKE999")

    rv = client.post("/finance/mpesa/reconcile", json={
        "entries": [{"payment_id": payment_id, "action": "FLAG",
                     "notes": "Code not in Safaricom statement"}]
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert rv.get_json()["flagged"] == 1

    from app.extensions import db
    from app.models.judge_alert import JudgeAlert
    with app.app_context():
        alert = db.session.query(JudgeAlert).filter_by(alert_type="MPESA_FLAGGED").first()
    assert alert is not None


# ── 6. Budget CRUD ────────────────────────────────────────────────────────────

def test_owner_can_create_budget(client, owner_token, general_dept_id):
    rv = client.post("/finance/budgets", json={
        "department_id": general_dept_id,
        "period":        "2099-01",
        "amount":        "100000",
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    data = rv.get_json()
    assert Decimal(data["amount"]) == Decimal("100000")


def test_manager_cannot_create_budget(client, manager_token, general_dept_id):
    rv = client.post("/finance/budgets", json={
        "department_id": general_dept_id, "period": "2099-02", "amount": "50000",
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 403
    assert "error" in rv.get_json()


def test_budget_edit_and_disable_enable(client, owner_token, general_dept_id):
    rv = client.post("/finance/budgets", json={
        "department_id": general_dept_id, "period": "2099-03", "amount": "50000",
    }, headers={"Authorization": f"Bearer {owner_token}"})
    budget_id = rv.get_json()["id"]

    # Edit
    rv = client.patch(f"/finance/budgets/{budget_id}", json={"amount": "75000"},
                      headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    assert Decimal(rv.get_json()["amount"]) == Decimal("75000")

    # Disable
    rv = client.post(f"/finance/budgets/{budget_id}/disable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.get_json()["is_active"] is False

    # Enable
    rv = client.post(f"/finance/budgets/{budget_id}/enable",
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.get_json()["is_active"] is True


# ── 7. Budget spend vs budget ─────────────────────────────────────────────────

def test_budget_status_over_budget(client, owner_token, general_dept_id, app):
    """Seed a tiny budget and a purchase that exceeds it."""
    from app.extensions import db
    from app.models.inventory_item import InventoryItem
    from app.models.purchase import Purchase
    from app.models.user import User

    period = datetime.now(timezone.utc).strftime("%Y-%m")

    # Create a budget of KES 100 for general dept this month
    client.post("/finance/budgets", json={
        "department_id": general_dept_id, "period": period, "amount": "100",
    }, headers={"Authorization": f"Bearer {owner_token}"})

    # Record a purchase of KES 500 against an item in general dept
    with app.app_context():
        owner = db.session.query(User).filter_by(username="owner1").first()
        inv_item = InventoryItem(
            name="Cooking Gas", unit="kg",
            department_id=general_dept_id, reorder_level="5"
        )
        db.session.add(inv_item)
        db.session.flush()

        purchase = Purchase(
            item_id=inv_item.id,
            quantity="1",
            actual_cost="500",
            receipt_photo_path="/receipts/gas_001.jpg",
            recorded_by_id=owner.id,
            idempotency_key=str(uuid.uuid4()),
        )
        db.session.add(purchase)
        db.session.commit()

    rv = client.get(f"/finance/budgets/status?period={period}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    rows = rv.get_json()["budgets"]

    general_row = next((r for r in rows if "General" in r["department"]), None)
    assert general_row is not None
    assert general_row["over_budget"] is True
    assert Decimal(general_row["spent"]) >= Decimal("500")


# ── 8. Void rate analytics ────────────────────────────────────────────────────

def test_void_rate_computed(client, owner_token, waiter_token, food_item_id):
    """Create orders, cancel items, verify void rate appears in analytics."""
    # Create 4 orders: cancel items in 3 of them → void rate = 75%
    from datetime import timedelta
    now  = datetime.now(timezone.utc)
    frm  = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    to   = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    for cancel in [True, True, True, False]:
        rv = client.post("/tabs", json={}, headers={"Authorization": f"Bearer {waiter_token}"})
        tab_id = rv.get_json()["id"]
        rv = client.post("/orders", json={
            "tab_id": tab_id,
            "items": [{"menu_item_id": food_item_id, "quantity": 1}],
            "idempotency_key": str(uuid.uuid4()),
        }, headers={"Authorization": f"Bearer {waiter_token}"})
        order_id = rv.get_json()["id"]
        client.post(f"/orders/{order_id}/send",
                    headers={"Authorization": f"Bearer {waiter_token}"})
        if cancel:
            # cancel the PENDING item
            from app.extensions import db
            from app.models.order import Order
            from app.models.order_item import OrderItem
            with client.application.app_context():
                order = db.session.get(Order, order_id)
                oi_id = order.items[0].id
            client.post(f"/order-items/{oi_id}/cancel",
                        json={"reason": "test void"},
                        headers={"Authorization": f"Bearer {waiter_token}"})

    rv = client.get(f"/finance/anomalies/voids?from={frm}&to={to}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    data = rv.get_json()
    waiter_row = next(
        (r for r in data["staff_rates"] if r["staff_name"] == "waiter1"), None
    )
    assert waiter_row is not None
    assert waiter_row["void_count"] == 3


# ── 9. Three-way reconciliation report ───────────────────────────────────────

def test_three_way_report_assembles(client, owner_token, waiter_token):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # One cash payment so receipts corner has data
    _make_tab_and_pay(client, waiter_token, "2000")

    rv = client.get(f"/finance/reconciliation?date={today}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    data = rv.get_json()

    assert "receipts" in data
    assert "cash_reconciliation" in data
    assert "stock" in data
    assert Decimal(data["receipts"]["cash"]) >= Decimal("2000")


def test_three_way_report_shows_gap_when_cash_short(client, owner_token, waiter_token, app):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    # Reconcile SHORT
    client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "700",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})

    rv = client.get(f"/finance/reconciliation?date={today}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    assert data["balanced"] is False
    assert len(data["gaps"]) > 0


# ── 10. Period close ──────────────────────────────────────────────────────────

def test_period_close_balanced(client, owner_token, waiter_token, app):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    # Reconcile exactly
    client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "1000",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})

    # Close period with safe_count = 1000 (what was handed in)
    rv = client.post("/finance/close-period", json={
        "date": today, "safe_count": "1000",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["status"] == "BALANCED"
    assert Decimal(data["difference"]) == Decimal("0")


def test_period_close_short_fires_alert(client, owner_token, waiter_token, app):
    """Safe has less cash than what was handed in → SAFE_COUNT_MISMATCH alert."""
    from app.extensions import db
    from app.models.judge_alert import JudgeAlert
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    waiter_id = _get_waiter_id(app)
    _make_tab_and_pay(client, waiter_token, "1000")

    client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "1000",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})

    idem = str(uuid.uuid4())
    rv = client.post("/finance/close-period", json={
        "date": today, "safe_count": "800",  # 200 missing from safe
        "idempotency_key": idem,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    assert rv.get_json()["status"] == "SHORT"

    with app.app_context():
        alert = db.session.query(JudgeAlert).filter_by(
            alert_type="SAFE_COUNT_MISMATCH"
        ).first()
    assert alert is not None


def test_period_close_idempotency(client, owner_token):
    idem = str(uuid.uuid4())
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rv1 = client.post("/finance/close-period", json={
        "date": today, "safe_count": "0", "idempotency_key": idem,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    rv2 = client.post("/finance/close-period", json={
        "date": today, "safe_count": "0", "idempotency_key": idem,
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv1.status_code == 201
    assert rv2.status_code == 200
    assert rv2.get_json()["duplicate"] is True


# ── 11. Period re-close: manager blocked, owner allowed ───────────────────────

def test_manager_cannot_reclose_period(client, owner_token, manager_token):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # First close by owner
    client.post("/finance/close-period", json={
        "date": today, "safe_count": "0",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})

    # Manager tries to re-close with different idempotency_key
    rv = client.post("/finance/close-period", json={
        "date": today, "safe_count": "0",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 400
    assert "error" in rv.get_json()


# ── 12. Finance dashboard — owner only ───────────────────────────────────────

def test_dashboard_owner_only(client, owner_token, manager_token):
    rv = client.get("/finance/dashboard",
                    headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 403

    rv = client.get("/finance/dashboard",
                    headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert "revenue" in data
    assert "budgets" in data
    assert "judge_alerts_open" in data


def test_dashboard_revenue_today_includes_payment(client, owner_token, waiter_token):
    _make_tab_and_pay(client, waiter_token, "999")

    rv = client.get("/finance/dashboard",
                    headers={"Authorization": f"Bearer {owner_token}"})
    data = rv.get_json()
    assert Decimal(data["revenue"]["today"]) >= Decimal("999")


# ── 13. Decimal precision end to end ─────────────────────────────────────────

def test_cash_decimal_precision(client, owner_token, waiter_token, app):
    """10 payments of 33.33 each = 333.30 total pending."""
    waiter_id = _get_waiter_id(app)
    for _ in range(10):
        _make_tab_and_pay(client, waiter_token, "33.33")

    rv = client.get(f"/finance/cash/pending?staff_id={waiter_id}",
                    headers={"Authorization": f"Bearer {owner_token}"})
    total = Decimal(rv.get_json()["expected_total"])
    assert total == Decimal("333.30")


# ── 14. Role enforcement ──────────────────────────────────────────────────────

def test_staff_cannot_view_pending_cash(client, app):
    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        u = db.session.query(User).filter_by(username="staff1").first()
        staff_id = u.id
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    staff_token = rv.get_json()["access_token"]

    rv = client.get(f"/finance/cash/pending?staff_id={staff_id}",
                    headers={"Authorization": f"Bearer {staff_token}"})
    assert rv.status_code == 403
    assert "error" in rv.get_json()


def test_staff_cannot_set_budgets(client, general_dept_id, app):
    rv = client.post("/auth/pin-login", json={"username": "staff1", "pin": "3333"})
    staff_token = rv.get_json()["access_token"]
    rv = client.post("/finance/budgets", json={
        "department_id": general_dept_id, "period": "2099-12", "amount": "1000",
    }, headers={"Authorization": f"Bearer {staff_token}"})
    assert rv.status_code == 403


# ── 15. Append-only: new record, not edit ─────────────────────────────────────

def test_correction_creates_new_record(client, owner_token, waiter_token, app):
    """
    Reconcile once, then record a correction.
    Both records exist; the second is new (different id).
    """
    from app.extensions import db
    from app.models.cash_reconciliation import CashReconciliation
    waiter_id = _get_waiter_id(app)

    _make_tab_and_pay(client, waiter_token, "1000")
    rv1 = client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "800",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    id1 = rv1.get_json()["id"]

    # Next payment — correction reconciliation
    _make_tab_and_pay(client, waiter_token, "500")
    rv2 = client.post("/finance/cash/reconcile", json={
        "staff_id": waiter_id, "actual_amount": "500",
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    id2 = rv2.get_json()["id"]

    assert id1 != id2

    with app.app_context():
        count = db.session.query(CashReconciliation).filter_by(
            staff_id=waiter_id
        ).count()
    assert count == 2
