"""
LeaveRequest — employee asks for time off.
Approved leave makes an absence "with-notice" — it won't show as no-notice in attendance.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class LeaveType(str, enum.Enum):
    SICK      = "SICK"
    ANNUAL    = "ANNUAL"
    EMERGENCY = "EMERGENCY"
    UNPAID    = "UNPAID"
    OTHER     = "OTHER"


class LeaveStatus(str, enum.Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    CANCELLED = "CANCELLED"


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                            nullable=False, index=True)

    leave_type = db.Column(db.String(12), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date   = db.Column(db.Date, nullable=False)
    reason     = db.Column(db.Text, nullable=True)

    status         = db.Column(db.String(12), nullable=False, default=LeaveStatus.PENDING.value)
    reviewed_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    reviewed_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    notes          = db.Column(db.Text, nullable=True)

    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    created_at_utc  = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    employee    = db.relationship("EmployeeProfile", lazy="select")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("end_date >= start_date", name="ck_leave_end_after_start"),
    )

    def __repr__(self):
        return f"<LeaveRequest {self.leave_type} {self.start_date}–{self.end_date} {self.status}>"
