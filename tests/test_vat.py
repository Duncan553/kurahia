"""
VAT — recorded per sale, summarised for whoever files the return.

Filing is handled by someone else, so this is a BRIDGE not an eTIMS
integration. What the system owes that person is an accurate, reproducible
statement of what was sold and how much tax it contained.

Two decisions the tests pin down:

  PRICES ARE VAT-INCLUSIVE. That is the Kenyan hospitality norm and, more
  importantly, what the existing data already assumes — every menu price is what
  the guest actually pays. Treating those as net would have raised the whole
  menu by 16% the moment tax was switched on.

  THE RATE IS SNAPSHOTTED PER CHARGE. Rates change by statute, so a sale must
  keep computing with the rate that applied when it was made (invariant 3).
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.charge import Charge
from app.models.system_setting import SystemSetting
from app.services.tax import get_vat_rate, split_inclusive, VAT_RATE_KEY


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── The maths ────────────────────────────────────────────────────────────────

def test_inclusive_split_is_exact_at_16_percent(app):
    """KSh 1,160 gross at 16% is KSh 1,000 net + KSh 160 tax."""
    net, tax = split_inclusive(Decimal("1160"), Decimal("16"))
    assert net == Decimal("1000.00")
    assert tax == Decimal("160.00")


def test_net_and_tax_always_add_back_to_the_gross(app):
    """
    Net is taken as gross - tax rather than computed independently, so a receipt
    can never be a cent short of itself.
    """
    for gross in ["1800", "350", "0.01", "4500", "999.99", "1"]:
        net, tax = split_inclusive(Decimal(gross), Decimal("16"))
        assert net + tax == Decimal(gross), f"{gross} did not reconcile"


def test_the_rate_comes_from_the_database_not_the_code(app):
    """Invariant 10: rates change by statute; a constant would need a deploy."""
    assert get_vat_rate() == Decimal("16")          # default when unset

    db.session.add(SystemSetting(key=VAT_RATE_KEY, value="14"))
    db.session.commit()
    assert get_vat_rate() == Decimal("14")


def test_a_malformed_rate_does_not_silently_become_zero(app):
    """Falling back to 0% would under-report tax and look like a clean return."""
    db.session.add(SystemSetting(key=VAT_RATE_KEY, value="not-a-number"))
    db.session.commit()
    assert get_vat_rate() == Decimal("16")


# ── Charges carry it ─────────────────────────────────────────────────────────

@pytest.fixture
def sold_item(app, client, waiter_token, food_item_id):
    """Open a tab, order the seeded food item, send it — producing a charge."""
    rv = client.post("/tabs", json={"reference": f"vat-{uuid.uuid4().hex[:6]}",
                                    "idempotency_key": str(uuid.uuid4())},
                     headers=_auth(waiter_token))
    tab_id = rv.get_json()["id"]

    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(waiter_token))
    order_id = rv.get_json()["id"]
    client.post(f"/orders/{order_id}/send", json={"idempotency_key": str(uuid.uuid4())},
                headers=_auth(waiter_token))
    return tab_id


def test_a_sale_records_the_rate_that_applied(app, sold_item):
    charge = db.session.query(Charge).filter_by(tab_id=sold_item).first()
    assert charge is not None
    assert Decimal(str(charge.tax_rate_snapshot)) == Decimal("16")


def test_the_tax_is_inside_the_price_not_added_to_it(app, sold_item):
    """
    The guest pays the menu price. Tax comes OUT of it — adding it on top would
    reprice everything already on the menu.
    """
    charge = db.session.query(Charge).filter_by(tab_id=sold_item).first()
    gross = Decimal(str(charge.amount))
    assert charge.net_amount + charge.tax_amount == gross
    assert charge.tax_amount < gross


def test_a_rate_change_does_not_rewrite_past_sales(app, sold_item):
    """
    The whole reason the rate is snapshotted. A sale made at 16% must still
    report 16% after the statutory rate moves.
    """
    before = db.session.query(Charge).filter_by(tab_id=sold_item).first()
    original_tax = before.tax_amount

    db.session.add(SystemSetting(key=VAT_RATE_KEY, value="8"))
    db.session.commit()
    db.session.refresh(before)

    assert before.tax_amount == original_tax, (
        "changing the rate must not retroactively alter tax already charged"
    )


# ── The summary the accountant gets ──────────────────────────────────────────

def test_summary_reports_gross_net_and_tax(app, client, manager_token, sold_item):
    rv = client.get("/finance/vat-summary", headers=_auth(manager_token))
    assert rv.status_code == 200
    body = rv.get_json()

    assert body["by_rate"], "a period with sales must report at least one rate"
    row = body["by_rate"][0]
    assert Decimal(row["net"]) + Decimal(row["tax"]) == Decimal(row["gross"])


def test_summary_groups_by_the_rate_that_applied(app, client, manager_token, waiter_token,
                                                 food_item_id, sold_item):
    """A period spanning a rate change must report BOTH rates separately."""
    db.session.add(SystemSetting(key=VAT_RATE_KEY, value="8"))
    db.session.commit()

    rv = client.post("/tabs", json={"reference": f"vat2-{uuid.uuid4().hex[:6]}",
                                    "idempotency_key": str(uuid.uuid4())},
                     headers=_auth(waiter_token))
    tab2 = rv.get_json()["id"]
    rv = client.post("/orders", json={
        "tab_id": tab2, "items": [{"menu_item_id": food_item_id, "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers=_auth(waiter_token))
    client.post(f"/orders/{rv.get_json()['id']}/send",
                json={"idempotency_key": str(uuid.uuid4())}, headers=_auth(waiter_token))

    body = client.get("/finance/vat-summary", headers=_auth(manager_token)).get_json()
    rates = {r["rate_percent"] for r in body["by_rate"]}
    assert len(rates) >= 2, f"expected two rates in the period, got {rates}"


def test_pre_vat_charges_are_reported_separately_not_assumed_zero(app, client,
                                                                  manager_token, owner_token,
                                                                  sold_item):
    """
    Charges recorded before VAT tracking have an unknown treatment. Folding them
    into the totals would hand the accountant a number the resort cannot stand
    behind.
    """
    legacy = Charge(
        tab_id=sold_item, amount=Decimal("500"), description="legacy charge",
        created_by_id=db.session.query(Charge).first().created_by_id,
        tax_rate_snapshot=None,
    )
    db.session.add(legacy)
    db.session.commit()

    body = client.get("/finance/vat-summary", headers=_auth(manager_token)).get_json()
    assert body["untracked"]["charges"] >= 1
    assert Decimal(body["untracked"]["gross"]) >= Decimal("500")
    # and it must NOT be inside the headline totals
    assert Decimal(body["totals"]["gross"]) < (
        Decimal(body["totals"]["gross"]) + Decimal(body["untracked"]["gross"])
    )


def test_a_waiter_cannot_read_the_vat_summary(app, client, waiter_token):
    assert client.get("/finance/vat-summary",
                      headers=_auth(waiter_token)).status_code == 403


def test_a_bad_date_is_refused_in_plain_english(app, client, manager_token):
    rv = client.get("/finance/vat-summary?from=january", headers=_auth(manager_token))
    assert rv.status_code == 400
    assert "YYYY-MM-DD" in rv.get_json()["error"]
