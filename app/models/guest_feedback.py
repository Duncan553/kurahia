"""
GuestFeedback — customer rating tied to a department or a specific staff member.
booking_id / event_id: optional context.
served_by_employee_id: when named, feeds the employee's performance guest_rating component.
score 1-5 (1=poor, 5=excellent).
Anonymous feedback allowed: guest_name="anonymous", guest_phone=NULL.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class GuestFeedback(db.Model):
    __tablename__ = "guest_feedback"

    id                    = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id            = db.Column(db.String(36), db.ForeignKey("bookings.id"), nullable=True)
    event_id              = db.Column(db.String(36), db.ForeignKey("events.id"),   nullable=True)
    guest_name            = db.Column(db.String(200), nullable=False)
    guest_phone           = db.Column(db.String(30),  nullable=True)
    department_id         = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=True)
    score                 = db.Column(db.Integer,    nullable=False)   # 1-5
    comments              = db.Column(db.Text,       nullable=True)
    # Links feedback to a specific employee — activates their performance guest_rating
    served_by_employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"), nullable=True)
    idempotency_key       = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking    = db.relationship("Booking",         lazy="select")
    event      = db.relationship("Event",           lazy="select")
    department = db.relationship("Department",      lazy="select")
    served_by  = db.relationship("EmployeeProfile", lazy="select")

    __table_args__ = (
        db.CheckConstraint("score >= 1 AND score <= 5", name="ck_feedback_score_range"),
    )

    def __repr__(self):
        return f"<GuestFeedback score={self.score} dept={self.department_id}>"
