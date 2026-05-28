"""
AbsenceNotice — "I'll be late / I won't make it today" from the employee app.
Marks the upcoming/missed shift as absent-with-notice in attendance reports.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class NoticeType(str, enum.Enum):
    LATE   = "LATE"    # coming, but will be late
    ABSENT = "ABSENT"  # won't come at all


class AbsenceNotice(db.Model):
    __tablename__ = "absence_notices"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                            nullable=False, index=True)

    expected_shift_id    = db.Column(db.String(36), db.ForeignKey("shifts.id"), nullable=True)
    notice_type          = db.Column(db.String(10), nullable=False)   # LATE / ABSENT
    expected_late_minutes = db.Column(db.Integer, nullable=True)      # for LATE notices
    reason               = db.Column(db.Text, nullable=True)
    sent_at_utc          = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    employee       = db.relationship("EmployeeProfile", lazy="select")
    expected_shift = db.relationship("Shift",           lazy="select")

    def __repr__(self):
        return f"<AbsenceNotice {self.notice_type} emp={self.employee_id}>"
