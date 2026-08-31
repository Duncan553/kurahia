"""
tests/test_scenarios_money.py — ADVERSARIAL money scenarios.

Domain: payments, charges, tabs, deposits, reconciliation, VAT, refunds,
budgets, cash handling, wristband credit.

This file used to carry twelve `@pytest.mark.xfail(strict=True)` markers, each
one pinning a hole the engineering invariants said should not exist. strict=True
was the whole point: the moment somebody fixed a hole the test started passing,
pytest reported XPASS as a FAILURE, and whoever did the fix was told about it.
A hole could not be quietly closed and forgotten, or quietly reintroduced.

ALL TWELVE ARE NOW CLOSED. Every one of those tests is still here, renamed off
the HOLE_ prefix, with its finding kept in the docstring in past tense. They are
regression cover now: each fails again on the day its hole comes back. Do not
delete them because the bug is gone — the bug being gone is what they guard.

The findings, for anyone reading the history: four endpoints let Decimal('NaN')
reach a comparison and 500; two took no upper bound against a Numeric(14,2)
column; a payment could be recorded sub-cent so the receipt and the ledger
disagreed; a payment idempotency key was matched without its tab, so real cash
could vanish behind a "duplicate" success screen; a refunded item trapped its
tab open forever; a water-session charge had no idempotency key at all; and the
auto-opened tab — most tabs on a busy night — wrote no audit row.

What is left in here is the ordinary kind: a GOOD path that must work, and a
BAD path the system must refuse.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest


def auth(token):
    """Bearer header helper — every endpoint here is JWT-protected."""
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures / helpers
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def villa_resource(app):
    """A bookable VILLA. Local copy of test_bookings.py's `villa` so this file
    stands alone — no cross-file fixture import while other agents edit them."""
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.extensions import db
    r = BookableResource(name="Scenario Villa", resource_type=ResourceType.VILLA.value,
                         base_price="10000", capacity=4)
    db.session.add(r)
    db.session.commit()
    return r


def open_tab_with_charge(client, token, item_id, qty=1):
    """Create an order, send it (which writes the Charge), return (tab_id, order_id).

    Sending is what creates money — a DRAFT order has no Charge rows at all
    (app/pos/orders.py:178), so a test that only creates an order is testing
    nothing about the ledger.
    """
    r = client.post("/orders",
                    json={"items": [{"menu_item_id": item_id, "quantity": qty}]},
                    headers=auth(token))
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    s = client.post(f"/orders/{body['id']}/send", headers=auth(token))
    assert s.status_code == 200, s.get_data(as_text=True)
    return body["tab_id"], body["id"]


def serve_all_items(client, token, order_id, prep_token=None):
    """Walk every item on an order PENDING → RECEIVED → READY → SERVED so the
    tab becomes closable (is_tab_closable refuses while anything is in flight).

    receive and ready are STATION actions: _can_operate_station
    (app/pos/orders.py:41) only lets the item's own department or a manager+ do
    them, so a waiter token is a 403 on both and the item stays PENDING. Pass a
    manager-level `prep_token` for that half — serving stays with `token`,
    which is what really happens: the kitchen cooks, the waiter carries.

    Every step is asserted. Swallowing the responses is how this helper used to
    leave items at PENDING and make later refund tests fail for the wrong
    reason.
    """
    from app.extensions import db
    from app.models.order_item import OrderItem
    prep_token = prep_token or token
    for oi in db.session.query(OrderItem).filter_by(order_id=order_id).all():
        for step, tok in (("receive", prep_token), ("ready", prep_token),
                          ("serve", token)):
            r = client.post(f"/order-items/{oi.id}/{step}", headers=auth(tok))
            assert r.status_code == 200, \
                f"{step} on {oi.id} failed: {r.status_code} {r.get_data(as_text=True)}"


def balance_of(client, token, tab_id):
    """Read the DERIVED balance back through the API as a Decimal."""
    r = client.get(f"/tabs/{tab_id}", headers=auth(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    return Decimal(r.get_json()["balance"])


def checked_in_villa(client, token, villa_resource, phone="+254700900001"):
    """Book → pay the 30% deposit → confirm → check in.
    Returns (booking_id, tab_id). Check-in is what opens the VILLA tab and
    posts the accommodation charge (app/services/booking.py:231)."""
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    r = client.post("/bookings", json={
        "resource_id": villa_resource.id, "guest_name": "Jane Kamau",
        "guest_phone": phone,
        "check_in_planned_utc": ci.isoformat(),
        "check_out_planned_utc": co.isoformat(),
        "number_of_guests": 2,
    }, headers=auth(token))
    assert r.status_code == 201, r.get_data(as_text=True)
    bid = r.get_json()["id"]
    d = client.post("/booking-payments",
                    json={"booking_id": bid, "purpose": "DEPOSIT",
                          "method": "CASH", "amount": "3000"},
                    headers=auth(token))
    assert d.status_code == 201, d.get_data(as_text=True)
    assert client.post(f"/bookings/{bid}/confirm", headers=auth(token)).status_code == 200
    ck = client.post(f"/bookings/{bid}/check-in", headers=auth(token))
    assert ck.status_code == 200, ck.get_data(as_text=True)
    return bid, ck.get_json()["tab_id"]


def sign_water_waiver(client, token, booking_id):
    """The water-session endpoint refuses without an active waiver, so every
    probe of its money handling has to get past this gate first."""
    r = client.post("/waivers", json={"booking_id": booking_id,
                                      "activity_type": "WATER_ACTIVITY",
                                      "signed_by_name": "Jane Kamau"},
                    headers=auth(token))
    assert r.status_code == 201, r.get_data(as_text=True)


def issue_band(client, token):
    """Issue a wristband at the gate. The KSh 3,000 entry fee is written as a
    Payment on the new BAND tab, so the tab starts at -3000 (credit)."""
    r = client.post("/gate/issue-band", json={"method": "CASH"}, headers=auth(token))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["tab_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. The derived-balance invariant
# ═══════════════════════════════════════════════════════════════════════════

def test_balance_is_exactly_charges_minus_payments(client, owner_token, food_item_id, app):
    """Live value DERIVED from append-only records, never stored.

    Proven by computing SUM(charges) - SUM(payments) straight off the tables and
    demanding the API's number match to the cent.
    """
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.payment import Payment

    tab, _ = open_tab_with_charge(client, owner_token, food_item_id, qty=3)   # 3 x 1200
    client.post(f"/tabs/{tab}/payments", json={"amount": "1500", "method": "CASH"},
                headers=auth(owner_token))
    client.post(f"/tabs/{tab}/payments", json={"amount": "700.50", "method": "MPESA",
                                               "mpesa_code": "QK12AB34"},
                headers=auth(owner_token))

    charges = sum(Decimal(str(c.amount))
                  for c in db.session.query(Charge).filter_by(tab_id=tab))
    payments = sum(Decimal(str(p.amount))
                   for p in db.session.query(Payment).filter_by(tab_id=tab))

    assert balance_of(client, owner_token, tab) == charges - payments
    assert balance_of(client, owner_token, tab) == Decimal("1399.50")


def test_no_tab_row_ever_stores_a_balance(app):
    """Structural: if Tab grew a `balance` column somebody would start reading a
    stale copy. The invariant is enforceable at the schema level, so check it."""
    from app.models.tab import Tab
    cols = {c.name for c in Tab.__table__.columns}
    assert "balance" not in cols and "total" not in cols, (
        f"Tab must never cache a balance; found {cols & {'balance', 'total'}}")


def test_money_columns_are_decimal_not_float(app):
    """Invariant 1 — money is Decimal. A Float column here is a silent
    rounding bug in every report downstream."""
    import sqlalchemy as sa
    from app.models.charge import Charge
    from app.models.payment import Payment
    from app.models.budget import Budget
    from app.models.cash_reconciliation import CashReconciliation

    money_cols = [
        (Charge, "amount"), (Charge, "tax_rate_snapshot"),
        (Payment, "amount"), (Budget, "amount"),
        (CashReconciliation, "expected_amount"),
        (CashReconciliation, "actual_amount"),
        (CashReconciliation, "difference"),
    ]
    for model, col in money_cols:
        t = model.__table__.columns[col].type
        assert isinstance(t, sa.Numeric) and not isinstance(t, sa.Float), \
            f"{model.__name__}.{col} is {t!r}, must be Numeric"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Payment amount validation — the BAD paths that must be refused
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("amount", ["-100", "0", "-0.01", "NaN", "Infinity", "-Infinity"])
def test_bad_payment_amounts_are_refused_in_plain_english(client, owner_token,
                                                          food_item_id, amount):
    """Negative, zero, NaN and Infinity must all bounce with a message a
    front-desk clerk can read. app/utils/money.py checks is_finite() BEFORE any
    comparison, which is what stops NaN from blowing up the comparison.

    The assertion used to demand the literal word "positive" for all six cases.
    That was too tight: it forced one vague sentence to cover four different
    mistakes. The messages now name the ACTUAL problem — "cannot be negative",
    "must be more than zero", "must be a real number" — which is more use to
    the person holding the cash, so the test checks the message identifies the
    field and the fault instead of matching one magic word.
    """
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    r = client.post(f"/tabs/{tab}/payments", json={"amount": amount, "method": "CASH"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    msg = r.get_json()["error"]
    assert msg and not msg.startswith("<"), "error must be plain English, not markup"
    assert "amount" in msg.lower(), f"message must name the field: {msg}"
    assert any(w in msg.lower() for w in
               ("positive", "negative", "more than zero", "real number")), \
        f"message must say what is actually wrong: {msg}"
    # and nothing was written
    assert balance_of(client, owner_token, tab) == Decimal("1200.00")


@pytest.mark.parametrize("amount", ["abc", "1,200", "", [1], {"a": 1}, True])
def test_non_numeric_payment_amounts_are_refused(client, owner_token, food_item_id, amount):
    """Junk in the amount field is a bad request, never a 500."""
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    r = client.post(f"/tabs/{tab}/payments", json={"amount": amount, "method": "CASH"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_payment_needs_a_known_method(client, owner_token, food_item_id):
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    r = client.post(f"/tabs/{tab}/payments", json={"amount": "100", "method": "BITCOIN"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "CASH" in r.get_json()["error"]


def test_payment_on_a_closed_tab_is_refused(client, owner_token, food_item_id):
    """Closed means closed — a late payment must not reopen the ledger."""
    tab, order_id = open_tab_with_charge(client, owner_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(owner_token))
    serve_all_items(client, owner_token, order_id)
    assert client.post(f"/tabs/{tab}/close", headers=auth(owner_token)).status_code == 200

    r = client.post(f"/tabs/{tab}/payments", json={"amount": "50", "method": "CASH"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "closed" in r.get_json()["error"].lower()


def test_payment_against_a_tab_that_does_not_exist_is_404(client, owner_token):
    r = client.post(f"/tabs/{uuid.uuid4()}/payments",
                    json={"amount": "100", "method": "CASH"}, headers=auth(owner_token))
    assert r.status_code == 404
    assert "not found" in r.get_json()["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Idempotency
# ═══════════════════════════════════════════════════════════════════════════

def test_the_same_idempotency_key_cannot_double_charge_a_tab(client, owner_token,
                                                             food_item_id, app):
    """Retry storm: five identical POSTs with one key must leave one Payment."""
    from app.extensions import db
    from app.models.payment import Payment

    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    key = str(uuid.uuid4())
    codes = []
    for _ in range(5):
        r = client.post(f"/tabs/{tab}/payments",
                        json={"amount": "1200", "method": "CASH", "idempotency_key": key},
                        headers=auth(owner_token))
        codes.append(r.status_code)

    assert codes[0] == 201 and set(codes[1:]) == {200}
    assert db.session.query(Payment).filter_by(tab_id=tab).count() == 1
    assert balance_of(client, owner_token, tab) == Decimal("0.00")


def test_order_idempotency_does_not_create_a_second_order(client, owner_token,
                                                          food_item_id, app):
    from app.extensions import db
    from app.models.order import Order
    key = str(uuid.uuid4())
    payload = {"idempotency_key": key,
               "items": [{"menu_item_id": food_item_id, "quantity": 2}]}
    r1 = client.post("/orders", json=payload, headers=auth(owner_token))
    r2 = client.post("/orders", json=payload, headers=auth(owner_token))
    assert r1.status_code == 201 and r2.status_code == 200
    assert r2.get_json()["duplicate"] is True
    assert db.session.query(Order).count() == 1


def test_sending_the_same_order_twice_does_not_double_the_charges(client, owner_token,
                                                                  food_item_id, app):
    """The DRAFT check is the only thing between one send and two sets of
    Charges — there is no idempotency key on the send call itself."""
    from app.extensions import db
    from app.models.charge import Charge
    tab, order_id = open_tab_with_charge(client, owner_token, food_item_id)
    again = client.post(f"/orders/{order_id}/send", headers=auth(owner_token))
    assert again.status_code == 400
    assert db.session.query(Charge).filter_by(tab_id=tab).count() == 1
    assert balance_of(client, owner_token, tab) == Decimal("1200.00")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Decimal precision
# ═══════════════════════════════════════════════════════════════════════════

def test_two_hundred_ten_cent_payments_sum_exactly(client, owner_token, food_item_id):
    """0.10 has no exact binary representation. 200 of them under float
    arithmetic drift; under Decimal they are exactly 20.00."""
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    for _ in range(200):
        r = client.post(f"/tabs/{tab}/payments", json={"amount": "0.10", "method": "CASH"},
                        headers=auth(owner_token))
        assert r.status_code == 201
    assert balance_of(client, owner_token, tab) == Decimal("1180.00")


def test_a_third_of_a_shilling_three_times_does_not_drift(client, owner_token, food_item_id):
    """0.33 x 3 = 0.99, not 0.9899999999999999."""
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    for _ in range(3):
        client.post(f"/tabs/{tab}/payments", json={"amount": "0.33", "method": "CASH"},
                    headers=auth(owner_token))
    assert balance_of(client, owner_token, tab) == Decimal("1199.01")


# ═══════════════════════════════════════════════════════════════════════════
# 5. VAT — frozen snapshots, inclusive split, reversal symmetry
# ═══════════════════════════════════════════════════════════════════════════

def test_the_tax_rate_is_frozen_on_the_charge(client, owner_token, food_item_id, app):
    """Invariant 3 — historical facts frozen at write time. Move the statutory
    rate after the sale; the sale must keep computing at the old rate."""
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.system_setting import SystemSetting

    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    charge = db.session.query(Charge).filter_by(tab_id=tab).one()
    assert Decimal(str(charge.tax_rate_snapshot)) == Decimal("16.00")
    assert charge.tax_amount == Decimal("165.52")          # 1200 x 16/116
    assert charge.net_amount == Decimal("1034.48")
    assert charge.tax_amount + charge.net_amount == Decimal(str(charge.amount))

    db.session.add(SystemSetting(key="vat_rate_percent", value="20"))
    db.session.commit()
    db.session.expire_all()

    charge = db.session.query(Charge).filter_by(tab_id=tab).one()
    assert Decimal(str(charge.tax_rate_snapshot)) == Decimal("16.00"), \
        "a statutory change must not rewrite a sale already made"
    assert charge.tax_amount == Decimal("165.52")


def test_a_reversal_carries_the_original_rate_and_cancels_the_tax(
        client, waiter_token, manager_token, food_item_id, app):
    """Refund a served item after the rate moves. The negative Charge must carry
    the ORIGINAL rate, or the VAT return will not net back to zero."""
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.system_setting import SystemSetting

    tab, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)

    db.session.add(SystemSetting(key="vat_rate_percent", value="25"))
    db.session.commit()

    from app.models.order_item import OrderItem
    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()
    r = client.post(f"/order-items/{oi.id}/refund",
                    json={"reason": "sent back cold", "idempotency_key": str(uuid.uuid4())},
                    headers=auth(manager_token))
    assert r.status_code == 200, r.get_data(as_text=True)

    charges = db.session.query(Charge).filter_by(tab_id=tab).all()
    assert len(charges) == 2, "correction must be a NEW row, never an edit"
    assert sum(Decimal(str(c.amount)) for c in charges) == Decimal("0")
    assert sum(c.tax_amount for c in charges) == Decimal("0"), \
        "reversal tax must exactly cancel the original tax"
    assert {Decimal(str(c.tax_rate_snapshot)) for c in charges} == {Decimal("16.00")}


def test_split_inclusive_is_exactly_symmetric_across_zero(app):
    """Every gross from 0.01 to 40.00 and its negative must produce tax figures
    that sum to zero — otherwise a refund leaves a stray cent of VAT behind.
    Also proves net + tax == gross for both signs."""
    from app.services.tax import split_inclusive
    rate = Decimal("16")
    for cents in range(1, 4001):
        gross = Decimal(cents) / Decimal("100")
        net_p, tax_p = split_inclusive(gross, rate)
        net_n, tax_n = split_inclusive(-gross, rate)
        assert tax_p == -tax_n, f"asymmetric at {gross}"
        assert net_p + tax_p == gross
        assert net_n + tax_n == -gross


def test_a_malformed_vat_rate_never_becomes_zero_percent(app):
    """Under-reporting tax because a setting got fat-fingered is a KRA problem,
    not a rounding problem."""
    from app.extensions import db
    from app.models.system_setting import SystemSetting
    from app.services.tax import get_vat_rate, DEFAULT_VAT_RATE
    db.session.add(SystemSetting(key="vat_rate_percent", value="sixteen"))
    db.session.commit()
    assert get_vat_rate() == DEFAULT_VAT_RATE


# ═══════════════════════════════════════════════════════════════════════════
# 6. Refunds / reversals
# ═══════════════════════════════════════════════════════════════════════════

def test_a_refund_cannot_be_applied_twice(client, waiter_token, manager_token,
                                          food_item_id, app):
    """A reversal larger than the original is the classic skim. Two different
    idempotency keys, same item — the second must not write another credit."""
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.order_item import OrderItem

    tab, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)
    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()

    first = client.post(f"/order-items/{oi.id}/refund",
                        json={"reason": "cold", "idempotency_key": str(uuid.uuid4())},
                        headers=auth(manager_token))
    second = client.post(f"/order-items/{oi.id}/refund",
                         json={"reason": "cold again", "idempotency_key": str(uuid.uuid4())},
                         headers=auth(manager_token))
    assert first.status_code == 200 and second.status_code == 200
    assert second.get_json().get("duplicate") is True

    negatives = [c for c in db.session.query(Charge).filter_by(tab_id=tab)
                 if Decimal(str(c.amount)) < 0]
    assert len(negatives) == 1
    assert sum(Decimal(str(c.amount))
               for c in db.session.query(Charge).filter_by(tab_id=tab)) == Decimal("0")


def test_a_refund_never_edits_the_original_charge(client, waiter_token, manager_token,
                                                  food_item_id, app):
    """Append-only: the original row's id, amount and timestamp survive intact."""
    from app.extensions import db
    from app.models.charge import Charge
    from app.models.order_item import OrderItem

    tab, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)
    original = db.session.query(Charge).filter_by(tab_id=tab).one()
    frozen = (original.id, Decimal(str(original.amount)), original.created_at)

    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()
    client.post(f"/order-items/{oi.id}/refund",
                json={"reason": "cold", "idempotency_key": str(uuid.uuid4())},
                headers=auth(manager_token))
    db.session.expire_all()

    after = db.session.get(Charge, frozen[0])
    assert (after.id, Decimal(str(after.amount)), after.created_at) == frozen


