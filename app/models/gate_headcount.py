"""
GateHeadcount — physical/turnstile count submitted by an independent counter.
One record per day. Used to cross-check against bands_issued.
If counted > bands_issued, someone entered without a band → theft signal.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class GateHeadcount(db.Model):
    __tablename__ = "gate_headcounts"

    id           = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    count_date   = db.Column(db.String(10), nullable=False, unique=True)  # "YYYY-MM-DD"
    counted      = db.Column(db.Integer,    nullable=False)
    notes        = db.Column(db.Text, nullable=True)
    recorded_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("counted >= 0", name="ck_headcount_nonneg"),
    )

    def __repr__(self):
        return f"<GateHeadcount {self.count_date} counted={self.counted}>"
