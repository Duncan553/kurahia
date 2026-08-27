"""
Menu engineering — the Kasavana-Smith matrix.

Two axes, both measured against the MENU'S OWN AVERAGE rather than an industry
benchmark, because "profitable" means profitable for this menu:

    popular + profitable      STAR       protect it
    popular + unprofitable    PLOWHORSE  fix the cost or nudge the price
    unpopular + profitable    PUZZLE     promote it
    unpopular + unprofitable  DOG        take it off

The axis is CONTRIBUTION MARGIN in shillings, not food-cost percentage. A dish
at 20% food cost sounds better than one at 40%, but if the first sells for 300
and the second for 1,800, the second puts far more money in the bank.
Percentage describes a dish; contribution margin describes the business.
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.department import Department
from app.models.inventory_item import InventoryItem
from app.models.menu_item import MenuItem, PrepStation
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.recipe_line import RecipeLine


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _dish(name, price, cost, dept_id, owner_id):
    """A dish whose recipe costs exactly `cost`, so margin is predictable."""
    ing = InventoryItem(name=f"{name} ingredient", unit="kg",
                        department_id=dept_id, cost_per_unit=Decimal(str(cost)))
    db.session.add(ing)
    db.session.flush()

    item = MenuItem(name=name, price=Decimal(str(price)), category="Test",
                    prep_station=PrepStation.KITCHEN.value, department_id=dept_id)
    db.session.add(item)
    db.session.flush()

    db.session.add(RecipeLine(menu_item_id=item.id, inventory_item_id=ing.id,
                              quantity=Decimal("1"), unit="kg"))
    db.session.commit()
    return item.id


def _sell(menu_item_id, units, order_id):
    """Record `units` as SERVED — the only status that counts as a sale."""
    from datetime import datetime, timezone
    db.session.add(OrderItem(
        order_id=order_id, menu_item_id=menu_item_id,
        quantity=Decimal(str(units)),
        unit_price_snapshot=Decimal("1"),
        prep_station_snapshot=PrepStation.KITCHEN.value,
        status=OrderItemStatus.SERVED.value,
        served_at=datetime.now(timezone.utc),
    ))
    db.session.commit()


@pytest.fixture
def a_menu(app, client, waiter_token, food_item_id):
    """Four dishes spanning the matrix, plus an order to hang sales on."""
    from app.models.user import User
    from app.models.order import Order
    dept = db.session.query(Department).filter_by(name="General").first().id
    owner_id = db.session.query(User).filter_by(username="owner1").first().id

    rv = client.post("/tabs", json={"reference": f"me-{uuid.uuid4().hex[:6]}",
                                    "idempotency_key": str(uuid.uuid4())},
                     headers=_auth(waiter_token))
    tab_id = rv.get_json()["id"]
    order = Order(tab_id=tab_id, created_by_id=owner_id,
                  idempotency_key=str(uuid.uuid4()))
    db.session.add(order)
    db.session.commit()

    ids = {
        # price, cost -> margin
        "star":      _dish("Star Dish", 2000, 400, dept, owner_id),    # margin 1600
        "plowhorse": _dish("Plow Dish", 500, 400, dept, owner_id),     # margin 100
        "puzzle":    _dish("Puzzle Dish", 2000, 400, dept, owner_id),  # margin 1600
        "dog":       _dish("Dog Dish", 500, 400, dept, owner_id),      # margin 100
    }
    _sell(ids["star"], 50, order.id)        # popular
    _sell(ids["plowhorse"], 50, order.id)   # popular
    _sell(ids["puzzle"], 1, order.id)       # unpopular
    _sell(ids["dog"], 1, order.id)          # unpopular
    return ids


def _classify(client, token):
    rv = client.get("/finance/menu-engineering", headers=_auth(token))
    assert rv.status_code == 200, rv.get_json()
    body = rv.get_json()
    lookup = {}
    for kind, rows in body["items"].items():
        for r in rows:
            lookup[r["name"]] = kind
    return body, lookup


def test_the_four_quadrants_are_classified_correctly(app, client, manager_token, a_menu):
    _, kind = _classify(client, manager_token)
    assert kind["Star Dish"] == "STAR"
    assert kind["Plow Dish"] == "PLOWHORSE"
    assert kind["Puzzle Dish"] == "PUZZLE"
    assert kind["Dog Dish"] == "DOG"


def test_contribution_margin_is_shillings_not_a_percentage(app, client, manager_token, a_menu):
    """
    The distinction that matters. Star and Plow have very different food-cost
    percentages (20% vs 80%) but the axis is the actual money per sale.
    """
    body, _ = _classify(client, manager_token)
    star = next(r for rows in body["items"].values() for r in rows if r["name"] == "Star Dish")
    assert Decimal(star["contribution_margin"]) == Decimal("1600")
    assert Decimal(star["total_contribution"]) == Decimal("1600") * Decimal("50")


def test_every_item_carries_an_action_not_just_a_label(app, client, manager_token, a_menu):
    """A classification nobody knows what to do with is trivia."""
    body, _ = _classify(client, manager_token)
    for rows in body["items"].values():
        for r in rows:
            assert r["action"], f"{r['name']} has no action"


def test_thresholds_are_the_menus_own_averages(app, client, manager_token, a_menu):
    """The matrix is relative by design — profitable FOR THIS MENU."""
    body, _ = _classify(client, manager_token)
    t = body["thresholds"]
    assert Decimal(t["avg_units_sold"]) > 0
    assert Decimal(t["avg_contribution_margin"]) > 0


def test_items_without_a_recipe_are_not_classified(app, client, manager_token, a_menu):
    """
    Their food cost is unknown, so any margin would be invented — and an
    invented number here drives a real decision to delist a dish.
    """
    body, kind = _classify(client, manager_token)
    # The seeded menu items have no recipes, so they must land here.
    assert body["unclassified"]["count"] >= 1
    for r in body["unclassified"]["items"]:
        assert r["name"] not in kind, "an unpriced item must not be classified"
        assert "no recipe" in r["reason"].lower()


def test_only_SERVED_units_count_as_sales(app, client, manager_token, a_menu, waiter_token):
    """A cancelled plate is not a sale; counting it inflates popularity."""
    from app.models.order import Order
    from datetime import datetime, timezone

    body_before, _ = _classify(client, manager_token)
    puzzle_before = next(r for rows in body_before["items"].values()
                         for r in rows if r["name"] == "Puzzle Dish")

    order = db.session.query(Order).first()
    db.session.add(OrderItem(
        order_id=order.id, menu_item_id=a_menu["puzzle"], quantity=Decimal("500"),
        unit_price_snapshot=Decimal("1"), prep_station_snapshot=PrepStation.KITCHEN.value,
        status=OrderItemStatus.CANCELLED.value, served_at=datetime.now(timezone.utc),
    ))
    db.session.commit()

    body_after, _ = _classify(client, manager_token)
    puzzle_after = next(r for rows in body_after["items"].values()
                        for r in rows if r["name"] == "Puzzle Dish")
    assert puzzle_after["units_sold"] == puzzle_before["units_sold"], (
        "500 cancelled units must not turn a Puzzle into a Star"
    )


def test_a_waiter_cannot_read_it(app, client, waiter_token):
    assert client.get("/finance/menu-engineering",
                      headers=_auth(waiter_token)).status_code == 403


def test_a_bad_date_is_refused_in_plain_english(app, client, manager_token):
    rv = client.get("/finance/menu-engineering?from=soon", headers=_auth(manager_token))
    assert rv.status_code == 400
    assert "YYYY-MM-DD" in rv.get_json()["error"]
