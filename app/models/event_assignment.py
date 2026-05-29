"""
EventAssignment — which employee fills which role at an event.
ASSIGNED: manager assigned them.
ACKNOWLEDGED: employee confirmed they saw it.
CANCELLED: removed from this event (history preserved).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class AssignmentStatus(str, enum.Enum):
    ASSIGNED     = "ASSIGNED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CANCELLED    = "CANCELLED"


VALID_ASSIGNMENT_TRANSITIONS: dict[str, set] = {
    AssignmentStatus.ASSIGNED.value:     {AssignmentStatus.ACKNOWLEDGED.value,
                                          AssignmentStatus.CANCELLED.value},
    AssignmentStatus.ACKNOWLEDGED.value: {AssignmentStatus.CANCELLED.value},
    AssignmentStatus.CANCELLED.value:    set(),
}


class EventAssignment(db.Model):
    __tablename__ = "event_assignments"

    id           = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id     = db.Column(db.String(36), db.ForeignKey("events.id"),
                             nullable=False, index=True)
    employee_id  = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                             nullable=False)
    role_on_event = db.Column(db.String(100), nullable=False)
    notes         = db.Column(db.Text, nullable=True)
    status        = db.Column(db.String(15), nullable=False, default=AssignmentStatus.ASSIGNED.value)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    event    = db.relationship("Event", back_populates="assignments", lazy="select")
    employee = db.relationship("EmployeeProfile", lazy="select")
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")

    def __repr__(self):
        return f"<EventAssignment event={self.event_id} emp={self.employee_id} {self.status}>"
