"""
PeriodClose — locks a business day and records the physical safe count.

expected_total_cash: sum of actual_amount from all CashReconciliations
                     in the period (what the cashier should have put in the safe).
safe_count:          physical cash counted in the safe by the closer.
difference:          safe_count - expected_total_cash
                     Negative = money missing from the safe (cashier-level theft).

Append-only by design. One closed period can be queried for all subsequent audits.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class PeriodCloseStatus(str, enum.Enum):
    BALANCED = "BALANCED"
    SHORT    = "SHORT"
    OVER     = "OVER"


class PeriodClose(db.Model):
    __tablename__ = "period_closes"

    id               = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    period_start_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    period_end_utc   = db.Column(db.DateTime(timezone=True), nullable=False)
    closed_by_id     = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    safe_count          = db.Column(db.Numeric(14, 2), nullable=False)
    expected_total_cash = db.Column(db.Numeric(14, 2), nullable=False)  # snapshot at close time
    difference          = db.Column(db.Numeric(14, 2), nullable=False)  # safe_count - expected

    status          = db.Column(db.String(10), nullable=False)
    notes           = db.Column(db.Text, nullable=True)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    closed_by = db.relationship("User", foreign_keys=[closed_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("safe_count >= 0", name="ck_periodclose_safe_nonneg"),
    )

    def __repr__(self):
        return f"<PeriodClose {self.period_start_utc.date()} status={self.status}>"
