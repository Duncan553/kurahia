"""
CalendarEntry — peak dates, holidays, planning-meeting triggers.
planning_trigger_offset_days: if set, a Notification to the owner is queued
  (offset) days before date_start_utc when this entry is saved.
is_peak: auto-flag for dates that typically drive high traffic.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class CalendarEntryType(str, enum.Enum):
    HOLIDAY             = "HOLIDAY"
    PEAK                = "PEAK"
    PLANNING_MEETING    = "PLANNING_MEETING"
    EXTERNAL_OBSERVANCE = "EXTERNAL_OBSERVANCE"


class CalendarEntry(db.Model):
    __tablename__ = "calendar_entries"

    id                          = db.Column(db.String(36), primary_key=True,
                                            default=lambda: str(uuid.uuid4()))
    title                       = db.Column(db.String(200), nullable=False)
    date_start_utc              = db.Column(db.DateTime(timezone=True), nullable=False)
    date_end_utc                = db.Column(db.DateTime(timezone=True), nullable=False)
    entry_type                  = db.Column(db.String(25), nullable=False)
    description                 = db.Column(db.Text, nullable=True)
    is_peak                     = db.Column(db.Boolean, nullable=False, default=False)
    # Days before date_start to fire a planning-meeting notification to the owner
    planning_trigger_offset_days = db.Column(db.Integer, nullable=True)
    created_by_id               = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    is_active                   = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("date_end_utc >= date_start_utc",
                           name="ck_calendar_end_after_start"),
    )

    def __repr__(self):
        return f"<CalendarEntry {self.title!r} {self.entry_type}>"
