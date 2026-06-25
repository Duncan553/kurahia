"""
LostFound — tracks items found on resort premises.

Status lifecycle:
  UNCLAIMED → CLAIMED   (guest/owner collects it)
  UNCLAIMED → DISPOSED  (not collected within retention period)

found_by_id = staff member who logged it.
claimed_by_name = free-text name of the person who collected it (guest, not a system user).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class LostFoundStatus(str, enum.Enum):
    UNCLAIMED = "UNCLAIMED"
    CLAIMED   = "CLAIMED"
    DISPOSED  = "DISPOSED"


class LostFound(db.Model):
    __tablename__ = "lost_found"

    id              = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    description     = db.Column(db.String(500), nullable=False)
    found_location  = db.Column(db.String(200), nullable=False)
    found_by_id     = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    found_at        = db.Column(db.DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))
    status          = db.Column(db.String(20), nullable=False, default=LostFoundStatus.UNCLAIMED.value)
    claimed_by_name = db.Column(db.String(200), nullable=True)
    claimed_at      = db.Column(db.DateTime(timezone=True), nullable=True)
    notes           = db.Column(db.String(500), nullable=True)
    is_active       = db.Column(db.Boolean, nullable=False, default=True)

    # Relationship for easy username lookup in serialisation
    found_by = db.relationship("User", foreign_keys=[found_by_id], lazy="select")

    def __repr__(self):
        return f"<LostFound {self.id[:8]} {self.status}>"
