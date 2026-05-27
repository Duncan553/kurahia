"""
StockMovement — the single source of truth for all stock changes.
APPEND-ONLY. Never update or delete rows.

change_amount is signed:
  positive → stock in  (PURCHASE)
  negative → stock out (SPOILAGE, STAFF_MEAL, SENT_BACK, SALE_PLACEHOLDER)
  either   → COUNT (reconciliation), TRANSFER, ADJUSTMENT

current_stock(item) = SELECT SUM(change_amount) WHERE item_id = ?
That sum is the ONLY correct way to know current stock. Never cache it.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class MovementReason(str, enum.Enum):
    PURCHASE         = "PURCHASE"
    COUNT            = "COUNT"           # reconciliation after physical count
    SPOILAGE         = "SPOILAGE"
    STAFF_MEAL       = "STAFF_MEAL"
    SENT_BACK        = "SENT_BACK"
    TRANSFER         = "TRANSFER"
    ADJUSTMENT       = "ADJUSTMENT"
    SALE_PLACEHOLDER = "SALE_PLACEHOLDER"  # POS will write here when built


# Reasons that represent stock leaving (used by variance math)
CONSUMPTION_REASONS = {
    MovementReason.SPOILAGE,
    MovementReason.STAFF_MEAL,
    MovementReason.SENT_BACK,
    MovementReason.SALE_PLACEHOLDER,
}


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    change_amount = db.Column(db.Numeric(12, 4), nullable=False)  # signed
    reason = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    timestamp_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    notes = db.Column(db.Text, nullable=True)

    # Caller-supplied key; duplicate key → return existing row, no second write
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    item  = db.relationship("InventoryItem", lazy="select")
    actor = db.relationship("User", foreign_keys=[actor_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("change_amount != 0", name="ck_movement_nonzero"),
    )

    def __repr__(self):
        return f"<StockMovement {self.reason} {self.change_amount} item={self.item_id}>"
