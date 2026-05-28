"""
CashReconciliation — records one staff member's cash hand-in.

expected_amount: sum of their unreconciled CASH payments at the moment
                 of reconciliation (derived, then snapshotted here).
actual_amount:   the physical cash they hand in to the cashier.
difference:      actual - expected (negative = SHORT, the dangerous case).

The link table cash_recon_payments ties which Payment rows were swept up.
payment_id is the PK there — each payment reconciled at most once.

Append-only by policy: corrections create a new record, never edit this one.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class ReconciliationStatus(str, enum.Enum):
    BALANCED = "BALANCED"
    SHORT    = "SHORT"   # actual < expected — shortfall
    OVER     = "OVER"    # actual > expected — unusual


# Join table: which Payment rows were swept into a reconciliation.
# payment_id is PK → each payment belongs to at most one reconciliation.
cash_recon_payments = db.Table(
    "cash_recon_payments",
    db.Column("recon_id",   db.String(36), db.ForeignKey("cash_reconciliations.id"), nullable=False),
    db.Column("payment_id", db.String(36), db.ForeignKey("payments.id"), primary_key=True),
)


class CashReconciliation(db.Model):
    __tablename__ = "cash_reconciliations"

    id               = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    staff_id         = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    reconciled_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    expected_amount  = db.Column(db.Numeric(14, 2), nullable=False)
    actual_amount    = db.Column(db.Numeric(14, 2), nullable=False)
    difference       = db.Column(db.Numeric(14, 2), nullable=False)  # actual - expected

    period_start_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    period_end_utc   = db.Column(db.DateTime(timezone=True), nullable=False)

    status          = db.Column(db.String(10), nullable=False)
    notes           = db.Column(db.Text, nullable=True)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc  = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    staff         = db.relationship("User", foreign_keys=[staff_id],         lazy="select")
    reconciled_by = db.relationship("User", foreign_keys=[reconciled_by_id], lazy="select")
    payments      = db.relationship("Payment", secondary="cash_recon_payments", lazy="select")

    __table_args__ = (
        db.CheckConstraint("expected_amount >= 0", name="ck_cashrecon_expected_nonneg"),
        db.CheckConstraint("actual_amount >= 0",   name="ck_cashrecon_actual_nonneg"),
    )

    def __repr__(self):
        return f"<CashRecon staff={self.staff_id} status={self.status} diff={self.difference}>"
