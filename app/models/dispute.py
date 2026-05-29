"""
Dispute — formal complaint lifecycle.
subject_employee_ids is a one-to-many via DisputeSubject (multiple parties per dispute).
is_owner_only: same two-tier filter as suggestions — invisible to managers at the query layer.
State machine: OPEN → UNDER_REVIEW → RESOLVED | DISMISSED
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class DisputeCategory(str, enum.Enum):
    PERFORMANCE       = "PERFORMANCE"
    INTERPERSONAL     = "INTERPERSONAL"
    CONDUCT_VIOLATION = "CONDUCT_VIOLATION"
    OTHER             = "OTHER"


class DisputeStatus(str, enum.Enum):
    OPEN         = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED     = "RESOLVED"
    DISMISSED    = "DISMISSED"


class DisputePriority(str, enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


VALID_DISPUTE_TRANSITIONS: dict[str, set] = {
    DisputeStatus.OPEN.value:         {DisputeStatus.UNDER_REVIEW.value,
                                       DisputeStatus.DISMISSED.value},
    DisputeStatus.UNDER_REVIEW.value: {DisputeStatus.RESOLVED.value,
                                       DisputeStatus.DISMISSED.value},
    DisputeStatus.RESOLVED.value:     set(),
    DisputeStatus.DISMISSED.value:    set(),
}


class Dispute(db.Model):
    __tablename__ = "disputes"

    id                    = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reporter_employee_id  = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                                      nullable=False, index=True)
    category              = db.Column(db.String(20), nullable=False)
    description           = db.Column(db.Text,       nullable=False)
    status                = db.Column(db.String(15),  nullable=False, default=DisputeStatus.OPEN.value)
    priority              = db.Column(db.String(10),  nullable=False, default=DisputePriority.MEDIUM.value)
    is_owner_only         = db.Column(db.Boolean,    nullable=False, default=False)
    assigned_to_employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"), nullable=True)
    resolution_notes      = db.Column(db.Text, nullable=True)
    idempotency_key       = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    reporter    = db.relationship("EmployeeProfile", foreign_keys=[reporter_employee_id], lazy="select")
    assigned_to = db.relationship("EmployeeProfile", foreign_keys=[assigned_to_employee_id], lazy="select")
    subjects    = db.relationship("DisputeSubject", back_populates="dispute",
                                  lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Dispute {self.category} {self.status}>"


class DisputeSubject(db.Model):
    """Association: which employees are the subject(s) of this dispute."""
    __tablename__ = "dispute_subjects"

    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dispute_id  = db.Column(db.String(36), db.ForeignKey("disputes.id"),
                            nullable=False, index=True)
    employee_id = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"), nullable=False)

    dispute  = db.relationship("Dispute", back_populates="subjects", lazy="select")
    employee = db.relationship("EmployeeProfile", lazy="select")

    __table_args__ = (
        db.UniqueConstraint("dispute_id", "employee_id", name="uq_dispute_subject"),
    )
