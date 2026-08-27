"""
Guard against model/database drift.

This exists because of a real gap: app/models/tab.py declares

    assigned_to_id = db.Column(db.String(36), db.ForeignKey("users.id"), ...)

but the migration that created the table never added the constraint, so the
production database accepted any string there — including a user id that never
existed. It undercut invariant 9 ("DB-level enforcement of every business rule
that can be a constraint ... FKs everywhere") and nobody noticed, because the
ORM relationship kept working and the tests build their schema with
db.create_all() straight from the models rather than by running migrations.

That is the blind spot: create_all() can never disagree with the models, so a
test suite built on it can never see drift. These tests compare the two things
that actually have to agree.
"""
import pytest
from sqlalchemy import inspect

from app.extensions import db


def _model_foreign_keys():
    """{(table, column) -> referenced table} as the MODELS declare it."""
    out = {}
    for table in db.metadata.sorted_tables:
        for fk in table.foreign_keys:
            out[(table.name, fk.parent.name)] = fk.column.table.name
    return out


def _db_foreign_keys(bind):
    """{(table, column) -> referenced table} as the DATABASE actually enforces it."""
    insp = inspect(bind)
    out = {}
    for table_name in insp.get_table_names():
        for fk in insp.get_foreign_keys(table_name):
            for col in fk["constrained_columns"]:
                out[(table_name, col)] = fk["referred_table"]
    return out


def test_every_declared_foreign_key_exists_in_the_database(app):
    """
    The schema the app runs against must enforce every FK the models declare.

    Note this passes trivially on a create_all() database — which is the point
    of the companion test below. Here it protects against a model gaining a
    relationship that the metadata does not actually turn into a constraint.
    """
    declared = _model_foreign_keys()
    actual = _db_foreign_keys(db.engine)

    missing = {k: v for k, v in declared.items() if k not in actual}
    assert not missing, (
        "these foreign keys are declared on the models but NOT enforced by the "
        f"database: {sorted(missing)}"
    )


def test_tabs_assigned_to_id_is_a_real_constraint(app):
    """
    The specific regression. tabs.assigned_to_id was a FK in the model and a
    bare string column in the database.
    """
    actual = _db_foreign_keys(db.engine)
    assert actual.get(("tabs", "assigned_to_id")) == "users", (
        "tabs.assigned_to_id must be a real foreign key to users.id, not just an "
        "ORM relationship — otherwise a tab can be assigned to a user id that "
        "does not exist"
    )


def test_menu_item_inventory_link_is_a_real_constraint(app):
    """The direct-depletion link must be enforced too, for the same reason."""
    actual = _db_foreign_keys(db.engine)
    assert actual.get(("menu_items", "inventory_item_id")) == "inventory_items", (
        "MenuItem.inventory_item_id points at the stock row a pass-through sale "
        "deducts; a dangling id there would silently stop deducting"
    )


def test_every_table_has_a_primary_key(app):
    """A table without a PK cannot be safely updated, replicated or audited."""
    insp = inspect(db.engine)
    missing = [
        t for t in insp.get_table_names()
        if t != "alembic_version" and not insp.get_pk_constraint(t)["constrained_columns"]
    ]
    assert not missing, f"tables without a primary key: {missing}"
