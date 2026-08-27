"""MenuItem.stock_tracking: make the tracking decision explicit

Two situations used to be stored the same way — as ABSENCE of a recipe:

    "this deliberately consumes nothing"  (a swimming pool day pass)
    "nobody has configured this yet"      (a jet ski that really burns fuel)

While those were indistinguishable the leak could not be enforced. A hard block
would have fired on the pool pass, staff would have learned the warning was
noise, and the real gaps would have kept leaking behind it.

BACKFILL POLICY — deliberately conservative:

  has recipe lines        -> RECIPE
  has inventory_item_id   -> DIRECT
  everything else         -> UNTRACKED

Nothing is auto-classified as SERVICE. SERVICE means "a human looked at this and
confirmed it consumes no stock", and this migration is not that human. Guessing
here would launder 16 unreviewed items into a clean-looking state and defeat the
entire point of the column.

Revision ID: 9b2e5c71f40a
Revises: 7c1d4e2f9a30
"""
from alembic import op
import sqlalchemy as sa


revision = '9b2e5c71f40a'
down_revision = '7c1d4e2f9a30'
branch_labels = None
depends_on = None


def upgrade():
    # Added with a server_default so existing rows satisfy NOT NULL immediately;
    # the default is then dropped so the application layer owns the value.
    op.add_column('menu_items', sa.Column(
        'stock_tracking', sa.String(length=12),
        nullable=False, server_default='UNTRACKED',
    ))

    # Backfill from what the data already proves.
    op.execute("""
        UPDATE menu_items SET stock_tracking = 'RECIPE'
        WHERE id IN (SELECT DISTINCT menu_item_id FROM recipe_lines WHERE is_active = 1)
    """)
    op.execute("""
        UPDATE menu_items SET stock_tracking = 'DIRECT'
        WHERE stock_tracking = 'UNTRACKED' AND inventory_item_id IS NOT NULL
    """)


def downgrade():
    op.drop_column('menu_items', 'stock_tracking')
