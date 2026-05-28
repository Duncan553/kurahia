"""
Shift — a manager-scheduled work block for one employee.
status updates allowed; the row itself is logically immutable (use CANCELLED not delete).
Schedule conflict check (same employee, overlapping windows) enforced at the route layer.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class ShiftStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"


class Shift(db.Model):
    __tablename__ = "shifts"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"), nullable=False, index=True)

    scheduled_start_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    scheduled_end_utc   = db.Column(db.DateTime(timezone=True), nullable=False)

    role_on_shift = db.Column(db.String(100), nullable=True)   # "waiter", "cashier" etc.
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=True)
    status        = db.Column(db.String(12),  nullable=False, default=ShiftStatus.SCHEDULED.value)

    created_by_id   = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    employee   = db.relationship("EmployeeProfile", lazy="select")
    department = db.relationship("Department",      lazy="select")
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint(
            "scheduled_end_utc > scheduled_start_utc",
            name="ck_shift_end_after_start",
        ),
    )

    def __repr__(self):
        return f"<Shift emp={self.employee_id} {self.scheduled_start_utc}–{self.scheduled_end_utc}>"
