"""
MenuItem — what the venue sells.
prep_station determines routing:
  KITCHEN → food prep queue
  BAR     → drinks queue
  NONE    → no queue; item is SERVED immediately (spa, water activities)
Price is Decimal. History is preserved via unit_price_snapshot on OrderItem.
"""
import uuid
import enum
from decimal import Decimal
from app.extensions import db


class PrepStation(str, enum.Enum):
    KITCHEN = "KITCHEN"
    BAR     = "BAR"
    NONE    = "NONE"


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name          = db.Column(db.String(150), nullable=False)
    price         = db.Column(db.Numeric(14, 2), nullable=False)
    category      = db.Column(db.String(80), nullable=True)    # e.g. "Main", "Cocktail", "Spa"
    prep_station  = db.Column(db.String(10), nullable=False, default=PrepStation.NONE.value)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=False)
    description    = db.Column(db.Text, nullable=True)
    image_path     = db.Column(db.String(500), nullable=True)
    allergens      = db.Column(db.String(500), nullable=True)   # comma-separated: "dairy, nuts, gluten"
    dietary_flags  = db.Column(db.String(200), nullable=True)   # comma-separated: "vegetarian, halal, vegan"
    is_active      = db.Column(db.Boolean, nullable=False, default=True)

    # ── Direct depletion (the "Tusker / apple" case) ──────────────────────────
    # A menu item is stock-tracked in one of two ways, which is the standard
    # split in bar and restaurant systems:
    #
    #   RECIPE  — a composed item. A cocktail, a burger, or a spa treatment
    #             ("back bar" usage) draws down several ingredients through
    #             RecipeLine rows.
    #   DIRECT  — a pass-through item. A bottled Tusker or an apple IS the
    #             inventory item; selling one deducts exactly one unit of it.
    #             Nobody should have to write a one-line "recipe" for a beer.
    #
    # Null on both means the item is UNTRACKED: it sells, but stock never moves.
    # consume_order_item() raises a no-recipe notification in that case so the
    # gap is visible rather than silent.
    inventory_item_id = db.Column(
        db.String(36), db.ForeignKey("inventory_items.id"), nullable=True, index=True
    )

    department = db.relationship("Department", lazy="select")

    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_menuitem_price_nonneg"),
        db.UniqueConstraint("name", "department_id", name="uq_menuitem_name_dept"),
    )

    def __repr__(self):
        return f"<MenuItem {self.name} {self.price} ({self.prep_station})>"
