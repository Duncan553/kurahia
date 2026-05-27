"""
JudgeBaseline — expected consumption ratio per item per business driver.
Example: "cooking oil consumes ~0.5 kg per KSh 10,000 restaurant revenue."
Seeded with conservative honest values at install. Not learned — human-set.
The judge reads these to flag anomalies. Staff-food items have no baselines.
"""
import uuid
from decimal import Decimal
from app.extensions import db


class JudgeBaseline(db.Model):
    __tablename__ = "judge_baselines"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False)

    # What drives consumption — "restaurant_revenue", "covers_served", "bar_revenue"
    business_driver = db.Column(db.String(100), nullable=False)

    # How much of the item is consumed per unit of the driver
    # e.g. 0.5 (kg of oil) per 10_000 (KSh revenue)
    expected_ratio = db.Column(db.Numeric(12, 6), nullable=False)
    driver_unit    = db.Column(db.String(50),  nullable=False)   # "per KSh 10k revenue"

    # Acceptable deviation before flagging (%)
    tolerance_percent = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("20"))

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    item = db.relationship("InventoryItem", lazy="select")

    __table_args__ = (
        db.UniqueConstraint("item_id", "business_driver", name="uq_baseline_item_driver"),
        db.CheckConstraint("expected_ratio > 0",    name="ck_baseline_ratio_pos"),
        db.CheckConstraint("tolerance_percent > 0", name="ck_baseline_tol_pos"),
    )

    def __repr__(self):
        return f"<JudgeBaseline item={self.item_id} driver={self.business_driver}>"
