"""
Waiver — safety gate for water activities.
Required before any water-activity session charge can be posted on a booking's tab.
is_active allows revocation (e.g. expired waiver) without losing the record.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class WaiverActivityType(str, enum.Enum):
    WATER_ACTIVITY = "WATER_ACTIVITY"
    GENERAL        = "GENERAL"


class Waiver(db.Model):
    __tablename__ = "waivers"

    id                = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id        = db.Column(db.String(36), db.ForeignKey("bookings.id"),
                                  nullable=False, index=True)
    activity_type     = db.Column(db.String(20), nullable=False)   # WATER_ACTIVITY / GENERAL
    signed_by_name    = db.Column(db.String(200), nullable=False)
    signature_proof   = db.Column(db.String(500), nullable=True)   # photo path or reference
    is_active         = db.Column(db.Boolean, nullable=False, default=True)

    signed_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking = db.relationship("Booking", back_populates="waivers", lazy="select")

    def __repr__(self):
        return f"<Waiver {self.activity_type} booking={self.booking_id}>"
