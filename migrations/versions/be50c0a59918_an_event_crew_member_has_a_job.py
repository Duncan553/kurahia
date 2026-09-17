"""An event crew member has a job

KITCHEN hears the plates, BAR the drinks, SERVICE is told when a dish is
ready for pickup, SETUP sets up. Nullable only for assignments made before
jobs existed; the API requires one on every new assignment.

Revision ID: be50c0a59918
Revises: 8261a12ee61c
Create Date: 2026-09-17 16:06:40.453135

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'be50c0a59918'
down_revision = '8261a12ee61c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job', sa.String(length=10), nullable=True))



def downgrade():
    with op.batch_alter_table('event_assignments', schema=None) as batch_op:
        batch_op.drop_column('job')

