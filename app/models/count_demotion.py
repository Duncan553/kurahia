"""
CountDemotion — append-only record of an item demoted from AUTO_CONFIRMED to MUST_COUNT.

Created automatically when a spot-check reveals variance on an item the system
previously trusted. The demotion is active for 4 weeks from demoted_at; after that,
the item must earn back AUTO_CONFIRMED status through clean counts.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class CountDemotion(db.Model):
    __tablename__ = "count_demotions"

    id             = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id        = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    demoted_at     = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    demoted_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    reason         = db.Column(db.String(50),  nullable=False, default="SPOT_CHECK_VARIANCE")
    # Idempotency key prevents double-demotion from the same count submission
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    item       = db.relationship("InventoryItem", lazy="select")
    demoted_by = db.relationship("User", foreign_keys=[demoted_by_id], lazy="select")

    def __repr__(self):
        return f"<CountDemotion item={self.item_id} at={self.demoted_at}>"
