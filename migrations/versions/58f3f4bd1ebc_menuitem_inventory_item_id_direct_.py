"""MenuItem.inventory_item_id: direct depletion for pass-through items

A menu item is stock-tracked one of two ways, which is the standard split in
bar and restaurant systems:

  RECIPE  — a composed item (cocktail, burger, spa treatment) draws down several
            ingredients through RecipeLine rows.
  DIRECT  — a pass-through item (bottled Tusker, an apple) IS the inventory item;
            selling one deducts exactly one unit. This column is that link.

Autogenerate also wanted to add a foreign key on tabs.assigned_to_id, which is
PRE-EXISTING drift between the model and the database, not part of this change.
It was removed so this migration does one thing. See docs/TODO_FOUND_ISSUES.md.

Revision ID: 58f3f4bd1ebc
Revises: 3a335b98e8dc
Create Date: 2026-08-27 02:55:08.811046
"""
from alembic import op
import sqlalchemy as sa


revision = '58f3f4bd1ebc'
down_revision = '3a335b98e8dc'
branch_labels = None
depends_on = None

# Named explicitly: SQLite runs these through batch mode, which rebuilds the
# table, and an unnamed constraint cannot be dropped again on downgrade.
FK_NAME = 'fk_menu_items_inventory_item_id'
IX_NAME = 'ix_menu_items_inventory_item_id'


def upgrade():
    # NOT batch_alter_table.
    #
    # SQLite cannot ALTER a table to add a foreign key, so Alembic's batch mode
    # rebuilds it: create a copy, move the rows, DROP the original. That DROP
    # fails here — order_items and recipe_lines both reference menu_items, and
    # this app runs with FK enforcement ON, so the database refuses to drop a
    # table that other rows point at.
    #
    # Adding a NULLABLE column needs none of that: plain ADD COLUMN is supported
    # natively and touches no existing row. The FK is added only on backends that
    # can do it in place (Postgres in production). On SQLite the relationship
    # still holds at the ORM level, and prod gets the real constraint.
    op.add_column('menu_items', sa.Column('inventory_item_id', sa.String(length=36), nullable=True))
    op.create_index(IX_NAME, 'menu_items', ['inventory_item_id'], unique=False)

    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key(FK_NAME, 'menu_items', 'inventory_items',
                              ['inventory_item_id'], ['id'])


def downgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint(FK_NAME, 'menu_items', type_='foreignkey')
    op.drop_index(IX_NAME, table_name='menu_items')
    op.drop_column('menu_items', 'inventory_item_id')
