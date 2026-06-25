"""
Supplier — vendors who supply goods to the resort.
Tracks contact info, what they supply, and payment terms.
Soft-delete via is_active (invariant #6: disable, never delete).
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_person = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    # Comma-separated list, e.g. "vegetables, dairy, spirits"
    items_supplied = db.Column(db.String(500), nullable=True)
    # e.g. "Net 30", "COD"
    payment_terms = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.String(500), nullable=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Supplier {self.name} active={self.is_active}>"