def test_a_waiter_cannot_refund(client, waiter_token, manager_token, food_item_id, app):
    from app.extensions import db
    from app.models.order_item import OrderItem
    _, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)
    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()
    r = client.post(f"/order-items/{oi.id}/refund",
                    json={"reason": "because", "idempotency_key": str(uuid.uuid4())},
                    headers=auth(waiter_token))
    assert r.status_code == 403
    assert "manager" in r.get_json()["error"].lower()


def test_a_refund_needs_a_reason_and_an_idempotency_key(client, waiter_token,
                                                        manager_token, food_item_id, app):
    from app.extensions import db
    from app.models.order_item import OrderItem
    _, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)
    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()

    no_key = client.post(f"/order-items/{oi.id}/refund", json={"reason": "x"},
                         headers=auth(manager_token))
    assert no_key.status_code == 400 and "idempotency" in no_key.get_json()["error"].lower()

    no_reason = client.post(f"/order-items/{oi.id}/refund",
                            json={"idempotency_key": str(uuid.uuid4())},
                            headers=auth(manager_token))
    assert no_reason.status_code == 400 and "reason" in no_reason.get_json()["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Tab closing rules
# ═══════════════════════════════════════════════════════════════════════════

def test_a_tab_cannot_close_with_money_owed(client, owner_token, food_item_id):
    tab, order_id = open_tab_with_charge(client, owner_token, food_item_id)
    serve_all_items(client, owner_token, order_id)
    r = client.post(f"/tabs/{tab}/close", headers=auth(owner_token))
    assert r.status_code == 400
    assert "outstanding balance" in r.get_json()["error"].lower()


def test_a_tab_cannot_close_with_food_still_in_the_kitchen(client, owner_token,
                                                           food_item_id):
    """Paid in full but the plate never arrived — closing would lose the fact
    that the guest is owed food."""
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(owner_token))
    r = client.post(f"/tabs/{tab}/close", headers=auth(owner_token))
    assert r.status_code == 400
    assert "still pending" in r.get_json()["error"].lower()


