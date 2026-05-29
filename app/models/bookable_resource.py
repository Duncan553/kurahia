"""
BookableResource — anything that can be reserved: villa, event field, water-activity slot.
base_price is a Decimal snapshot reference; the Booking stores its own base_total snapshot.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class ResourceType(str, enum.Enum):
    VILLA          = "VILLA"
    EVENT_VENUE    = "EVENT_VENUE"
    WATER_ACTIVITY = "WATER_ACTIVITY"
    OTHER          = "OTHER"


class BookableResource(db.Model):
    __tablename__ = "bookable_resources"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name          = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(20),  nullable=False)
    capacity      = db.Column(db.Integer,     nullable=True)    # max guests (event venue / villas)
    department_id = db.Column(db.String(36),  db.ForeignKey("departments.id"), nullable=True)
    base_price    = db.Column(db.Numeric(12, 2), nullable=False)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    department = db.relationship("Department", lazy="select")
    bookings   = db.relationship("Booking", back_populates="resource", lazy="dynamic")

    __table_args__ = (
        db.CheckConstraint("base_price >= 0", name="ck_resource_price_nonneg"),
    )

    def __repr__(self):
        return f"<BookableResource {self.name} ({self.resource_type})>"
