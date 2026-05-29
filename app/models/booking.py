"""
Booking — reservation lifecycle.
State machine: HELD → CONFIRMED → CHECKED_IN → CHECKED_OUT
                  ↘ CANCELLED   ↘ CANCELLED
                  ↘ NO_SHOW

base_total is a snapshot taken at create time; changing the resource price won't rewrite history.
tab_id is NULL until check-in; set when the villa Tab is opened.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class BookingStatus(str, enum.Enum):
    HELD        = "HELD"
    CONFIRMED   = "CONFIRMED"
    CHECKED_IN  = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED   = "CANCELLED"
    NO_SHOW     = "NO_SHOW"


# State machine: which statuses can transition to which
VALID_BOOKING_TRANSITIONS: dict[str, set] = {
    BookingStatus.HELD.value:        {BookingStatus.CONFIRMED.value,
                                      BookingStatus.CANCELLED.value,
                                      BookingStatus.NO_SHOW.value},
    BookingStatus.CONFIRMED.value:   {BookingStatus.CHECKED_IN.value,
                                      BookingStatus.CANCELLED.value},
    BookingStatus.CHECKED_IN.value:  {BookingStatus.CHECKED_OUT.value},
    BookingStatus.CHECKED_OUT.value: set(),
    BookingStatus.CANCELLED.value:   set(),
    BookingStatus.NO_SHOW.value:     set(),
}


class Booking(db.Model):
    __tablename__ = "bookings"

    id               = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource_id      = db.Column(db.String(36), db.ForeignKey("bookable_resources.id"),
                                 nullable=False, index=True)
    guest_record_id  = db.Column(db.String(36), db.ForeignKey("guest_records.id"), nullable=True)

    guest_name       = db.Column(db.String(200), nullable=False)
    guest_phone      = db.Column(db.String(30),  nullable=False)
    guest_id_number  = db.Column(db.String(50),  nullable=True)
    number_of_guests = db.Column(db.Integer,     nullable=False, default=1)

    check_in_planned_utc  = db.Column(db.DateTime(timezone=True), nullable=False)
    check_out_planned_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    check_in_actual_utc   = db.Column(db.DateTime(timezone=True), nullable=True)
    check_out_actual_utc  = db.Column(db.DateTime(timezone=True), nullable=True)

    base_total        = db.Column(db.Numeric(14, 2), nullable=False)   # price snapshot
    deposit_required  = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    status   = db.Column(db.String(15), nullable=False, default=BookingStatus.HELD.value)
    tab_id   = db.Column(db.String(36), db.ForeignKey("tabs.id"), nullable=True)
    notes    = db.Column(db.Text, nullable=True)

    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    created_by_id   = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    resource     = db.relationship("BookableResource", back_populates="bookings", lazy="select")
    guest_record = db.relationship("GuestRecord", back_populates="bookings", lazy="select")
    tab          = db.relationship("Tab", lazy="select")
    created_by   = db.relationship("User", foreign_keys=[created_by_id], lazy="select")
    payments     = db.relationship("BookingPayment", back_populates="booking",
                                   lazy="dynamic", cascade="all, delete-orphan")
    waivers      = db.relationship("Waiver", back_populates="booking",
                                   lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("check_out_planned_utc > check_in_planned_utc",
                           name="ck_booking_checkout_after_checkin"),
        db.CheckConstraint("number_of_guests > 0", name="ck_booking_guests_pos"),
        db.CheckConstraint("base_total >= 0",       name="ck_booking_total_nonneg"),
        db.CheckConstraint("deposit_required >= 0", name="ck_booking_deposit_nonneg"),
    )

    def __repr__(self):
        return f"<Booking {self.guest_name} {self.status}>"
