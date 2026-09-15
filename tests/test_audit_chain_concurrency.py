"""The audit chain has to survive a busy Saturday.

Appending is read-the-tail-then-write, which two threads can interleave: both
read the same latest row, both chain off it, and one entry silently skips its
predecessor. verify_chain() then reports the history as BROKEN forever — from
ordinary traffic, not from tampering. An alarm that is always sounding cannot
tell a real rewrite from a busy service.

It was fixed once with with_for_update(), whose own comment notes that SQLite
has no row locks. Dev runs SQLite on Flask's threaded server, so the fix did
nothing where it was being used: three taps on "Start cooking" in quick
succession broke the chain on the development database.
"""
import threading

import pytest

from app import create_app
from app.extensions import db
from app.models.audit_log import AuditLog


@pytest.fixture
def file_app(tmp_path):
    """A file-backed SQLite app, built the way the dev server builds one.

    Two things this has to get right:

    * the suite's usual database is ONE shared in-memory connection
      (StaticPool), so two threads inside it collide with "cannot start a
      transaction within a transaction" — the harness serialises exactly what
      this test needs to run in parallel;
    * config.py reads DATABASE_URL at IMPORT time and app/__init__ binds the
      config map at import too, so setting the env var here does nothing. The
      first version of this test silently ran against the developer's own
      kurahia_dev.db — the assert below is what caught it, and it stays.
    """
    from config import config as config_map

    dev = config_map["development"]
    original = dev.SQLALCHEMY_DATABASE_URI
    dev.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/audit.db"
    try:
        app = create_app("development")
        assert str(tmp_path) in app.config["SQLALCHEMY_DATABASE_URI"], \
            "refusing to run: this test is not pointed at its own database"
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.session.remove()
    finally:
        dev.SQLALCHEMY_DATABASE_URI = original


def test_chain_survives_concurrent_appends(file_app):
    """Six tills writing at once, twelve entries each."""
    app = file_app
    errors = []

    def worker(n):
        with app.app_context():
            try:
                for i in range(12):
                    AuditLog.log(actor=f"till{n}", action="order_item.receive",
                                 target=f"{n}-{i}")
                    db.session.commit()
            except Exception as exc:                      # pragma: no cover
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors

    with app.app_context():
        written = db.session.query(AuditLog).count()
        ok, msg = AuditLog.verify_chain()

    assert written >= 60, f"only {written} entries survived"
    assert ok, msg
