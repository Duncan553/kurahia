"""charge check nonneg to nonzero

Cancelled order items now write a negative reversal Charge (append-only
correction — guest must not pay for cancelled food). The old amount >= 0
CHECK blocked those rows; amount != 0 still rejects junk zero rows.

Revision ID: a868b6111792
Revises: 3608347f51bd
Create Date: 2026-06-12 20:32:18.032560

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a868b6111792'
down_revision = '3608347f51bd'
branch_labels = None
depends_on = None


def upgrade():
    # batch mode: SQLite can't ALTER constraints in place — table is rebuilt
    with op.batch_alter_table("charges", schema=None) as batch_op:
        batch_op.drop_constraint("ck_charge_amount_nonneg", type_="check")
        batch_op.create_check_constraint("ck_charge_amount_nonzero", "amount != 0")


def downgrade():
    with op.batch_alter_table("charges", schema=None) as batch_op:
        batch_op.drop_constraint("ck_charge_amount_nonzero", type_="check")
        batch_op.create_check_constraint("ck_charge_amount_nonneg", "amount >= 0")
