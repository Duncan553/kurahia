"""
EventStockMovement — bridge between an EventInventoryAllocation and StockMovement.
Records exactly which physical stock move corresponds to this allocation step.
ISSUE: items leave main store for the event.
RETURN: leftover items come back.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class EventMovementType(str, enum.Enum):
    ISSUE  = "ISSUE"
    RETURN = "RETURN"


class EventStockMovement(db.Model):
    __tablename__ = "event_stock_movements"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    allocation_id = db.Column(db.String(36),
                              db.ForeignKey("event_inventory_allocations.id"),
                              nullable=False, index=True)
    movement_id   = db.Column(db.String(36), db.ForeignKey("stock_movements.id"),
                              nullable=False, unique=True)
    movement_type = db.Column(db.String(10), nullable=False)   # ISSUE / RETURN

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    allocation = db.relationship("EventInventoryAllocation",
                                 back_populates="stock_movements", lazy="select")
    movement   = db.relationship("StockMovement", lazy="select")

    def __repr__(self):
        return f"<EventStockMovement {self.movement_type} alloc={self.allocation_id}>"
