"""Add the missing foreign key on tabs.assigned_to_id

MODEL/DATABASE DRIFT. app/models/tab.py:44 declares

    assigned_to_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

but the database never got the constraint — `PRAGMA foreign_key_list(tabs)`
returned only opened_by_id and closed_by_id. So the column accepted any string,
including a user id that does not exist or one that was later removed.

That quietly undercuts invariant 9: "DB-level enforcement of every business rule
that can be a constraint ... FKs everywhere. Defense in depth." The ORM
relationship still worked, which is exactly why nobody noticed.

Tests were never affected: they build the schema with db.create_all() straight
from the models, so the FK is present there. Only databases built by migrations
— which is production — carry the gap.

Revision ID: 7c1d4e2f9a30
Revises: 58f3f4bd1ebc
"""
from alembic import op


revision = '7c1d4e2f9a30'
down_revision = '58f3f4bd1ebc'
branch_labels = None
depends_on = None

FK_NAME = 'fk_tabs_assigned_to_id_users'


def upgrade():
    # SQLite cannot ALTER a foreign key into an existing table. Alembic's batch
    # mode works around that by rebuilding the table — copy, move rows, DROP the
    # original — but that DROP fails here: orders, charges, payments and
    # wristbands all reference tabs, and this app runs with FK enforcement ON.
    #
    # Production is Postgres, where the constraint can be added in place, and
    # that is the deployment the gap actually matters for. Dev SQLite keeps the
    # ORM-level relationship; a rebuilt dev database gets the FK from
    # create_all() anyway.
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key(FK_NAME, 'tabs', 'users', ['assigned_to_id'], ['id'])


def downgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint(FK_NAME, 'tabs', type_='foreignkey')
