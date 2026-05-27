"""
Purchase — a completed purchase with a mandatory receipt photo.
Recording a Purchase also triggers a PURCHASE StockMovement (handled in the route).
receipt_photo_path must be non-empty — rejected without it (DB + app check).
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Purchase(db.Model):
    __tablename__ = "purchases"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Links to the approval chain (optional — ad-hoc purchases allowed)
    purchase_request_id = db.Column(
        db.String(36), db.ForeignKey("purchase_requests.id"), nullable=True
    )

    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False)
    quantity = db.Column(db.Numeric(12, 4), nullable=False)
    actual_cost = db.Column(db.Numeric(14, 2), nullable=False)

    # Mandatory — no purchase recorded without a receipt
    receipt_photo_path = db.Column(db.String(500), nullable=False)

    supplier_name = db.Column(db.String(200), nullable=True)   # full supplier table later
    recorded_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    # Three timestamps in the purchase lifecycle
    timestamp_asked     = db.Column(db.DateTime(timezone=True), nullable=True)
    timestamp_delivered = db.Column(db.DateTime(timezone=True), nullable=True)
    timestamp_added     = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    # FK to the StockMovement created when this purchase was recorded
    movement_id = db.Column(
        db.String(36), db.ForeignKey("stock_movements.id"), nullable=True
    )

    item            = db.relationship("InventoryItem", lazy="select")
    recorded_by     = db.relationship("User", foreign_keys=[recorded_by_id], lazy="select")
    purchase_request = db.relationship("PurchaseRequest", lazy="select")

    __table_args__ = (
        db.CheckConstraint("quantity > 0",     name="ck_purchase_qty_pos"),
        db.CheckConstraint("actual_cost >= 0", name="ck_purchase_cost_nonneg"),
    )

    def __repr__(self):
        return f"<Purchase item={self.item_id} qty={self.quantity} cost={self.actual_cost}>"
