"""
consumption.py — Recipe-based auto-consumption for POS order fulfillment.

consume_order_item(oi, actor):
  Called when an OrderItem moves to READY.
  Writes StockMovement(SALE, -qty) per active RecipeLine ingredient.
  Quantity = line.quantity × order_item.quantity (e.g. 0.3 kg × 2 dishes = 0.6 kg).
  If no recipe: queues a no-recipe alert to the head chef so they add one.
  After each movement: fires a low-stock notification if stock drops below reorder_level.

reverse_consumption(oi, actor):
  Called when a READY item is subsequently cancelled.
  Writes equal positive movements to undo the deduction.

Both functions must be called inside the caller's begin_nested() transaction.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.extensions import db
from app.models.stock_movement import StockMovement, MovementReason
from app.models.recipe_line import RecipeLine
from app.models.inventory_item import InventoryItem
from app.models.notification import Notification, NotificationStatus, NotificationReferenceType
from app.services.stock import get_current_stock


def consume_order_item(oi, actor):
    """
    Auto-deduct ingredients when kitchen/bar marks an order item READY.
    Idempotency key per (order_item, ingredient) so a double-mark is harmless.
    """
    lines = db.session.query(RecipeLine).filter_by(
        menu_item_id=oi.menu_item_id, is_active=True
    ).all()

    if not lines:
        _notify_no_recipe(oi, actor)
        return

    order_qty = Decimal(str(oi.quantity))
    for line in lines:
        inv_item = db.session.get(InventoryItem, line.inventory_item_id)
        if not inv_item:
            continue

        recipe_qty = Decimal(str(line.quantity))
        stock_qty = inv_item.recipe_to_stock(recipe_qty)
        deduct = -(stock_qty * order_qty)  # negative = stock out
        idem   = f"sale-{oi.id}-{inv_item.id}"

        # Idempotency: DB UNIQUE constraint is the hard guard; this is the soft check
        if db.session.query(StockMovement).filter_by(idempotency_key=idem).first():
            continue

        db.session.add(StockMovement(
            item_id=inv_item.id,
            change_amount=deduct,
            reason=MovementReason.SALE.value,
            actor_id=actor.id,
            notes=f"Auto-consumption: order_item={oi.id}",
            idempotency_key=idem,
        ))
        db.session.flush()  # so get_current_stock sees the new row
        _check_low_stock(inv_item, actor)


def reverse_consumption(oi, actor):
    """
    Un-deduct ingredients when a READY order item is cancelled by a manager.
    Positive movement per ingredient — same amounts as the original deduction.
    """
    lines = db.session.query(RecipeLine).filter_by(
        menu_item_id=oi.menu_item_id, is_active=True
    ).all()

    order_qty = Decimal(str(oi.quantity))
    for line in lines:
        inv_item = db.session.get(InventoryItem, line.inventory_item_id)
        if not inv_item:
            continue

        recipe_qty = Decimal(str(line.quantity))
        stock_qty = inv_item.recipe_to_stock(recipe_qty)
        restore = stock_qty * order_qty  # positive = stock back
        idem    = f"sale-reverse-{oi.id}-{inv_item.id}"

        if db.session.query(StockMovement).filter_by(idempotency_key=idem).first():
            continue

        db.session.add(StockMovement(
            item_id=inv_item.id,
            change_amount=restore,
            reason=MovementReason.SALE.value,
            actor_id=actor.id,
            notes=f"Reversal (cancel-after-ready): order_item={oi.id}",
            idempotency_key=idem,
        ))


def _check_low_stock(inv_item: InventoryItem, actor):
    """
    After a SALE movement, check if stock dropped below reorder_level.
    Queues a Notification to the owner (level 10). Skips if a low-stock
    notification was already sent for this item in the last 24 hours — avoids
    spam when the same item is sold repeatedly on a busy shift.
    """
    from app.models.user import User
    from app.models.role import Role

    current = get_current_stock(inv_item.id)
    if current >= Decimal(str(inv_item.reorder_level)):
        return

    owner = db.session.query(User).join(User.role).filter(
        Role.level >= 10, User.is_active == True
    ).first()
    if not owner:
        return

    # Dedup: skip if already notified in the last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    already = db.session.query(Notification).filter(
        Notification.recipient_user_id == owner.id,
        Notification.subject == f"Low stock: {inv_item.name}",
        Notification.scheduled_for_utc >= cutoff,
    ).first()
    if already:
        return

    db.session.add(Notification(
        recipient_user_id=owner.id,
        reference_type=NotificationReferenceType.GENERAL.value,
        subject=f"Low stock: {inv_item.name}",
        body=(
            f"{inv_item.name} has dropped to {current} {inv_item.unit} "
            f"(reorder level: {inv_item.reorder_level} {inv_item.unit}). Please reorder."
        ),
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    ))


def _notify_no_recipe(oi, actor):
    """
    When a menu item reaches READY but has no recipe, the ingredients cannot
    be auto-deducted. Alert the head chef (level-5 Kitchen user) so they add
    the recipe. Falls back to the owner if no head chef is found.
    """
    from app.models.user import User
    from app.models.role import Role
    from app.models.department import Department

    menu_item = oi.menu_item
    if not menu_item:
        return

    # Head of the prep department for this item's station
    station_dept = oi.prep_station_snapshot if oi.prep_station_snapshot else "Kitchen"
    recipient = (
        db.session.query(User)
        .join(User.role)
        .join(User.department)
        .filter(
            db.func.upper(Department.name) == station_dept.upper(),
            Role.level >= 5,
            User.is_active == True,
        )
        .first()
    )
    if not recipient:
        recipient = (
            db.session.query(User).join(User.role)
            .filter(Role.level >= 10, User.is_active == True)
            .first()
        )
    if not recipient:
        return

    idem = f"no-recipe-alert-{oi.menu_item_id}"
    if db.session.query(Notification).filter_by(idempotency_key=idem).first():
        return  # one alert per menu item is enough until the recipe is set

    db.session.add(Notification(
        recipient_user_id=recipient.id,
        reference_type=NotificationReferenceType.GENERAL.value,
        subject=f"No recipe: {menu_item.name}",
        body=(
            f"Order sold for '{menu_item.name}' but no recipe is set. "
            f"Stock cannot be auto-deducted. Please add a recipe so inventory stays accurate."
        ),
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=idem,
    ))
