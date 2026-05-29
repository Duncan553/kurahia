"""
GateEntry — links a wristband to an arrival event.
head_count: always 1 now (1:1 policy). Field kept for future flexibility.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class GateEntry(db.Model):
    __tablename__ = "gate_entries"

    id           = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wristband_id = db.Column(db.String(36), db.ForeignKey("wristbands.id"),
                             nullable=False, unique=True)   # one entry per band
    head_count   = db.Column(db.Integer, nullable=False, default=1)
    notes        = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    wristband  = db.relationship("Wristband", lazy="select")
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("head_count > 0", name="ck_gate_entry_count_pos"),
    )

    def __repr__(self):
        return f"<GateEntry band={self.wristband_id} count={self.head_count}>"
