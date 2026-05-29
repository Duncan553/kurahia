"""
Event — a scheduled occasion at the resort.
State machine: PLANNED → CONFIRMED → IN_PROGRESS → COMPLETED
               ↘ CANCELLED   ↘ CANCELLED   ↘ CANCELLED

booking_id: most events are a booking of the event field (Chunk 6), but some
            are internal-only (staff party, training) with no booking record.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class EventStatus(str, enum.Enum):
    PLANNED     = "PLANNED"
    CONFIRMED   = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"


VALID_EVENT_TRANSITIONS: dict[str, set] = {
    EventStatus.PLANNED.value:     {EventStatus.CONFIRMED.value, EventStatus.CANCELLED.value},
    EventStatus.CONFIRMED.value:   {EventStatus.IN_PROGRESS.value, EventStatus.CANCELLED.value},
    EventStatus.IN_PROGRESS.value: {EventStatus.COMPLETED.value, EventStatus.CANCELLED.value},
    EventStatus.COMPLETED.value:   set(),
    EventStatus.CANCELLED.value:   set(),
}


class Event(db.Model):
    __tablename__ = "events"

    id              = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title           = db.Column(db.String(200), nullable=False)
    event_type_id   = db.Column(db.String(36), db.ForeignKey("event_types.id"), nullable=False)
    booking_id      = db.Column(db.String(36), db.ForeignKey("bookings.id"), nullable=True)
    starts_at_utc   = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at_utc     = db.Column(db.DateTime(timezone=True), nullable=False)
    expected_guests = db.Column(db.Integer, nullable=False, default=1)
    location        = db.Column(db.String(200), nullable=True)
    notes           = db.Column(db.Text, nullable=True)
    status          = db.Column(db.String(15), nullable=False, default=EventStatus.PLANNED.value)
    created_by_id   = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    event_type  = db.relationship("EventType", lazy="select")
    booking     = db.relationship("Booking", lazy="select")
    created_by  = db.relationship("User", foreign_keys=[created_by_id], lazy="select")
    assignments = db.relationship("EventAssignment", back_populates="event",
                                  lazy="dynamic", cascade="all, delete-orphan")
    allocations = db.relationship("EventInventoryAllocation", back_populates="event",
                                  lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("ends_at_utc > starts_at_utc",    name="ck_event_end_after_start"),
        db.CheckConstraint("expected_guests > 0",            name="ck_event_guests_pos"),
    )

    def __repr__(self):
        return f"<Event {self.title!r} {self.status}>"
