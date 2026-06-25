"""
Incident — append-only accident/incident log for the resort.

Append-only: once logged, rows are never edited or deleted.
Managers can only "action" (acknowledge) an incident — that sets a flag,
it does NOT modify the original record.

severity values: LOW, MEDIUM, HIGH
actioned: False until a manager explicitly acknowledges the incident.
"""
import uuid
import enum
from sqlalchemy.sql import func
from app.extensions import db


class IncidentSeverity(str, enum.Enum):
    LOW    = "LOW"     # minor — no injury
    MEDIUM = "MEDIUM"  # injury handled on-site
    HIGH   = "HIGH"    # injury requiring medical attention or evacuation


class Incident(db.Model):
    __tablename__ = "incidents"

    id             = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who filed the report
    reported_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    # What happened, where, how bad
    description    = db.Column(db.Text, nullable=False)
    location       = db.Column(db.String(200), nullable=False)      # e.g. "Pool area"
    severity       = db.Column(db.String(20), nullable=False)       # IncidentSeverity value

    # Optional: guest involved (free text — may not be a system user)
    involved_guest = db.Column(db.String(200), nullable=True)

    # Idempotency — prevents duplicate submissions on retry
    idempotency_key = db.Column(db.String(100), nullable=False, unique=True)

    # Manager acknowledgement
    actioned       = db.Column(db.Boolean, nullable=False, default=False)
    actioned_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    actioned_at    = db.Column(db.DateTime(timezone=True), nullable=True)

    # Server-stamped UTC creation time
    created_at     = db.Column(db.DateTime(timezone=True), nullable=False,
                               server_default=func.now())

    # Relationships for easy serialisation
    reporter  = db.relationship("User", foreign_keys=[reported_by_id], lazy="select")
    actioner  = db.relationship("User", foreign_keys=[actioned_by_id], lazy="select")

    def __repr__(self):
        return f"<Incident {self.id[:8]} {self.severity} actioned={self.actioned}>"
