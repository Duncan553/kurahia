"""
ClockEvent — a single clock-in or clock-out moment.

Append-only: no edits, no deletes. Corrections = new records with
is_manual_override=True and override_by/override_reason filled in.

shift_id: auto-linked by the service layer when the event falls within
          ±2 hours of a scheduled shift start. Null if no match (flagged).
source_ip: the server-observed remote_addr (not client-supplied).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class ClockEventType(str, enum.Enum):
    CLOCK_IN  = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"


class ClockEvent(db.Model):
    __tablename__ = "clock_events"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                            nullable=False, index=True)

    event_type      = db.Column(db.String(12), nullable=False)     # CLOCK_IN / CLOCK_OUT
    occurred_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)

    source_ip        = db.Column(db.String(45),  nullable=True)    # server-observed
    source_wifi_ssid = db.Column(db.String(100), nullable=True)    # client-reported (display only)

    shift_id = db.Column(db.String(36), db.ForeignKey("shifts.id"), nullable=True)

    is_manual_override = db.Column(db.Boolean, nullable=False, default=False)
    override_by_id     = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    override_reason    = db.Column(db.Text, nullable=True)

    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    employee    = db.relationship("EmployeeProfile", lazy="select")
    shift       = db.relationship("Shift",           lazy="select")
    override_by = db.relationship("User", foreign_keys=[override_by_id], lazy="select")

    def __repr__(self):
        return f"<ClockEvent {self.event_type} emp={self.employee_id}>"