def test_closing_a_settled_tab_twice_is_refused(client, owner_token, food_item_id):
    tab, order_id = open_tab_with_charge(client, owner_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(owner_token))
    serve_all_items(client, owner_token, order_id)
    assert client.post(f"/tabs/{tab}/close", headers=auth(owner_token)).status_code == 200
    again = client.post(f"/tabs/{tab}/close", headers=auth(owner_token))
    assert again.status_code == 400
    assert "already closed" in again.get_json()["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Wristband credit ceiling
# ═══════════════════════════════════════════════════════════════════════════

def test_a_band_tab_starts_with_the_entry_fee_as_credit(client, owner_token):
    """One Payment record IS the credit — balance -3000, no special case."""
    from app.services.gate import ENTRY_FEE
    tab = issue_band(client, owner_token)
    assert balance_of(client, owner_token, tab) == -ENTRY_FEE


def test_band_credit_ceiling_stops_the_charge_that_would_break_it(
        client, owner_token, drink_item_id):
    """Ceiling = 2 x ENTRY_FEE = 6,000 owed. Starting at -3,000 credit that is
    9,000 of drinks. The 10th batch of 10 lagers (3,000) is the one refused."""
    from app.services.gate import ENTRY_FEE
    from app.services.tab import BAND_CREDIT_CEILING_MULTIPLIER
    ceiling = ENTRY_FEE * BAND_CREDIT_CEILING_MULTIPLIER

    tab = issue_band(client, owner_token)
    refused = None
    for _ in range(10):
        o = client.post("/orders", json={"tab_id": tab,
                                         "items": [{"menu_item_id": drink_item_id,
                                                    "quantity": 10}]},   # 10 x 300
                        headers=auth(owner_token))
        s = client.post(f"/orders/{o.get_json()['id']}/send", headers=auth(owner_token))
        if s.status_code != 200:
            refused = s
            break

    assert refused is not None, "the ceiling never engaged"
    assert refused.status_code == 400
    msg = refused.get_json()["error"]
    assert "spending limit" in msg and "gate" in msg.lower(), \
        "the refusal must tell the waiter what to do next"
    assert balance_of(client, owner_token, tab) <= ceiling


def test_one_giant_order_cannot_jump_the_band_ceiling(client, owner_token, drink_item_id):
    """The check sums the WHOLE send, so splitting or inflating one order both
    hit the same wall (app/pos/orders.py:163)."""
    tab = issue_band(client, owner_token)
    o = client.post("/orders", json={"tab_id": tab,
                                     "items": [{"menu_item_id": drink_item_id,
                                                "quantity": 1000}]},
                    headers=auth(owner_token))
    s = client.post(f"/orders/{o.get_json()['id']}/send", headers=auth(owner_token))
    assert s.status_code == 400
    assert "spending limit" in s.get_json()["error"]
    assert balance_of(client, owner_token, tab) == Decimal("-3000.00")


def test_the_ceiling_does_not_apply_to_a_walk_in_tab(client, owner_token, drink_item_id):
    """A restaurant table has no ceiling — only wristbands do."""
    o = client.post("/orders", json={"items": [{"menu_item_id": drink_item_id,
                                                "quantity": 100}]},
                    headers=auth(owner_token))
    tab = o.get_json()["tab_id"]
    s = client.post(f"/orders/{o.get_json()['id']}/send", headers=auth(owner_token))
    assert s.status_code == 200
    assert balance_of(client, owner_token, tab) == Decimal("30000.00")


# ═══════════════════════════════════════════════════════════════════════════
# 9. Deposits
# ═══════════════════════════════════════════════════════════════════════════

def test_a_villa_cannot_be_confirmed_without_the_deposit(client, owner_token,
                                                         villa_resource):
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=5)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    r = client.post("/bookings", json={
        "resource_id": villa_resource.id, "guest_name": "Deposit Test",
        "guest_phone": "+254700900777",
        "check_in_planned_utc": ci.isoformat(),
        "check_out_planned_utc": co.isoformat(), "number_of_guests": 2,
    }, headers=auth(owner_token))
    bid = r.get_json()["id"]
    assert Decimal(r.get_json()["deposit_required"]) == Decimal("3000.00")   # 30% of 10,000

    blocked = client.post(f"/bookings/{bid}/confirm", headers=auth(owner_token))
    assert blocked.status_code == 400
    assert "deposit" in blocked.get_json()["error"].lower()

    # A PART payment is still not enough.
    client.post("/booking-payments",
                json={"booking_id": bid, "purpose": "DEPOSIT",
                      "method": "CASH", "amount": "2999.99"},
                headers=auth(owner_token))
    still_blocked = client.post(f"/bookings/{bid}/confirm", headers=auth(owner_token))
    assert still_blocked.status_code == 400

    client.post("/booking-payments",
                json={"booking_id": bid, "purpose": "DEPOSIT",
                      "method": "MPESA", "amount": "0.01"},
                headers=auth(owner_token))
    assert client.post(f"/bookings/{bid}/confirm",
                       headers=auth(owner_token)).status_code == 200


