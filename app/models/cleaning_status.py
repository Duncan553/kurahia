"""
CleaningStatus — tracks the housekeeping state of each villa/room.

Lifecycle: DIRTY → CLEANING → CLEAN → INSPECTED
  - Auto-created as DIRTY when a booking transitions to CHECKED_OUT
  - Housekeeper starts cleaning → CLEANING
  - Housekeeper finishes → CLEAN
  - Manager inspects → INSPECTED (ready for next guest)
  - FLAG can be set at any point to note issues (maintenance, missing items)

One active record per resource at a time. Historical records are kept
for audit and reporting (never deleted).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class CleaningStatusEnum(str, enum.Enum):
    DIRTY     = "DIRTY"
    CLEANING  = "CLEANING"
    CLEAN     = "CLEAN"
    INSPECTED = "INSPECTED"


# State machine: which statuses can transition to which
VALID_CLEANING_TRANSITIONS: dict[str, set] = {
    CleaningStatusEnum.DIRTY.value:     {CleaningStatusEnum.CLEANING.value},
    CleaningStatusEnum.CLEANING.value:  {CleaningStatusEnum.CLEAN.value},
    CleaningStatusEnum.CLEAN.value:     {CleaningStatusEnum.INSPECTED.value},
    CleaningStatusEnum.INSPECTED.value: {CleaningStatusEnum.DIRTY.value},  # re-dirtied after next checkout
}


class CleaningStatus(db.Model):
    __tablename__ = "cleaning_statuses"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Which villa/room this record tracks
    resource_id = db.Column(
        db.String(36), db.ForeignKey("bookable_resources.id"),
        nullable=False, index=True,
    )

    # Current cleaning state
    status = db.Column(db.String(15), nullable=False, default=CleaningStatusEnum.DIRTY.value)

    # Which housekeeper is assigned (nullable until assigned)
    assigned_to_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    assigned_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # When the housekeeper finished cleaning
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Manager inspection
    inspected_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    inspected_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Free-text notes (flagged issues, missing items, etc.)
    notes = db.Column(db.String(500), nullable=True)

    # Flag for issues that need attention beyond normal cleaning
    is_flagged = db.Column(db.Boolean, nullable=False, default=False)
    flag_reason = db.Column(db.String(500), nullable=True)

    # UTC timestamps — server-stamped
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    resource = db.relationship("BookableResource", lazy="select")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id], lazy="select")
    inspected_by = db.relationship("User", foreign_keys=[inspected_by_id], lazy="select")

    def __repr__(self):
        return f"<CleaningStatus {self.resource_id} {self.status}>"
