"""
EventInventoryAllocation — how much of an item is earmarked for an event.
PLANNED:  manager declares what's needed.
ISSUED:   items physically moved from main store to event; triggers StockMovement.
RETURNED: leftover items brought back; triggers a counter StockMovement.
CONSUMED: event used everything (or close enough); no return.
Append-only transitions — never edits.
"""
import uuid
import enum
from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db


class AllocationStatus(str, enum.Enum):
    PLANNED  = "PLANNED"
    ISSUED   = "ISSUED"
    RETURNED = "RETURNED"
    CONSUMED = "CONSUMED"


VALID_ALLOCATION_TRANSITIONS: dict[str, set] = {
    AllocationStatus.PLANNED.value:  {AllocationStatus.ISSUED.value},
    AllocationStatus.ISSUED.value:   {AllocationStatus.RETURNED.value,
                                      AllocationStatus.CONSUMED.value},
    AllocationStatus.RETURNED.value: set(),
    AllocationStatus.CONSUMED.value: set(),
}


class EventInventoryAllocation(db.Model):
    __tablename__ = "event_inventory_allocations"

    id                 = db.Column(db.String(36), primary_key=True,
                                   default=lambda: str(uuid.uuid4()))
    event_id           = db.Column(db.String(36), db.ForeignKey("events.id"),
                                   nullable=False, index=True)
    inventory_item_id  = db.Column(db.String(36), db.ForeignKey("inventory_items.id"),
                                   nullable=False)
    allocated_quantity = db.Column(db.Numeric(12, 4), nullable=False)
    notes              = db.Column(db.Text, nullable=True)
    status             = db.Column(db.String(10), nullable=False,
                                   default=AllocationStatus.PLANNED.value)
    idempotency_key    = db.Column(db.String(128), nullable=False, unique=True)
    created_by_id      = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    event          = db.relationship("Event", back_populates="allocations", lazy="select")
    inventory_item = db.relationship("InventoryItem", lazy="select")
    created_by     = db.relationship("User", foreign_keys=[created_by_id], lazy="select")
    stock_movements = db.relationship("EventStockMovement", back_populates="allocation",
                                      lazy="dynamic")

    __table_args__ = (
        db.CheckConstraint("allocated_quantity > 0", name="ck_alloc_qty_pos"),
    )

    def __repr__(self):
        return f"<EventInventoryAllocation event={self.event_id} item={self.inventory_item_id} {self.status}>"