@pytest.mark.parametrize("amount", ["0", "-500", "abc", "NaN"])
def test_a_deposit_must_be_a_positive_number(client, owner_token, villa_resource, amount):
    """deposits.py wraps the comparison inside the try, so NaN is caught here —
    This one always had the check in the right order. The three finance
    endpoints that did not — cash count, budget, safe count — are fixed now and
    pinned further down."""
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=6)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    bid = client.post("/bookings", json={
        "resource_id": villa_resource.id, "guest_name": "Neg Deposit",
        "guest_phone": "+254700900888",
        "check_in_planned_utc": ci.isoformat(),
        "check_out_planned_utc": co.isoformat(), "number_of_guests": 2,
    }, headers=auth(owner_token)).get_json()["id"]

    r = client.post("/booking-payments",
                    json={"booking_id": bid, "purpose": "DEPOSIT",
                          "method": "CASH", "amount": amount},
                    headers=auth(owner_token))
    assert r.status_code == 400
    # The message now names the ACTUAL fault (negative / zero / not a
    # real number) instead of one vague word covering all three.
    assert any(w in r.get_json()["error"].lower() for w in
               ("positive", "negative", "more than zero", "real number"))


def test_a_deposit_is_idempotent(client, owner_token, villa_resource, app):
    from app.extensions import db
    from app.models.payment import Payment
    now = datetime.now(timezone.utc)
    ci = (now + timedelta(days=7)).replace(hour=14, minute=0, second=0, microsecond=0)
    co = (ci + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    bid = client.post("/bookings", json={
        "resource_id": villa_resource.id, "guest_name": "Dup Deposit",
        "guest_phone": "+254700900999",
        "check_in_planned_utc": ci.isoformat(),
        "check_out_planned_utc": co.isoformat(), "number_of_guests": 2,
    }, headers=auth(owner_token)).get_json()["id"]

    key = str(uuid.uuid4())
    payload = {"booking_id": bid, "purpose": "DEPOSIT", "method": "CASH",
               "amount": "3000", "idempotency_key": key}
    a = client.post("/booking-payments", json=payload, headers=auth(owner_token))
    b = client.post("/booking-payments", json=payload, headers=auth(owner_token))
    assert a.status_code == 201 and b.status_code == 200
    assert b.get_json()["duplicate"] is True
    assert db.session.query(Payment).filter(
        Payment.description.like(f"deposit for booking {bid[:8]}")).count() == 1


def test_the_deposit_becomes_credit_on_the_villa_tab(client, owner_token, villa_resource):
    """3,000 deposit + 10,000 room => 7,000 owed at check-in."""
    _, tab = checked_in_villa(client, owner_token, villa_resource)
    assert balance_of(client, owner_token, tab) == Decimal("7000.00")


def test_checkout_is_blocked_while_the_villa_tab_owes_money(client, owner_token,
                                                            villa_resource):
    bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                phone="+254700900002")
    r = client.post(f"/bookings/{bid}/check-out", headers=auth(owner_token))
    assert r.status_code == 400
    assert "outstanding balance" in r.get_json()["error"].lower()

    client.post(f"/tabs/{tab}/payments", json={"amount": "7000", "method": "CASH"},
                headers=auth(owner_token))
    assert client.post(f"/bookings/{bid}/check-out",
                       headers=auth(owner_token)).status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 10. Cash reconciliation & budgets — role boundaries and derivation
