"""
RecipeLine — one ingredient line in a menu item's recipe.
Append-only spirit: deactivating a menu item soft-deletes its lines via is_active=False.
One menu_item → many RecipeLines. The set of active lines IS the current recipe.
"""
import uuid
from decimal import Decimal
from app.extensions import db


class RecipeLine(db.Model):
    __tablename__ = "recipe_lines"

    id                 = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    menu_item_id       = db.Column(db.String(36), db.ForeignKey("menu_items.id"), nullable=False, index=True)
    inventory_item_id  = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=False)
    quantity           = db.Column(db.Numeric(12, 4), nullable=False)
    unit               = db.Column(db.String(30), nullable=False)   # copied from inventory item at save time
    is_active          = db.Column(db.Boolean, nullable=False, default=True)

    menu_item      = db.relationship("MenuItem",       lazy="select")
    inventory_item = db.relationship("InventoryItem",  lazy="select")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_recipe_line_qty_positive"),
    )

    def __repr__(self):
        return f"<RecipeLine menu={self.menu_item_id} item={self.inventory_item_id} qty={self.quantity}>"
