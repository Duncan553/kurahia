"""
InventoryItem — a physical stock item tracked in a department.
Units are free-text strings (kg, crate, litre, bottle, etc.) — never hardcoded.
is_watch_list → tighter tolerance + daily count cadence.
is_staff_food  → lives in Staff dept, excluded from sale-stock variance and judge.
is_alcoholic   → liquor. Only a manager may put it in a recipe or link it to a sale.
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

    # Is this stock line liquor? Set by a manager, and it is the only way the
    # menu guards can TELL. Alcohol was gated on MenuItem.is_alcoholic alone —
    # a flag on the sale — so nothing stopped a bar lead binding White Rum into
    # the recipe for a "Virgin Mojito": a soft-drink price, a soft-drink
    # authority, and a bottle of rum leaving the store to cover it. The pour is
    # where liquor is stolen, so the pour is where the flag has to live too.
    is_alcoholic = db.Column(db.Boolean, nullable=False, default=False)

    # Pack-aware fields for spirits/cocktails: pack_size=750, pack_unit="ml" means
    # 1 bottle = 750 ml. Recipes specify ml; stock tracks bottles.
    # NULL = non-pack item (flour, rice) — recipe unit matches stock unit.
    pack_size = db.Column(db.Numeric(12, 4), nullable=True)
    pack_unit = db.Column(db.String(30), nullable=True)
    category  = db.Column(db.String(50), nullable=True)

    # ── How this is BOUGHT ───────────────────────────────────────────────────
    # Stock is counted in `unit` (bottle, kg), but nobody buys a bottle of
    # Tusker — they buy a crate of 25, a box of 24 waters, a bale of flour.
    # Receiving used to mean doing that multiplication in your head and typing
    # 150, which is where "6 crates" quietly becomes 120 or 250 bottles and the
    # count never reconciles again.
    #
    # purchase_pack_size is how many `unit`s are in one pack: crate = 25 bottles.
    # NULL means the item is bought in its own unit (a kg of onions is a kg).
    purchase_pack_name = db.Column(db.String(30), nullable=True)   # "crate", "box", "bale"
    purchase_pack_size = db.Column(db.Numeric(12, 4), nullable=True)  # 25

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

    def pack_to_stock(self, packs: Decimal) -> Decimal:
        """Convert a bought quantity to stock units. 6 crates → 150 bottles.

        The mirror of recipe_to_stock: one turns what the CHEF says into stock,
        this turns what the SUPPLIER delivers into stock. Both exist so the
        ledger can hold one canonical unit while the people using it speak
        their own — crates at the door, bottles on the shelf, millilitres in
        the glass.
        """
        if self.purchase_pack_size and Decimal(str(self.purchase_pack_size)) > 0:
            return packs * Decimal(str(self.purchase_pack_size))
        return packs

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