# ═══════════════════════════════════════════════════════════════════════════

def test_expected_cash_is_derived_and_a_payment_is_swept_only_once(
        client, owner_token, waiter_token, food_item_id, app):
    from app.models.user import User
    from app.extensions import db

    tab, _ = open_tab_with_charge(client, waiter_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "700", "method": "CASH"},
                headers=auth(waiter_token))
    client.post(f"/tabs/{tab}/payments", json={"amount": "500", "method": "MPESA",
                                               "mpesa_code": "QQ1"},
                headers=auth(waiter_token))

    waiter = db.session.query(User).filter_by(username="waiter1").one()
    pending = client.get(f"/finance/cash/pending?staff_id={waiter.id}",
                         headers=auth(owner_token)).get_json()
    assert Decimal(pending["expected_total"]) == Decimal("700.00"), "MPESA is not cash"

    r = client.post("/finance/cash/reconcile",
                    json={"staff_id": waiter.id, "actual_amount": "700"},
                    headers=auth(owner_token))
    assert r.status_code == 201 and r.get_json()["status"] == "BALANCED"

    after = client.get(f"/finance/cash/pending?staff_id={waiter.id}",
                       headers=auth(owner_token)).get_json()
    assert Decimal(after["expected_total"]) == Decimal("0"), "swept payments must not reappear"


def test_a_shortfall_is_recorded_not_hidden(client, owner_token, waiter_token,
                                            food_item_id, app):
    from app.models.user import User
    from app.extensions import db
    tab, _ = open_tab_with_charge(client, waiter_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(waiter_token))
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    r = client.post("/finance/cash/reconcile",
                    json={"staff_id": waiter.id, "actual_amount": "1100"},
                    headers=auth(owner_token))
    assert r.status_code == 201
    assert r.get_json()["status"] == "SHORT"
    assert Decimal(r.get_json()["difference"]) == Decimal("-100.00")


def test_a_waiter_cannot_reconcile_cash_or_read_the_float(client, waiter_token, app):
    from app.models.user import User
    from app.extensions import db
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    for r in (client.get(f"/finance/cash/pending?staff_id={waiter.id}",
                         headers=auth(waiter_token)),
              client.post("/finance/cash/reconcile",
                          json={"staff_id": waiter.id, "actual_amount": "0"},
                          headers=auth(waiter_token))):
        assert r.status_code == 403
        assert "manager" in r.get_json()["error"].lower()


def test_cash_reconciliation_is_idempotent(client, owner_token, waiter_token,
                                           food_item_id, app):
    from app.models.user import User
    from app.extensions import db
    from app.models.cash_reconciliation import CashReconciliation

    tab, _ = open_tab_with_charge(client, waiter_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(waiter_token))
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    key = str(uuid.uuid4())
    body = {"staff_id": waiter.id, "actual_amount": "1200", "idempotency_key": key}
    a = client.post("/finance/cash/reconcile", json=body, headers=auth(owner_token))
    b = client.post("/finance/cash/reconcile", json=body, headers=auth(owner_token))
    assert a.status_code == 201 and b.status_code == 200
    assert db.session.query(CashReconciliation).count() == 1


