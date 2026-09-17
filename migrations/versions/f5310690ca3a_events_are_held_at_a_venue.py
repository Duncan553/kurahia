"""Events are held at a venue

Every event now books one of the resort's EVENT_VENUE resources, so the API can
refuse a guest count the space cannot hold and two open events in the same
space at the same time. Before this, "where" was free text.

Nullable: events created before venues existed have none. The API requires a
venue on every new event.

Revision ID: f5310690ca3a
Revises: c1282c1760b3
Create Date: 2026-09-17 14:33:04.671402
"""
from alembic import op
import sqlalchemy as sa


revision = 'f5310690ca3a'
down_revision = 'c1282c1760b3'
branch_labels = None
depends_on = None

FK_NAME = 'fk_events_venue_id_bookable_resources'


def upgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('venue_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_events_venue_id'), ['venue_id'], unique=False)
    # Same constraint as the model declares. SQLite cannot add a foreign key to
    # an existing table without a rebuild that FK enforcement blocks — see
    # 7c1d4e2f9a30. Postgres (production) gets it in place.
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key(FK_NAME, 'events', 'bookable_resources', ['venue_id'], ['id'])


def downgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint(FK_NAME, 'events', type_='foreignkey')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_venue_id'))
        batch_op.drop_column('venue_id')
