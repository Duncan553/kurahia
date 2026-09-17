"""An event carries a booking fee

Paid before confirming (like a villa deposit), kept if the event is cancelled.
Existing events get 0, which requires nothing.

Revision ID: 360741afb30f
Revises: be50c0a59918
Create Date: 2026-09-17 19:04:43.021117

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '360741afb30f'
down_revision = 'be50c0a59918'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('booking_fee', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False))



def downgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('booking_fee')

