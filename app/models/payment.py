"""
Payment — append-only record of money received against a tab.
received_by: the named staff member who collected the payment.
mpesa_code:  captured as-typed; verification deferred to daily reconciliation (Chunk 5).
card_ref:    captured for card payments; reconciled later.

For Chunk 7 band tabs: a gate-entry Payment(amount=3000) is created at activation.
Balance = SUM(charges) - SUM(payments); that Payment starts the tab at -3000 (credit).
Same formula. No special case.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class PaymentMethod(str, enum.Enum):
    CASH  = "CASH"
    CARD  = "CARD"
    MPESA = "MPESA"


class Payment(db.Model):
    __tablename__ = "payments"

    id         = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tab_id     = db.Column(db.String(36), db.ForeignKey("tabs.id"), nullable=False, index=True)
    amount     = db.Column(db.Numeric(14, 2), nullable=False)
    method     = db.Column(db.String(10), nullable=False)
    mpesa_code = db.Column(db.String(20), nullable=True)   # captured, not verified yet
    card_ref   = db.Column(db.String(50), nullable=True)

    received_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    tab         = db.relationship("Tab",  lazy="select")
    received_by = db.relationship("User", foreign_keys=[received_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_payment_amount_pos"),
    )

    def __repr__(self):
        return f"<Payment {self.method} {self.amount} tab={self.tab_id}>"
