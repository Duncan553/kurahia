"""
Order — a round of items placed against a Tab.
DRAFT → can still add items; not yet in the prep queue.
SENT  → charges created; routed items visible in kitchen/bar queue.
FULLY_SERVED → all items SERVED or CANCELLED (set automatically).
CANCELLED → whole order voided before being sent.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class OrderStatus(str, enum.Enum):
    DRAFT        = "DRAFT"
    SENT         = "SENT"
    FULLY_SERVED = "FULLY_SERVED"
    CANCELLED    = "CANCELLED"


class Order(db.Model):
    __tablename__ = "orders"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tab_id      = db.Column(db.String(36), db.ForeignKey("tabs.id"), nullable=False, index=True)
    status      = db.Column(db.String(20), nullable=False, default=OrderStatus.DRAFT.value)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at      = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    tab        = db.relationship("Tab", lazy="select")
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")
    items      = db.relationship("OrderItem", back_populates="order", lazy="dynamic")

    def __repr__(self):
        return f"<Order {self.status} tab={self.tab_id}>"
