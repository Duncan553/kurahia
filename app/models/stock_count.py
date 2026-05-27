"""
StockCount — immutable snapshot of a physical count.
Used as opening/closing anchors in the variance formula.
Submitting a count also creates a COUNT StockMovement to reconcile
the derived stock level with physical reality.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class CountType(str, enum.Enum):
    DAILY         = "DAILY"
    WEEKLY        = "WEEKLY"
    OPENING       = "OPENING"
    CLOSING       = "CLOSING"
    SPECIAL_AUDIT = "SPECIAL_AUDIT"


class StockCount(db.Model):
    __tablename__ = "stock_counts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    counted_amount = db.Column(db.Numeric(12, 4), nullable=False)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    timestamp_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    count_type = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    item  = db.relationship("InventoryItem", lazy="select")
    actor = db.relationship("User", foreign_keys=[actor_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("counted_amount >= 0", name="ck_count_nonneg"),
    )

    def __repr__(self):
        return f"<StockCount {self.count_type} {self.counted_amount} item={self.item_id}>"
