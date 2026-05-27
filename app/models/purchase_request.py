"""
PurchaseRequest — a department's request to buy more stock.
Approval chain: dept-head creates → manager proposes budget → owner approves.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class RequestStatus(str, enum.Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    FULFILLED = "FULFILLED"


class PurchaseRequest(db.Model):
    __tablename__ = "purchase_requests"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # item_id is nullable — requestor may describe a new item not yet catalogued
    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=True)
    item_description = db.Column(db.String(200), nullable=True)  # free-text fallback

    quantity = db.Column(db.Numeric(12, 4), nullable=False)
    estimated_cost = db.Column(db.Numeric(14, 2), nullable=True)  # set by manager at propose step

    requested_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=RequestStatus.PENDING)

    # Set at propose step
    manager_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    manager_notes = db.Column(db.Text, nullable=True)

    # Set at approve/reject step
    owner_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    owner_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    item         = db.relationship("InventoryItem", lazy="select")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id], lazy="select")
    manager      = db.relationship("User", foreign_keys=[manager_id], lazy="select")
    owner        = db.relationship("User", foreign_keys=[owner_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_preq_qty_pos"),
        db.CheckConstraint(
            "item_id IS NOT NULL OR item_description IS NOT NULL",
            name="ck_preq_item_or_desc",
        ),
    )

    def __repr__(self):
        return f"<PurchaseRequest {self.status} qty={self.quantity}>"
