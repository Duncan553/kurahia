"""
BookingPayment — links a Payment to a Booking.
DEPOSIT: recorded before check-in; the Payment has tab_id=NULL.
BALANCE: post-check-in settlement (less common — most payments go straight to the Tab).

payment_id is UNIQUE so each Payment belongs to at most one BookingPayment.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class BookingPaymentPurpose(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    BALANCE = "BALANCE"


class BookingPayment(db.Model):
    __tablename__ = "booking_payments"

    id         = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = db.Column(db.String(36), db.ForeignKey("bookings.id"),
                           nullable=False, index=True)
    payment_id = db.Column(db.String(36), db.ForeignKey("payments.id"),
                           nullable=False, unique=True)
    purpose    = db.Column(db.String(10), nullable=False)   # DEPOSIT / BALANCE

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking = db.relationship("Booking",  back_populates="payments", lazy="select")
    payment = db.relationship("Payment",  lazy="select")

    def __repr__(self):
        return f"<BookingPayment {self.purpose} booking={self.booking_id}>"
