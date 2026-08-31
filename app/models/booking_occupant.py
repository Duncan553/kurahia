"""
BookingOccupant — the other people actually staying in the villa.

Booking records ONE name (guest_name) plus number_of_guests as an integer, so a
family of six was one name and the number 6. Five of those people did not exist
anywhere in the system.

That is a problem in three directions:
  - a guest register with names is a legal expectation for accommodation;
  - "may this person charge to Villa 6?" is unanswerable when only the payer
    is on file, and any of the six can walk to the bar and say the room number;
  - a returning family is matched by the lead guest's phone alone.

Append-only like everything else: a companion who leaves early is marked
checked_out_utc, never deleted, because they were in the building.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class BookingOccupant(db.Model):
    __tablename__ = "booking_occupants"

    id         = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = db.Column(db.String(36), db.ForeignKey("bookings.id"), nullable=False, index=True)

    full_name  = db.Column(db.String(200), nullable=False)
    # Optional on purpose. Requiring ID for every companion would block check-in
    # over a teenager without a card or an ID left in the car, and a desk that
    # cannot complete check-in gets worked around — which loses the name too.
    # The lead guest's ID is captured on Booking.guest_id_number.
    id_number  = db.Column(db.String(50), nullable=True)
    phone      = db.Column(db.String(30), nullable=True)
    is_adult   = db.Column(db.Boolean, nullable=False, default=True)

    # Whether this person may put charges on the villa tab. Defaults False:
    # the lead guest is liable for the bill, and anyone else must be granted it
    # deliberately rather than by being listed.
    may_charge = db.Column(db.Boolean, nullable=False, default=False)

    checked_out_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at_utc  = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking = db.relationship("Booking", lazy="select")

    def __repr__(self):
        return f"<BookingOccupant {self.full_name} booking={self.booking_id}>"
