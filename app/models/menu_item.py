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


class StockTracking(str, enum.Enum):
    """How a menu item's sale is expected to move stock.

    The point of this field is to separate two things that used to look
    identical, because both were stored as ABSENCE:

      "this deliberately consumes nothing"   (a swimming pool day pass)
      "nobody has configured this yet"       (a jet ski that really burns fuel)

    While those were indistinguishable, the leak could not be enforced: a hard
    block would have fired on the pool pass, staff would have learned the warning
    was noise, and the genuine gaps would have kept leaking behind it.

    UNTRACKED is therefore the only problem state, and it is the one an item may
    not go live in.
    """
    RECIPE    = "RECIPE"      # composed: draws down ingredients via RecipeLine
    DIRECT    = "DIRECT"      # pass-through: IS an inventory item (a Tusker, an apple)
    SERVICE   = "SERVICE"     # consumes no stock, and someone SAID SO on purpose
    UNTRACKED = "UNTRACKED"   # nobody has decided yet — not sellable


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

    # ── Who may author this item ──────────────────────────────────────────────
    # The head chef writes the FOOD and the JUICES — what the kitchen cooks and
    # what the bar squeezes. Alcohol is not theirs: a drinks list is a licensed,
    # excised, management-priced thing in every hotel, and the person who
    # designs a dish is not the person who signs for the liquor.
    #
    # This is a COLUMN and not a match on category, because `category` is
    # free text the owner edits in the admin panel ("Beer", "Beers", "Draught").
    # A permission boundary that breaks when somebody renames a category is not
    # a boundary. Engineering invariant 10: configuration through data.
    is_alcoholic = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

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

    # Declared intent, not inference. See StockTracking above.
    stock_tracking = db.Column(
        db.String(12), nullable=False, default=StockTracking.UNTRACKED.value
    )

    department = db.relationship("Department", lazy="select")

    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_menuitem_price_nonneg"),
        db.UniqueConstraint("name", "department_id", name="uq_menuitem_name_dept"),
    )

    def __repr__(self):
        return f"<MenuItem {self.name} {self.price} ({self.prep_station})>"