def test_a_negative_actual_cash_count_is_refused(client, owner_token, waiter_token, app):
    from app.models.user import User
    from app.extensions import db
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    r = client.post("/finance/cash/reconcile",
                    json={"staff_id": waiter.id, "actual_amount": "-1"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "negative" in r.get_json()["error"].lower()


def test_a_waiter_cannot_set_or_read_budgets(client, waiter_token, general_dept_id):
    a = client.post("/finance/budgets",
                    json={"department_id": general_dept_id, "period": "2026-09",
                          "amount": "50000"}, headers=auth(waiter_token))
    b = client.get("/finance/budgets/status?period=2026-09", headers=auth(waiter_token))
    assert a.status_code == 403 and b.status_code == 403


def test_a_manager_cannot_edit_or_disable_a_budget_already_in_force(
        client, owner_token, manager_token, general_dept_id):
    created = client.post("/finance/budgets",
                          json={"department_id": general_dept_id, "period": "2026-09",
                                "amount": "50000"}, headers=auth(manager_token))
    assert created.status_code == 201
    bid = created.get_json()["id"]
    assert client.patch(f"/finance/budgets/{bid}", json={"amount": "1"},
                        headers=auth(manager_token)).status_code == 403
    assert client.post(f"/finance/budgets/{bid}/disable",
                       headers=auth(manager_token)).status_code == 403


def test_a_negative_budget_is_refused_and_duplicates_are_rejected(
        client, owner_token, general_dept_id):
    neg = client.post("/finance/budgets",
                      json={"department_id": general_dept_id, "period": "2026-09",
                            "amount": "-1"}, headers=auth(owner_token))
    assert neg.status_code == 400 and "negative" in neg.get_json()["error"].lower()

    ok = client.post("/finance/budgets",
                     json={"department_id": general_dept_id, "period": "2026-09",
                           "amount": "1000"}, headers=auth(owner_token))
    assert ok.status_code == 201
    dup = client.post("/finance/budgets",
                      json={"department_id": general_dept_id, "period": "2026-09",
                            "amount": "2000"}, headers=auth(owner_token))
    assert dup.status_code == 409
    assert "already exists" in dup.get_json()["error"]


def test_exceeding_a_budget_is_reported_not_blocked(client, owner_token,
                                                    general_dept_id, app):
    """Spending past a budget must be VISIBLE. It is a reporting flag, not a
    hard stop — but the flag has to actually fire."""
    from app.extensions import db
    from app.models.inventory_item import InventoryItem

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    client.post("/finance/budgets",
                json={"department_id": general_dept_id, "period": period,
                      "amount": "1000"}, headers=auth(owner_token))

    item = InventoryItem(name="Scenario Flour", unit="kg",
                         department_id=general_dept_id)
    db.session.add(item)
    db.session.commit()

    # Spend through the REAL endpoint, not a hand-built Purchase row. A direct
    # ORM insert skipped receipt_photo_path (NOT NULL) and idempotency_key, so
    # the test blew up on a constraint instead of exercising the budget. Going
    # through POST /purchases also proves the spend the budget report reads is
    # the same spend a manager actually records.
    p = client.post("/inventory/purchases",
                    json={"item_id": item.id, "quantity": "1",
                          "actual_cost": "2500",
                          "receipt_photo_path": "uploads/receipts/flour.jpg",
                          "idempotency_key": str(uuid.uuid4())},
                    headers=auth(owner_token))
    assert p.status_code == 201, p.get_data(as_text=True)

    rows = client.get(f"/finance/budgets/status?period={period}",
                      headers=auth(owner_token)).get_json()["budgets"]
    row = next(r for r in rows if r["department"] == "General")
    assert Decimal(row["spent"]) == Decimal("2500.00")
    assert Decimal(row["remaining"]) == Decimal("-1500.00")
    assert row["over_budget"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 11. Audit trail
# ═══════════════════════════════════════════════════════════════════════════

def test_every_money_write_leaves_an_audit_row(client, owner_token, waiter_token,
                                               food_item_id, app):
    from app.extensions import db
    from app.models.audit_log import AuditLog
    from app.models.user import User

    # Every step is asserted. Without this the money writes could all quietly
    # 400 and the test would then be complaining that a write it never made
    # left no audit row — which is exactly how it read tab.close as a hole.
    tab, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    pay = client.post(f"/tabs/{tab}/payments",
                      json={"amount": "1200", "method": "CASH"},
                      headers=auth(waiter_token))
    assert pay.status_code == 201, pay.get_data(as_text=True)
    serve_all_items(client, waiter_token, order_id, prep_token=owner_token)
    closed = client.post(f"/tabs/{tab}/close", headers=auth(waiter_token))
    assert closed.status_code == 200, closed.get_data(as_text=True)
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    rec = client.post("/finance/cash/reconcile",
                      json={"staff_id": waiter.id, "actual_amount": "1200"},
                      headers=auth(owner_token))
    assert rec.status_code == 201, rec.get_data(as_text=True)

    actions = {a.action for a in db.session.query(AuditLog).all()}
    for expected in {"order.create", "order.send", "payment.record",
                     "tab.close", "finance.cash.reconcile"}:
        assert expected in actions, f"{expected} left no audit trail"


def test_the_audit_row_names_the_person_and_the_amount(client, waiter_token,
                                                       food_item_id, app):
    from app.extensions import db
    from app.models.audit_log import AuditLog
    tab, _ = open_tab_with_charge(client, waiter_token, food_item_id)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "MPESA",
                                               "mpesa_code": "QQ7"},
                headers=auth(waiter_token))
    row = db.session.query(AuditLog).filter_by(action="payment.record").one()
    assert row.actor == "waiter1"
    assert row.target == tab
    assert "1200" in row.details and "MPESA" in row.details


# ═══════════════════════════════════════════════════════════════════════════
# 12. CONFIRMED HOLES
#
# Each of these asserts the behaviour the invariants require. strict=True means
# a fix turns the test green and pytest then reports XPASS as a FAILURE, forcing
# whoever fixed it to delete the marker. Do not "fix" these by relaxing them.
# ═══════════════════════════════════════════════════════════════════════════

def test_a_negative_water_session_charge_is_refused(client, owner_token,
                                                    villa_resource):
    """WAS HOLE 1 — now closed, so this is regression cover.

    POST /bookings/<id>/water-sessions used to take `amount` straight from the
    request body and write it as a Charge with no positivity check, so front
    desk could post a NEGATIVE charge and wipe a guest's bill with no Payment
    row to show for it. app/models/charge.py:9-11 states the invariant: 'No API
    accepts an arbitrary negative amount — that would be the skim vector the
    judge watches.' app/bookings/core.py now refuses it, and the guest's
    balance must be untouched afterwards.
    """
    bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                phone="+254700901001")
    sign_water_waiver(client, owner_token, bid)
    before = balance_of(client, owner_token, tab)          # 7000.00

    r = client.post(f"/bookings/{bid}/water-sessions", json={"amount": "-5000"},
                    headers=auth(owner_token))
    assert r.status_code == 400, (
        f"a negative charge was ACCEPTED: {r.status_code} {r.get_json()}")
    # The refusal must be readable by a front-desk clerk, not a stack trace.
    # The message now names the ACTUAL fault (negative / zero / not a
    # real number) instead of one vague word covering all three.
    assert any(w in r.get_json()["error"].lower() for w in
               ("positive", "negative", "more than zero", "real number"))
    assert balance_of(client, owner_token, tab) == before


def test_an_absurd_water_session_charge_must_be_refused(client, owner_token,
                                                       villa_resource):
    """WAS HOLE 2 — app/bookings/core.py:474-490. Same endpoint, no upper
    bound. amount='1e15' is accepted; Charge.amount is Numeric(14,2) whose
    maximum is 999,999,999,999.99, so on PostgreSQL this is a numeric-
    field-overflow 500 and on SQLite it silently lands a
    1,000,000,000,002,000 balance.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                phone="+254700901002")
    sign_water_waiver(client, owner_token, bid)
    r = client.post(f"/bookings/{bid}/water-sessions", json={"amount": "1e15"},
                    headers=auth(owner_token))
    assert r.status_code == 400, (
        f"an out-of-range charge was ACCEPTED: {r.get_json()}")


@pytest.mark.parametrize("amount", ["0", "NaN"])
def test_a_degenerate_water_session_amount_does_not_crash(client, owner_token,
                                                          villa_resource, amount):
    """WAS HOLE 3 — now closed, so this is regression cover.

    amount='0' used to reach the INSERT and trip CheckConstraint
    ck_charge_amount_nonzero; amount='NaN' got past `Decimal(...)` fine and then
    blew up on the `amount <= 0` comparison (Decimal('NaN') <= 0 raises
    InvalidOperation, it does not return False). Both surfaced as a bare 500,
    violating 'every error response has a plain-English message'. The guard is
    now `not amount.is_finite() or amount <= 0`, checked in that order.
    """
    bid, _ = checked_in_villa(client, owner_token, villa_resource,
                              phone="+254700901003")
    sign_water_waiver(client, owner_token, bid)
    r = client.post(f"/bookings/{bid}/water-sessions", json={"amount": amount},
                    headers=auth(owner_token))
    assert r.status_code == 400
    # The message now names the ACTUAL fault (negative / zero / not a
    # real number) instead of one vague word covering all three.
    assert any(w in r.get_json()["error"].lower() for w in
               ("positive", "negative", "more than zero", "real number"))


def test_the_water_session_charge_must_be_idempotent(client, owner_token,
                                                    villa_resource):
    """WAS HOLE 4 — app/bookings/core.py:487. The water-session charge has no
    idempotency key at all: the endpoint reads no such field and Charge
    has no such column. A double-tapped 'Add jetski' posts the charge
    twice. Violates 'every write: transaction + idempotency_key + audit
    log'.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                phone="+254700901004")
    sign_water_waiver(client, owner_token, bid)
    key = str(uuid.uuid4())
    body = {"amount": "3000", "idempotency_key": key}
    client.post(f"/bookings/{bid}/water-sessions", json=body, headers=auth(owner_token))
    client.post(f"/bookings/{bid}/water-sessions", json=body, headers=auth(owner_token))
    assert balance_of(client, owner_token, tab) == Decimal("10000.00"), \
        "the retry charged the guest a second time"


