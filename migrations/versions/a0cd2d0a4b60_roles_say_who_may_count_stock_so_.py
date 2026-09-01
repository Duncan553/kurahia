"""roles say who may count stock, so counting is not owner-only

Revision ID: a0cd2d0a4b60
Revises: 848b4885d999
Create Date: 2026-09-01 12:29:44.591937

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0cd2d0a4b60'
down_revision = '848b4885d999'
branch_labels = None
depends_on = None


# The roles that actually hold stock, plus the manager who spot-checks it.
# Autogenerate cannot know these; without the grant the column would land as
# all-False and counting would still be owner-only, which is the bug this
# migration exists to end.
GRANTED = (
    "manager",         # spot-checks any department
    "head_chef",       # Kitchen, 11 items
    "bar_lead",        # Bar, 12 items
    "water_lead",      # Water Activities, 4 items
    "spa_attendant",   # Spa & Gym, 4 items
    "housekeeping",    # Housekeeping, 4 items
    "grounds",         # Grounds, 3 items
)


def upgrade():
    # A PLAIN add_column, not batch_alter_table. Batch mode rebuilds the whole
    # table — create temp, copy, drop, rename — and `roles` is referenced by
    # users.role_id, so the drop trips "FOREIGN KEY constraint failed" and
    # leaves a stray _alembic_tmp_roles behind that masks the real error on the
    # next attempt. SQLite handles a straight ADD COLUMN natively; batch is only
    # needed for what it cannot do, like dropping a column or altering a type.
    #
    # server_default is required, not cosmetic: the column is NOT NULL and the
    # table already has rows, so without it the ALTER fails outright.
    op.add_column("roles", sa.Column("can_count_stock", sa.Boolean(),
                                     nullable=False, server_default=sa.false()))

    roles = sa.table("roles", sa.column("name", sa.String),
                     sa.column("can_count_stock", sa.Boolean))
    op.execute(roles.update()
               .where(roles.c.name.in_(GRANTED))
               .values(can_count_stock=True))
    # The owner is deliberately NOT in the list — the endpoint lets an owner
    # through on level alone, so the resort can never lock itself out of
    # counting by revoking a flag.


def downgrade():
    op.drop_column("roles", "can_count_stock")
