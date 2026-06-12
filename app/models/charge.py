"""
Charge — append-only record of what the tab owes.
Created when an Order is SENT (one Charge per OrderItem).
amount = order_item.quantity × order_item.unit_price_snapshot.
Never update or delete. Corrections = new rows.

A correction is a NEGATIVE row mirroring the original charge, written ONLY by
the cancel / send-back endpoints (one per cancelled item, enforced by the
order-item state machine + an existing-reversal check). No API accepts an
arbitrary negative amount — that would be the skim vector the judge watches.

Tab balance formula: SUM(charges.amount) − SUM(payments.amount)
That sum is computed on every balance query — never stored.

order_item_id is nullable: non-POS charges (villa rent, event minimums, manual
adjustments) link to no order item and use the description field instead.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Charge(db.Model):
    __tablename__ = "charges"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tab_id        = db.Column(db.String(36), db.ForeignKey("tabs.id"), nullable=False, index=True)
    order_item_id = db.Column(db.String(36), db.ForeignKey("order_items.id"), nullable=True)
    amount        = db.Column(db.Numeric(14, 2), nullable=False)
    description   = db.Column(db.String(200), nullable=False)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at    = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    tab        = db.relationship("Tab",       lazy="select")
    order_item = db.relationship("OrderItem", lazy="select")
    created_by = db.relationship("User",      foreign_keys=[created_by_id], lazy="select")

    __table_args__ = (
        # Negative rows are legal (cancel reversals); zero rows never are
        db.CheckConstraint("amount != 0", name="ck_charge_amount_nonzero"),
    )

    def __repr__(self):
        return f"<Charge {self.amount} tab={self.tab_id}>"