def test_a_nan_quantity_must_be_refused_not_crash(client, owner_token, food_item_id):
    """WAS HOLE 5 — app/pos/orders.py:110. `if qty <= 0 or not
    qty.is_finite()` evaluates the comparison FIRST, and Decimal('NaN') <=
    0 raises decimal.InvalidOperation. quantity='NaN' is an unhandled 500.
    The operands are the right way round in app/pos/payments.py:44 — same
    check, opposite order, and that one is safe.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    r = client.post("/orders",
                    json={"items": [{"menu_item_id": food_item_id, "quantity": "NaN"}]},
                    headers=auth(owner_token))
    assert r.status_code == 400
    # The message now names the ACTUAL fault (negative / zero / not a
    # real number) instead of one vague word covering all three.
    assert any(w in r.get_json()["error"].lower() for w in
               ("positive", "negative", "more than zero", "real number"))


def test_a_nan_cash_count_must_be_refused_not_crash(client, owner_token, app):
    """WAS HOLE 6 — app/finance/cash.py:92. `except InvalidOperation` covers
    only the Decimal() construction; Decimal('NaN') constructs fine and
    then `actual < Decimal('0')` raises InvalidOperation. Unhandled 500 on
    a cash-reconciliation endpoint.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    from app.models.user import User
    from app.extensions import db
    waiter = db.session.query(User).filter_by(username="waiter1").one()
    r = client.post("/finance/cash/reconcile",
                    json={"staff_id": waiter.id, "actual_amount": "NaN"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_a_nan_budget_must_be_refused_not_crash(client, owner_token, general_dept_id):
    """WAS HOLE 7 — app/finance/budgets.py:56. Identical bug shape to HOLE 6:
    `if amount < Decimal('0')` sits outside the try, so amount='NaN' is an
    unhandled 500.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    r = client.post("/finance/budgets",
                    json={"department_id": general_dept_id, "period": "2026-09",
                          "amount": "NaN"}, headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_a_nan_safe_count_must_be_refused_not_crash(client, owner_token):
    """WAS HOLE 8 — app/finance/reports.py:240. Identical bug shape again:
    `if safe_count < Decimal('0')` sits outside the try, so
    safe_count='NaN' is an unhandled 500 on the end-of-day close.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    r = client.post("/finance/close-period",
                    json={"date": "2026-08-01", "safe_count": "NaN"},
                    headers=auth(owner_token))
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_a_refunded_item_must_not_block_the_tab_forever(
  client, waiter_token, manager_token, food_item_id, app):
    """WAS HOLE 9 — app/services/tab.py:78. is_tab_closable's terminal set is
    {SERVED, CANCELLED} and omits REFUNDED, even though REFUNDED is
    terminal in VALID_TRANSITIONS (app/models/order_item.py:41) and in
    _maybe_complete_order (app/pos/orders.py:487). Refund a served item
    and the tab can NEVER be closed: 'Order item X is still REFUNDED.' The
    guest leaves, the table stays open forever.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    from app.extensions import db
    from app.models.order_item import OrderItem

    tab, order_id = open_tab_with_charge(client, waiter_token, food_item_id)
    serve_all_items(client, waiter_token, order_id, prep_token=manager_token)
    client.post(f"/tabs/{tab}/payments", json={"amount": "1200", "method": "CASH"},
                headers=auth(waiter_token))
    oi = db.session.query(OrderItem).filter_by(order_id=order_id).one()
    client.post(f"/order-items/{oi.id}/refund",
                json={"reason": "inedible", "idempotency_key": str(uuid.uuid4())},
                headers=auth(manager_token))

    r = client.post(f"/tabs/{tab}/close", headers=auth(waiter_token))
    assert r.status_code == 200, (
        f"a fully-refunded, fully-paid tab could not be closed: {r.get_json()}")


def test_an_out_of_range_payment_must_be_refused(client, owner_token, food_item_id):
    """WAS HOLE 10 — app/pos/payments.py:44. The only amount ceiling is
    'positive and finite'. A fat-fingered 1e15 is accepted; Payment.amount
    is Numeric(14,2) (max 999,999,999,999.99) so PostgreSQL raises numeric
    field overflow (500) while SQLite records a trillion-shilling credit.
    Nothing compares the payment to what is actually owed.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    r = client.post(f"/tabs/{tab}/payments", json={"amount": "1e15", "method": "CASH"},
                    headers=auth(owner_token))
    assert r.status_code == 400, (
        f"payment beyond Numeric(14,2) was accepted; balance is now "
        f"{balance_of(client, owner_token, tab)}")


def test_a_sub_cent_payment_must_be_refused(client, owner_token, food_item_id, app):
    """WAS HOLE 11 — app/pos/payments.py:41-45. No cent-scale check. A
    payment of 0.004 returns 201 and the response echoes amount='0.004',
    but the ledger stores 0.00 and the balance does not move — the receipt
    and the ledger disagree. 0.4999 is silently rounded UP to 0.50,
    crediting the guest more than they handed over. On PostgreSQL the 0.00
    row also violates ck_payment_amount_pos (amount > 0) and becomes a
    500.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    from app.extensions import db
    from app.models.payment import Payment

    tab, _ = open_tab_with_charge(client, owner_token, food_item_id)
    r = client.post(f"/tabs/{tab}/payments", json={"amount": "0.004", "method": "CASH"},
                    headers=auth(owner_token))
    if r.status_code == 400:
        return                                    # refused outright — fine
    stored = db.session.query(Payment).filter_by(tab_id=tab).one()
    assert Decimal(r.get_json()["amount"]) == Decimal(str(stored.amount)), (
        f"receipt says {r.get_json()['amount']} but the ledger stored {stored.amount}")


def test_an_idempotency_key_must_be_scoped_to_its_tab(client, owner_token,
                                                     food_item_id):
    """WAS HOLE 12 — app/pos/payments.py:57. The duplicate lookup is
    filter_by(idempotency_key=...) with no tab_id, and
    Payment.idempotency_key is globally unique. A client that reuses a key
    across tabs (or two terminals that generate the same key) gets HTTP
    200 and a 'duplicate' flag for a payment that was never recorded: real
    cash collected, nothing in the ledger, and the staff member sees a
    success screen.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    tab_a, _ = open_tab_with_charge(client, owner_token, food_item_id)
    tab_b, _ = open_tab_with_charge(client, owner_token, food_item_id)
    key = str(uuid.uuid4())

    client.post(f"/tabs/{tab_a}/payments",
                json={"amount": "100", "method": "CASH", "idempotency_key": key},
                headers=auth(owner_token))
    second = client.post(f"/tabs/{tab_b}/payments",
                         json={"amount": "1200", "method": "MPESA",
                               "mpesa_code": "QQ9", "idempotency_key": key},
                         headers=auth(owner_token))

    # Either record it, or refuse it loudly. Silently reporting success is the bug.
    if second.status_code >= 400:
        return
    assert balance_of(client, owner_token, tab_b) == Decimal("0.00"), (
        f"KSh 1200 was collected on tab B and swallowed; response was "
        f"{second.status_code} {second.get_json()}")


def test_an_auto_opened_tab_must_be_audited(client, owner_token, food_item_id, app):
    """WAS HOLE 13 — app/pos/orders.py:87-91. POST /orders with no tab_id
    opens a Tab inline and writes NO AuditLog row, while POST /tabs
    (app/pos/tabs.py:122) logs 'tab.open' for the identical write. Most
    tabs on a busy night are opened this way, so most tab openings have no
    audit trail.

    Closed now, so this is regression cover: it fails again the day
    the hole comes back."""
    from app.extensions import db
    from app.models.audit_log import AuditLog
    from app.models.tab import Tab

    client.post("/orders", json={"items": [{"menu_item_id": food_item_id, "quantity": 1}]},
                headers=auth(owner_token))
    assert db.session.query(Tab).count() == 1
    assert db.session.query(AuditLog).filter_by(action="tab.open").count() == 1, \
        "a tab was created with no audit row"


def test_a_deposit_is_counted_once_in_revenue_regression(
        client, owner_token, villa_resource, app):
    """One deposit, one row, one appearance in revenue.

    THE BUG THIS PINS. The deposit is collected at booking time, before any tab
    exists, so its Payment lands with tab_id=NULL. Check-in used to write a
    SECOND Payment for the same money just to attach it to the tab. Tab balance
    came out right, so nothing looked wrong — but every revenue reader sums
    Payment rows with no filter, so a KSh 3,000 deposit was reported as KSh
    6,000 taken that day.

    Measured through get_period_revenue_by_method itself, which is what the
    daily-summary PDF (app/reports/routes.py:175) and app/finance/reports.py
    both read. Asserting on the Payment table alone would not have proved the
    number the owner actually sees.
    """
    from app.extensions import db
    from app.models.payment import Payment
    from app.services.finance import get_period_revenue_by_method

    day_start = datetime.now(timezone.utc) - timedelta(hours=12)
    day_end   = datetime.now(timezone.utc) + timedelta(hours=12)

    before = get_period_revenue_by_method(day_start, day_end)["total"]

    # checked_in_villa pays a 3,000 deposit, then checks in (which is where the
    # duplicate used to be written).
    _bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                 phone="+254700900077")

    after = get_period_revenue_by_method(day_start, day_end)["total"]
    assert after - before == Decimal("3000"), (
        f"the 3,000 deposit was counted as {after - before} — "
        f"check transfer_deposit_to_tab is not writing a second Payment")

    # The same money is on the tab exactly once, under its REAL method.
    rows = db.session.query(Payment).filter(Payment.tab_id == tab).all()
    deposits = [p for p in rows if Decimal(str(p.amount)) == Decimal("3000")]
    assert len(deposits) == 1, f"expected one 3,000 payment on the tab, got {len(deposits)}"
    assert deposits[0].method == "CASH"


# ═══════════════════════════════════════════════════════════════════════════
# Every payment point must be able to settle a room bill
# ═══════════════════════════════════════════════════════════════════════════

def test_every_role_can_take_a_payment_on_a_villa_tab(client, owner_token,
                                                      villa_resource, app):
    """The room bill must be settleable from ANY till, not just the front desk.

    A guest checks out at the gate, or hands cash to whoever is at the counter.
    If only one role could take that payment, the bill would be stuck whenever
    that person was off shift.
    """
    from app.models.user import User
    from app.extensions import db
    from flask_jwt_extended import create_access_token

    _bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                 phone="+254700900201")
    refused = []
    for username in ("grace.muthoni", "brian.mwangi", "peter.mwendwa",
                     "david.otieno", "hassan.omondi"):
        u = db.session.query(User).filter_by(username=username).first()
        if not u:
            continue
        h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}
        client.post("/hr/clock-in", json={}, headers=h,
                    environ_base={"REMOTE_ADDR": "127.0.0.1"})
        r = client.post(f"/tabs/{tab}/payments", json={"amount": "1", "method": "CASH"},
                        headers=h, environ_base={"REMOTE_ADDR": "127.0.0.1"})
        if r.status_code not in (200, 201):
            refused.append(f"{username}: {r.status_code} {r.get_json()}")
    assert not refused, "these tills cannot settle a room bill: " + "; ".join(refused)


