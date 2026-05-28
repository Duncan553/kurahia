"""
Tab — a running bill for a customer visit.
type field: WALK_IN now; VILLA / BAND are forward-compat placeholders for Chunk 7.
Balance is NEVER stored — always derived from charges minus payments.
A Tab is closable only when balance ≤ 0 AND all order items are resolved.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class TabType(str, enum.Enum):
    WALK_IN = "WALK_IN"
    VILLA   = "VILLA"    # Chunk 7
    BAND    = "BAND"     # Chunk 7


class TabStatus(str, enum.Enum):
    OPEN   = "OPEN"
    CLOSED = "CLOSED"


class Tab(db.Model):
    __tablename__ = "tabs"

    id        = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tab_type  = db.Column(db.String(10), nullable=False, default=TabType.WALK_IN.value)
    reference = db.Column(db.String(100), nullable=True)   # e.g. "Table 5", villa name
    status    = db.Column(db.String(10),  nullable=False, default=TabStatus.OPEN.value)

    opened_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    opened_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    closed_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    closed_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    opened_by = db.relationship("User", foreign_keys=[opened_by_id], lazy="select")
    closed_by = db.relationship("User", foreign_keys=[closed_by_id], lazy="select")

    def __repr__(self):
        return f"<Tab {self.reference or self.id[:8]} {self.status}>"
