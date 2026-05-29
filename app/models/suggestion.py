"""
Suggestion — two-tier confidential feedback channel.

MANAGEMENT:    visible to manager+ at the query layer.
OWNER_PRIVATE: invisible to managers entirely — the query filter removes them.
               Anonymous submissions allowed (submitted_by_user_id=NULL).

This is structural authorization: OWNER_PRIVATE rows simply don't appear in
manager queries — no manager can request them by ID either (404 is returned).
Same pattern as leave can't-self-approve from Chunk 5.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class SuggestionCategory(str, enum.Enum):
    MANAGEMENT    = "MANAGEMENT"
    OWNER_PRIVATE = "OWNER_PRIVATE"


class SuggestionStatus(str, enum.Enum):
    NEW          = "NEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTIONED     = "ACTIONED"
    DISMISSED    = "DISMISSED"


class Suggestion(db.Model):
    __tablename__ = "suggestions"

    id                    = db.Column(db.String(36), primary_key=True,
                                      default=lambda: str(uuid.uuid4()))
    # NULL = anonymous (only allowed for OWNER_PRIVATE)
    submitted_by_user_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    submitted_by_name     = db.Column(db.String(200), nullable=True)   # "anonymous" or real name
    category              = db.Column(db.String(15), nullable=False)
    subject               = db.Column(db.String(200), nullable=False)
    body                  = db.Column(db.Text, nullable=False)
    status                = db.Column(db.String(15), nullable=False,
                                      default=SuggestionStatus.NEW.value)
    reviewed_by_id        = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    reviewed_at_utc       = db.Column(db.DateTime(timezone=True), nullable=True)
    response_to_submitter = db.Column(db.Text, nullable=True)
    idempotency_key       = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    submitted_by = db.relationship("User", foreign_keys=[submitted_by_user_id], lazy="select")
    reviewed_by  = db.relationship("User", foreign_keys=[reviewed_by_id],       lazy="select")

    def __repr__(self):
        return f"<Suggestion {self.category} {self.status}>"