def test_a_bank_transfer_can_be_matched_to_the_room_bill(client, owner_token,
                                                         villa_resource, app):
    """WAS A HOLE: money that arrived on its own could never settle a bill.

    M-Pesa C2B and the bank SMS forwarder write a Payment with tab_id=NULL —
    an SMS cannot say whose money it is, and guessing would be worse than not
    trying. But reconcile could only flip MATCHED/FLAGGED, never attach the
    payment, so a guest who paid their villa by transfer still showed the full
    room outstanding and was refused check-out while their money sat in the
    ledger counting towards revenue.

    Reconcile now takes an optional tab_id: the human who knows which guest
    paid is the one who says so.
    """
    from app.extensions import db
    from app.models.payment import Payment, PaymentMethod
    from app.services.tab import get_tab_balance

    _bid, tab = checked_in_villa(client, owner_token, villa_resource,
                                 phone="+254700900202")
    owed = get_tab_balance(tab)
    assert owed > 0

    # The forwarder's write: real money, no idea whose.
    p = Payment(method=PaymentMethod.BANK_TRANSFER.value, amount=owed,
                bank_ref=f"FT{uuid.uuid4().hex[:8].upper()}", received_by_id=None,
                idempotency_key=f"banksms-{uuid.uuid4().hex[:10]}",
                description="Auto-received via SMS forwarder")
    db.session.add(p)
    db.session.commit()
    assert p.tab_id is None
    assert get_tab_balance(tab) == owed, "an unattached payment must not move a bill"

    r = client.post("/finance/bank/reconcile", json={"entries": [
        {"payment_id": p.id, "action": "MATCH", "tab_id": tab,
         "statement_ref": p.bank_ref}]}, headers=auth(owner_token))
    assert r.status_code == 200, r.get_data(as_text=True)

    db.session.refresh(p)
    assert p.tab_id == tab
    assert get_tab_balance(tab) == Decimal("0"), "matching must settle the bill"


def test_a_matched_payment_is_never_stolen_from_another_bill(client, owner_token,
                                                             villa_resource, app):
    """Attaching fills a NULL. It must never MOVE money already on a bill —
    that would silently change two balances, and whoever reads the second one
    has no way of knowing why it moved."""
    from app.extensions import db
    from app.models.payment import Payment, PaymentMethod
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.services.tab import get_tab_balance

    # Two GUESTS need two VILLAS — one villa refuses a second booking over the
    # same nights, which is the double-booking guard doing its job.
    second = BookableResource(name="Scenario Villa B", capacity=4,
                              resource_type=ResourceType.VILLA.value,
                              base_price="10000")
    db.session.add(second)
    db.session.commit()

    _b1, tab_a = checked_in_villa(client, owner_token, villa_resource,
                                  phone="+254700900203")
    _b2, tab_b = checked_in_villa(client, owner_token, second,
                                  phone="+254700900204")
    p = Payment(tab_id=tab_a, method=PaymentMethod.BANK_TRANSFER.value, amount="500",
                bank_ref=f"FT{uuid.uuid4().hex[:8].upper()}", received_by_id=None,
                idempotency_key=f"banksms-{uuid.uuid4().hex[:10]}")
    db.session.add(p)
    db.session.commit()
    before_a, before_b = get_tab_balance(tab_a), get_tab_balance(tab_b)

    r = client.post("/finance/bank/reconcile", json={"entries": [
        {"payment_id": p.id, "action": "MATCH", "tab_id": tab_b}]},
        headers=auth(owner_token))
    assert r.status_code == 400
    assert "already settled against another bill" in r.get_json()["error"]

    db.session.refresh(p)
    assert p.tab_id == tab_a
    assert get_tab_balance(tab_a) == before_a
    assert get_tab_balance(tab_b) == before_b
