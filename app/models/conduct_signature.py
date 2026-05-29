"""
ConductSignature — employee acknowledged a specific rule version.
Append-only: signing twice on the same version is idempotent (unique constraint on
employee_id + conduct_rule_id). No edits, no deletes.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class ConductSignature(db.Model):
    __tablename__ = "conduct_signatures"

    id                   = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id          = db.Column(db.String(36), db.ForeignKey("employee_profiles.id"),
                                     nullable=False, index=True)
    conduct_rule_id      = db.Column(db.String(36), db.ForeignKey("conduct_rules.id"),
                                     nullable=False)
    signed_proof         = db.Column(db.String(200), nullable=True)  # typed name or check-mark
    idempotency_key      = db.Column(db.String(128), nullable=False, unique=True)

    signed_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    employee = db.relationship("EmployeeProfile", lazy="select")
    rule     = db.relationship("ConductRule", back_populates="signatures", lazy="select")

    # One signature per employee per rule version
    __table_args__ = (
        db.UniqueConstraint("employee_id", "conduct_rule_id",
                            name="uq_signature_employee_rule"),
    )

    def __repr__(self):
        return f"<ConductSignature emp={self.employee_id} rule={self.conduct_rule_id}>"
