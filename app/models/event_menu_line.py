"""
EventMenuLine — one dish (or drink) an event has planned, and how many.

An event is a special customer. Its food is planned ahead by a manager
(dish × plates) so the store can be checked before the day, then SENT as real
orders on the event's own bill — which is what puts it on the kitchen board,
moves stock on READY, and keeps it inside the theft checks.

A discount is recorded, never typed in as a lower price: the line keeps the
menu price, the discount per plate, the reason and who gave it. The charged
price is derived. That is what lets the owner see what was given away.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db


class EventMenuLine(db.Model):
    __tablename__ = "event_menu_lines"

    id                = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id          = db.Column(db.String(36), db.ForeignKey("events.id"), nullable=False, index=True)
    menu_item_id      = db.Column(db.String(36), db.ForeignKey("menu_items.id"), nullable=False)
    quantity          = db.Column(db.Numeric(8, 2), nullable=False)
    # The head chef's price when the line was planned — frozen, like an order line.
    menu_price        = db.Column(db.Numeric(14, 2), nullable=False)
    discount_per_unit = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    discount_reason   = db.Column(db.String(200), nullable=True)
    discount_by_id    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    # Set when the line goes to the kitchen/bar. A sent line is history.
    order_item_id     = db.Column(db.String(36), db.ForeignKey("order_items.id"), nullable=True)
    is_active         = db.Column(db.Boolean, nullable=False, default=True)
    created_by_id     = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at_utc    = db.Column(db.DateTime(timezone=True), nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    updated_at_utc    = db.Column(db.DateTime(timezone=True), nullable=True)

    event       = db.relationship("Event", lazy="select")
    menu_item   = db.relationship("MenuItem", lazy="select")
    discount_by = db.relationship("User", foreign_keys=[discount_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_eventmenu_qty_pos"),
        db.CheckConstraint("discount_per_unit >= 0", name="ck_eventmenu_discount_nonneg"),
        db.CheckConstraint("discount_per_unit <= menu_price", name="ck_eventmenu_discount_le_price"),
    )

    @property
    def charged_per_unit(self) -> Decimal:
        return Decimal(str(self.menu_price)) - Decimal(str(self.discount_per_unit))

    @property
    def is_sent(self) -> bool:
        return self.order_item_id is not None

    def __repr__(self):
        return f"<EventMenuLine {self.quantity} × {self.menu_item_id[:8]}>"
