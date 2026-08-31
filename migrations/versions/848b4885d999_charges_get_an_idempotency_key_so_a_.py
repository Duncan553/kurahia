"""charges get an idempotency key so a double-tapped charge cannot bill twice

Revision ID: 848b4885d999
Revises: 1fbe81ace9af
Create Date: 2026-09-01 01:35:24.592851

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '848b4885d999'
down_revision = '1fbe81ace9af'
branch_labels = None
depends_on = None


# SQLite rebuilds the whole table for an ALTER, so batch mode needs the
# constraint NAMED — autogenerate emits None and dies with "Constraint must
# have a name". Naming it also means the downgrade can find it again.
UQ = "uq_charges_idempotency_key"


def upgrade():
    with op.batch_alter_table("charges", schema=None) as batch_op:
        # Nullable: most charges do not come from a tap. An order item's charge
        # is already covered by the order's own key, and a reversal mirrors an
        # existing row. NULLs do not collide under UNIQUE in SQLite or Postgres.
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=64),
                                      nullable=True))
        batch_op.create_unique_constraint(UQ, ["idempotency_key"])


def downgrade():
    with op.batch_alter_table("charges", schema=None) as batch_op:
        batch_op.drop_constraint(UQ, type_="unique")
        batch_op.drop_column("idempotency_key")
