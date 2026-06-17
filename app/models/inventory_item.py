"""
InventoryItem — a physical stock item tracked in a department.
Units are free-text strings (kg, crate, litre, bottle, etc.) — never hardcoded.
is_watch_list → tighter tolerance + daily count cadence.
is_staff_food  → lives in Staff dept, excluded from sale-stock variance and judge.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.String(30), nullable=False)          # "kg", "litre", "bottle" …
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=False)
    reorder_level = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0"))

    # Watch-list items get tighter tolerance and are counted daily
    is_watch_list = db.Column(db.Boolean, nullable=False, default=False)

    # Per-item variance tolerance (%). None → use system default (5 %)
    tolerance_percent = db.Column(db.Numeric(5, 2), nullable=True)

    # Staff food lives in a separate dept; judge and sale-variance ignore it
    is_staff_food = db.Column(db.Boolean, nullable=False, default=False)

    # Pack-aware fields for spirits/cocktails: pack_size=750, pack_unit="ml" means
    # 1 bottle = 750 ml. Recipes specify ml; stock tracks bottles.
    # NULL = non-pack item (flour, rice) — recipe unit matches stock unit.
    pack_size = db.Column(db.Numeric(12, 4), nullable=True)
    pack_unit = db.Column(db.String(30), nullable=True)
    category  = db.Column(db.String(50), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Server-stamped at catalog creation — used for "new item" trust-tier criterion
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=True,
        default=lambda: datetime.now(timezone.utc),
    )

    # Weighted-average cost, updated on every PURCHASE movement. NULL until first purchase.
    cost_per_unit = db.Column(db.Numeric(14, 4), nullable=True)

    department = db.relationship("Department", lazy="select")

    __table_args__ = (
        db.UniqueConstraint("name", "department_id", name="uq_item_name_dept"),
        db.CheckConstraint("reorder_level >= 0", name="ck_item_reorder_nonneg"),
    )

    def recipe_to_stock(self, recipe_qty: Decimal) -> Decimal:
        """Convert a recipe quantity to stock units. 50ml recipe → 0.0667 bottles (pack_size=750)."""
        if self.pack_size and Decimal(str(self.pack_size)) > 0:
            return recipe_qty / Decimal(str(self.pack_size))
        return recipe_qty

    def recipe_unit_cost(self) -> Decimal | None:
        """Cost per recipe unit. KSh 1200/bottle ÷ 750ml = KSh 1.60/ml."""
        if self.cost_per_unit is None:
            return None
        cpu = Decimal(str(self.cost_per_unit))
        if self.pack_size and Decimal(str(self.pack_size)) > 0:
            return cpu / Decimal(str(self.pack_size))
        return cpu

    def effective_tolerance(self, system_default: Decimal = Decimal("5")) -> Decimal:
        """Returns this item's tolerance %, falling back to the system default."""
        if self.tolerance_percent is not None:
            return Decimal(str(self.tolerance_percent))
        # Watch-list items get half the system default tolerance
        if self.is_watch_list:
            return system_default / 2
        return system_default

    def __repr__(self):
        return f"<InventoryItem {self.name} ({self.unit})>"
