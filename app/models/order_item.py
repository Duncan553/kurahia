"""
OrderItem — a single line on an order.

unit_price_snapshot: price captured at order time so price changes
never rewrite history. This is the price used in Charge creation.

prep_station_snapshot: copied from MenuItem at order time so if the
item's routing changes, old orders still show the right station.

Lifecycle:
  Routed (KITCHEN/BAR): PENDING → RECEIVED → READY → SERVED
  Direct (NONE):        PENDING → (immediately SERVED on order.send)

Valid cancel targets: PENDING or RECEIVED (not SERVED).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class OrderItemStatus(str, enum.Enum):
    PENDING   = "PENDING"
    RECEIVED  = "RECEIVED"
    READY     = "READY"
    SERVED    = "SERVED"
    CANCELLED = "CANCELLED"


# Allowed forward transitions for routed items
VALID_TRANSITIONS = {
    OrderItemStatus.PENDING:  {OrderItemStatus.RECEIVED, OrderItemStatus.CANCELLED},
    OrderItemStatus.RECEIVED: {OrderItemStatus.READY,    OrderItemStatus.CANCELLED},
    OrderItemStatus.READY:    {OrderItemStatus.SERVED},
    OrderItemStatus.SERVED:   set(),   # terminal
    OrderItemStatus.CANCELLED: set(),  # terminal
}


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id       = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=False, index=True)
    menu_item_id = db.Column(db.String(36), db.ForeignKey("menu_items.id"), nullable=False)

    quantity              = db.Column(db.Numeric(8, 2), nullable=False)
    unit_price_snapshot   = db.Column(db.Numeric(14, 2), nullable=False)  # price at order time
    prep_station_snapshot = db.Column(db.String(10),     nullable=False)  # routing at order time

    status = db.Column(db.String(12), nullable=False, default=OrderItemStatus.PENDING.value)

    # Timestamps for each state transition (UTC, server-stamped)
    created_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    received_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    ready_at     = db.Column(db.DateTime(timezone=True), nullable=True)
    served_at    = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)

    cancel_reason = db.Column(db.Text, nullable=True)

    order     = db.relationship("Order", back_populates="items", lazy="select")
    menu_item = db.relationship("MenuItem", lazy="select")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_orderitem_qty_pos"),
    )

    def can_transition_to(self, new_status: OrderItemStatus) -> bool:
        current = OrderItemStatus(self.status)
        return new_status in VALID_TRANSITIONS.get(current, set())

    def __repr__(self):
        return f"<OrderItem {self.status} qty={self.quantity} item={self.menu_item_id}>"
