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

    # The LEAD housekeeper — the one accountable for the state of the room.
    # Kept as a single FK because every existing caller, the audit trail and the
    # "assigned to me" permission check all read one name.
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


class CleaningCleaner(db.Model):
    """Everyone who worked on one clean — a villa is usually done by two.

    CleaningStatus.assigned_to_id holds ONE name, which was fine while the
    board was "who is this room assigned to" and wrong as soon as front desk
    started recording who actually cleaned it: villas here are done in pairs,
    and the second person simply vanished from the record.

    The lead stays on CleaningStatus (permission checks and the audit row read
    one name). This table is the full list, lead included, so "who cleaned
    Villa 4 on the 12th" has a complete answer.
    """
    __tablename__ = "cleaning_cleaners"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cleaning_id = db.Column(db.String(36), db.ForeignKey("cleaning_statuses.id"),
                            nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    is_lead = db.Column(db.Boolean, nullable=False, default=False)
    added_at_utc = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id], lazy="select")

    __table_args__ = (
        # Structural, not app-level: the same person cannot be recorded twice
        # on one clean, so a double-tap cannot inflate who did the work.
        db.UniqueConstraint("cleaning_id", "user_id", name="uq_cleaning_cleaner"),
    )

    def __repr__(self):
        return f"<CleaningCleaner {self.cleaning_id} {self.user_id} lead={self.is_lead}>"
