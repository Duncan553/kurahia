"""inventory: how an item is bought (crate, box) alongside how it is counted

Stock is counted in the item's own unit, but nobody buys a bottle of Tusker —
they buy a crate of 25. These two columns hold that, so receiving can count
crates at the delivery door while the ledger keeps one language.

Plain add_column on purpose. Alembic autogenerates batch_alter_table, which on
SQLite rebuilds the whole table to add a nullable column it can add in place —
slower, and it drops and recreates constraints for no reason.

Revision ID: c1282c1760b3
Revises: b6f99a94b64d
Create Date: 2026-09-15 14:04:15.019917
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1282c1760b3'
down_revision = 'b6f99a94b64d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('inventory_items',
                  sa.Column('purchase_pack_name', sa.String(length=30), nullable=True))
    op.add_column('inventory_items',
                  sa.Column('purchase_pack_size', sa.Numeric(precision=12, scale=4), nullable=True))


def downgrade():
    op.drop_column('inventory_items', 'purchase_pack_size')
    op.drop_column('inventory_items', 'purchase_pack_name')
