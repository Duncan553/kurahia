"""
Inventory must not leak through direct-service departments.

consume_order_item() is what turns a sale into StockMovement rows. It was called
from exactly ONE place: the READY transition (app/pos/orders.py). Kitchen and bar
items pass through READY, so they deducted correctly.

Direct-service items — prep_station NONE, which is how spa treatments, water
activities and every other non-kitchen service are modelled — are set straight to
SERVED when the order is sent and never touch READY. So they deducted NOTHING.

Worse, the safety net missed too: when a menu item has no recipe,
consume_order_item notifies the head chef to add one. For NONE items that
function was never called at all, so the gap was completely silent.
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.menu_item import MenuItem, PrepStation, StockTracking
from app.models.recipe_line import RecipeLine
from app.models.stock_movement import StockMovement, MovementReason
from app.services.stock import get_current_stock


@pytest.fixture
def spa_service(app):
    """A spa treatment (prep_station NONE) whose recipe consumes massage oil."""
    from app.models.department import Department
    from app.models.user import User
    dept = db.session.query(Department).filter_by(name="General").first()
    owner_id = db.session.query(User).filter_by(username="owner1").first().id

    oil = InventoryItem(
        name="Massage Oil", unit="ml", department_id=dept.id,
        cost_per_unit=Decimal("2"), reorder_level=Decimal("100"),
    )
    db.session.add(oil)
    db.session.flush()

    # Opening stock, so there is something to draw down.
    db.session.add(StockMovement(
        item_id=oil.id, change_amount=Decimal("1000"),
        reason=MovementReason.PURCHASE.value,
        actor_id=owner_id,          # NOT NULL — every movement names who caused it
        idempotency_key=str(uuid.uuid4()),
    ))

    # RECIPE, because this fixture attaches RecipeLine rows straight to the DB.
    # Through the API, POST /menu/items/<id>/recipe sets this for you; building
    # the rows by hand skips that, and an item left UNTRACKED cannot be sold.
    service = MenuItem(
        name="Deep Tissue Massage", price="4500", category="Spa",
        prep_station=PrepStation.NONE.value, department_id=dept.id,
        stock_tracking=StockTracking.RECIPE.value,
    )
    db.session.add(service)
    db.session.flush()

    db.session.add(RecipeLine(
        menu_item_id=service.id, inventory_item_id=oil.id,
        quantity=Decimal("50"), unit="ml",
    ))
    db.session.commit()
    return {"service_id": service.id, "oil_id": oil.id}


def _open_tab(client, token) -> str:
    rv = client.post("/tabs", json={"reference": f"spa-{uuid.uuid4().hex[:6]}",
                                    "idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


def _order_and_send(client, token, tab_id, menu_item_id, qty=1) -> str:
    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": menu_item_id, "quantity": qty}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 201, rv.get_json()
    order_id = rv.get_json()["id"]

    rv = client.post(f"/orders/{order_id}/send", json={"idempotency_key": str(uuid.uuid4())},
                     headers={"Authorization": f"Bearer {token}"})
    assert rv.status_code == 200, rv.get_json()
    return order_id


def test_direct_service_deducts_its_ingredients(app, client, waiter_token, spa_service):
    """THE REGRESSION: a spa treatment must draw its oil down like any other sale."""
    before = get_current_stock(spa_service["oil_id"])

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, spa_service["service_id"])

    after = get_current_stock(spa_service["oil_id"])
    assert after == before - Decimal("50"), (
        f"a served spa treatment must consume 50ml of oil, but stock went "
        f"{before} -> {after}. Direct-service items never pass through READY, so "
        f"if consumption only fires there, every non-kitchen department leaks."
    )

    move = db.session.query(StockMovement).filter_by(
        item_id=spa_service["oil_id"], reason=MovementReason.SALE.value
    ).one()
    assert Decimal(str(move.change_amount)) == Decimal("-50")


def test_quantity_multiplies_the_recipe(app, client, waiter_token, spa_service):
    """Two treatments must consume twice the oil."""
    before = get_current_stock(spa_service["oil_id"])

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, spa_service["service_id"], qty=2)

    assert get_current_stock(spa_service["oil_id"]) == before - Decimal("100")


def test_a_served_direct_service_cannot_be_cancelled_and_keeps_its_stock(app, client, owner_token, spa_service):
    """
    A performed service is terminal. The oil is already on the guest's back — a
    refund returns the MONEY, it does not put the oil back in the bottle.
    /refund reverses the charge only, and that is correct.
    """
    from app.models.order import Order
    from app.models.order_item import OrderItem

    before = get_current_stock(spa_service["oil_id"])
    tab_id = _open_tab(client, owner_token)
    _order_and_send(client, owner_token, tab_id, spa_service["service_id"])
    assert get_current_stock(spa_service["oil_id"]) == before - Decimal("50")

    order = db.session.query(Order).filter_by(tab_id=tab_id).first()
    oi = db.session.query(OrderItem).filter_by(order_id=order.id).first()

    rv = client.post(f"/order-items/{oi.id}/cancel", json={"reason": "changed mind"},
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 400
    assert "SERVED" in rv.get_json()["error"]

    assert get_current_stock(spa_service["oil_id"]) == before - Decimal("50"), (
        "a rejected cancellation must not move stock"
    )


def test_cancelling_a_direct_service_BEFORE_send_does_not_invent_stock(app, client, owner_token, spa_service):
    """
    The mirror-image leak, and a bug I introduced fixing the first one.

    A NONE item consumes at SEND. If it is cancelled while still PENDING nothing
    has been deducted yet, so a reversal guarded only on "is this a NONE item"
    would write a POSITIVE movement and invent stock that never left.
    """
    from app.models.order import Order
    from app.models.order_item import OrderItem

    before = get_current_stock(spa_service["oil_id"])

    tab_id = _open_tab(client, owner_token)
    rv = client.post("/orders", json={
        "tab_id": tab_id,
        "items": [{"menu_item_id": spa_service["service_id"], "quantity": 1}],
        "idempotency_key": str(uuid.uuid4()),
    }, headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 201
    # deliberately NOT sent — the item is PENDING and nothing is consumed
    assert get_current_stock(spa_service["oil_id"]) == before

    order = db.session.query(Order).filter_by(tab_id=tab_id).first()
    oi = db.session.query(OrderItem).filter_by(order_id=order.id).first()

    rv = client.post(f"/order-items/{oi.id}/cancel", json={"reason": "mistake"},
                     headers={"Authorization": f"Bearer {owner_token}"})
    assert rv.status_code == 200, rv.get_json()

    assert get_current_stock(spa_service["oil_id"]) == before, (
        "cancelling before send must leave stock untouched — reversing here would "
        "invent 50ml of oil that was never deducted"
    )


def test_direct_service_without_a_recipe_alerts_the_head_chef(app, client, waiter_token):
    """
    The safety net. An untracked service must not fail silently — the head chef
    is told to add a recipe. This never fired for NONE items before, because
    consume_order_item was not called for them at all.
    """
    from app.models.department import Department
    from app.models.notification import Notification

    dept = db.session.query(Department).filter_by(name="General").first()
    # Deliberately RECIPE with NO recipe lines — that is exactly the state this
    # test is about: an item declared as consuming ingredients that has none,
    # which must alert the head chef rather than deduct nothing in silence.
    service = MenuItem(
        name="Sunset Boat Cruise", price="3000", category="Water",
        prep_station=PrepStation.NONE.value, department_id=dept.id,
        stock_tracking=StockTracking.RECIPE.value,
    )
    db.session.add(service)
    db.session.commit()

    before = db.session.query(Notification).count()

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, service.id)

    assert db.session.query(Notification).count() > before, (
        "a sale with no recipe must raise a no-recipe notification so the gap is "
        "visible instead of silently untracked"
    )


# ── DIRECT depletion: the "Tusker / apple" case ──────────────────────────────
# A pass-through item IS an inventory item — selling one deducts exactly one
# unit. This is the standard one-to-one depletion bar systems use for bottled
# stock. Forcing a one-line "recipe" onto a beer is the wrong workflow, so
# MenuItem.inventory_item_id links them directly.

@pytest.fixture
def bottled_beer(app):
    """A Tusker: the menu item and the stock item are the same object."""
    from app.models.department import Department
    from app.models.user import User
    dept = db.session.query(Department).filter_by(name="Bar").first()
    owner_id = db.session.query(User).filter_by(username="owner1").first().id

    stock = InventoryItem(
        name="Tusker 500ml", unit="bottle", department_id=dept.id,
        cost_per_unit=Decimal("180"), reorder_level=Decimal("24"),
    )
    db.session.add(stock)
    db.session.flush()
    db.session.add(StockMovement(
        item_id=stock.id, change_amount=Decimal("100"),
        reason=MovementReason.PURCHASE.value, actor_id=owner_id,
        idempotency_key=str(uuid.uuid4()),
    ))

    item = MenuItem(
        name="Tusker", price="350", category="Beer",
        prep_station=PrepStation.NONE.value, department_id=dept.id,
        inventory_item_id=stock.id,          # <- the direct link
        stock_tracking=StockTracking.DIRECT.value,   # ...and what it means
    )
    db.session.add(item)
    db.session.commit()
    return {"menu_id": item.id, "stock_id": stock.id}


def test_a_pass_through_item_deducts_one_unit_per_sale(app, client, waiter_token, bottled_beer):
    before = get_current_stock(bottled_beer["stock_id"])

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, bottled_beer["menu_id"], qty=3)

    assert get_current_stock(bottled_beer["stock_id"]) == before - Decimal("3"), (
        "selling 3 Tuskers must take 3 bottles off the shelf — no recipe required"
    )

    move = db.session.query(StockMovement).filter_by(
        item_id=bottled_beer["stock_id"], reason=MovementReason.SALE.value
    ).one()
    assert Decimal(str(move.change_amount)) == Decimal("-3")


def test_a_pass_through_sale_raises_no_missing_recipe_warning(app, client, waiter_token, bottled_beer):
    """A directly-linked item is fully tracked, so it must NOT be flagged."""
    from app.models.notification import Notification
    before = db.session.query(Notification).count()

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, bottled_beer["menu_id"])

    assert db.session.query(Notification).count() == before, (
        "a direct-linked item is tracked — warning about a missing recipe would "
        "train staff to ignore the alert that matters"
    )


def test_a_recipe_wins_over_a_direct_link(app, client, waiter_token, bottled_beer):
    """
    If someone sets BOTH, the recipe is authoritative: it is the more specific
    statement of what the sale consumes.
    """
    from app.models.department import Department
    from app.models.user import User
    dept = db.session.query(Department).filter_by(name="Bar").first()
    owner_id = db.session.query(User).filter_by(username="owner1").first().id

    garnish = InventoryItem(name="Lime Wedge", unit="piece", department_id=dept.id,
                            cost_per_unit=Decimal("5"))
    db.session.add(garnish)
    db.session.flush()
    db.session.add(StockMovement(
        item_id=garnish.id, change_amount=Decimal("50"),
        reason=MovementReason.PURCHASE.value, actor_id=owner_id,
        idempotency_key=str(uuid.uuid4()),
    ))
    db.session.add(RecipeLine(
        menu_item_id=bottled_beer["menu_id"], inventory_item_id=garnish.id,
        quantity=Decimal("1"), unit="piece",
    ))
    db.session.commit()

    bottles_before = get_current_stock(bottled_beer["stock_id"])
    limes_before   = get_current_stock(garnish.id)

    tab_id = _open_tab(client, waiter_token)
    _order_and_send(client, waiter_token, tab_id, bottled_beer["menu_id"])

    assert get_current_stock(garnish.id) == limes_before - Decimal("1")
    assert get_current_stock(bottled_beer["stock_id"]) == bottles_before, (
        "the recipe is the more specific statement; the direct link must not "
        "double-deduct on top of it"
    )
