"""
GuestRecord — repeat-guest history.
Auto-matched by phone number on booking creation.
last_visit_utc is updated at checkout.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class GuestRecord(db.Model):
    __tablename__ = "guest_records"

    id         = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name       = db.Column(db.String(200), nullable=False)
    phone      = db.Column(db.String(30),  nullable=False, unique=True)
    id_number  = db.Column(db.String(50),  nullable=True)
    notes      = db.Column(db.Text,        nullable=True)
    is_active  = db.Column(db.Boolean,     nullable=False, default=True)

    last_visit_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    bookings = db.relationship("Booking", back_populates="guest_record", lazy="dynamic")

    def __repr__(self):
        return f"<GuestRecord {self.name} {self.phone}>"
