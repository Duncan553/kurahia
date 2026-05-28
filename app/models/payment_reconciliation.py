"""
PaymentReconciliation — manual M-Pesa/card verification against real statements.

One row per Payment row (unique on payment_id). Updated when the cashier
matches or flags a typed code against the actual Safaricom/bank statement.

Future: Daraja API auto-match writes the same row automatically.
Socket ready — the flow doesn't change when automation arrives.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class PaymentReconciliationStatus(str, enum.Enum):
    MATCHED   = "MATCHED"
    UNMATCHED = "UNMATCHED"
    FLAGGED   = "FLAGGED"   # code doesn't match the statement → alert


class PaymentReconciliation(db.Model):
    __tablename__ = "payment_reconciliations"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id    = db.Column(db.String(36), db.ForeignKey("payments.id"),
                              nullable=False, unique=True)
    method        = db.Column(db.String(10), nullable=False)   # MPESA / CARD
    matched       = db.Column(db.Boolean,    nullable=False, default=False)
    matched_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    statement_ref = db.Column(db.String(100), nullable=True)   # real reference from the bank/Safaricom
    status        = db.Column(db.String(12),  nullable=False,
                              default=PaymentReconciliationStatus.UNMATCHED.value)
    notes         = db.Column(db.Text, nullable=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    payment    = db.relationship("Payment", lazy="select")
    matched_by = db.relationship("User", foreign_keys=[matched_by_id], lazy="select")

    def __repr__(self):
        return f"<PaymentRecon payment={self.payment_id} status={self.status}>"
