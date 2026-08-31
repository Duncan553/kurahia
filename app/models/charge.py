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

    # ── VAT, frozen at write time (invariant 3) ───────────────────────────────
    # `amount` is the GROSS the guest pays. Kenya hospitality quotes VAT
    # inclusive, so the tax is carried INSIDE that figure rather than added on
    # top — changing `amount` would silently reprice everything already sold.
    #
    # The rate is snapshotted per charge because rates change by statute, and a
    # sale from last year must keep computing with the rate that applied then.
    # Deriving it from today's setting would quietly rewrite history the moment
    # the rate moved — which is exactly what invariant 3 exists to prevent.
    #
    # NULL means "recorded before VAT tracking existed", and is reported
    # separately rather than assumed to be zero-rated.
    tax_rate_snapshot = db.Column(db.Numeric(5, 2), nullable=True)
    created_at    = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Idempotency (invariant 4: every write carries one) ────────────────────
    # Charges written from an endpoint a person can double-tap need this. The
    # water-session charge had no key and no column, so a double-tapped
    # "Add jetski" on a tablet with a slow connection posted the charge twice
    # and billed the guest for two rides they took once.
    #
    # NULLABLE because most charges do not come from a tap: an order item's
    # charge is already guarded by the order's own key, and a reversal mirrors
    # an existing row. UNIQUE still holds across the rows that do set it —
    # NULLs do not collide in either SQLite or PostgreSQL.
    idempotency_key = db.Column(db.String(64), nullable=True, unique=True)

    tab        = db.relationship("Tab",       lazy="select")
    order_item = db.relationship("OrderItem", lazy="select")
    created_by = db.relationship("User",      foreign_keys=[created_by_id], lazy="select")

    __table_args__ = (
        # Negative rows are legal (cancel reversals); zero rows never are
        db.CheckConstraint("amount != 0", name="ck_charge_amount_nonzero"),
    )


    @property
    def tax_amount(self):
        """The VAT contained in `amount`. DERIVED, never stored.

        Inclusive maths: gross = net x (1 + rate), so tax = gross x rate / (1 + rate).
        Storing this as its own column would let it drift out of step with
        `amount` after a correction; deriving it means it cannot.
        """
        from decimal import Decimal, ROUND_HALF_UP
        if self.tax_rate_snapshot is None:
            return None
        rate = Decimal(str(self.tax_rate_snapshot)) / Decimal("100")
        gross = Decimal(str(self.amount))
        return (gross * rate / (Decimal("1") + rate)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def net_amount(self):
        """`amount` minus the VAT it contains."""
        from decimal import Decimal
        tax = self.tax_amount
        if tax is None:
            return None
        return Decimal(str(self.amount)) - tax

    def __repr__(self):
        return f"<Charge {self.amount} tab={self.tab_id}>"
