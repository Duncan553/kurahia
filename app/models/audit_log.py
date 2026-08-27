"""
AuditLog — tamper-evident, append-only, hash-chained log.

How the chain works:
  entry_hash = SHA-256( actor + action + target + timestamp + prev_hash )

  Each row's entry_hash covers the previous row's hash, so if anyone
  edits or deletes a past row, every subsequent hash becomes invalid.
  Verify the chain with AuditLog.verify_chain().

Rule: NEVER delete or update rows. Corrections = new rows with action="correction".
"""
import uuid
import hashlib
from datetime import datetime, timezone
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who did it (username string — stored even if user is later deleted)
    actor = db.Column(db.String(80), nullable=False)

    # What happened (e.g. "user.login", "user.create", "pin.reset")
    action = db.Column(db.String(100), nullable=False)

    # Who/what was affected (e.g. username of target user)
    target = db.Column(db.String(200), nullable=True)

    # Extra context — JSON string, kept as Text so no JSON type incompatibility
    details = db.Column(db.Text, nullable=True)

    # UTC server timestamp
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Hash of the previous row's entry_hash (NULL for row #1)
    prev_hash = db.Column(db.String(64), nullable=True)

    # SHA-256 of (actor+action+target+timestamp.isoformat+prev_hash)
    entry_hash = db.Column(db.String(64), nullable=False)

    @staticmethod
    def _compute_hash(actor: str, action: str, target: str, timestamp: datetime, prev_hash: str | None) -> str:
        """
        Deterministic hash of row content + chain link.
        Timestamps are normalised to naive UTC ISO strings so SQLite and Postgres
        both produce the same input string (SQLite drops tzinfo on retrieval).
        """
        if timestamp.tzinfo is not None:
            # Convert aware datetime → naive UTC for consistent isoformat
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        raw = f"{actor}|{action}|{target or ''}|{timestamp.isoformat()}|{prev_hash or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def log(cls, actor: str, action: str, target: str = None, details: str = None):
        """
        Append a new audit entry. Must be called inside an active db session.
        Automatically fetches the last entry_hash to form the chain link.
        """
        # Read the chain tail UNDER A LOCK.
        #
        # Without with_for_update() two concurrent requests both read the same
        # "latest" row and both chain off it, so one entry silently skips its
        # predecessor and verify_chain() then reports the history as BROKEN
        # forever — from ordinary traffic, not tampering. Observed on the dev
        # database: two order_item.receive entries 6.6ms apart, the second
        # chained off the row before the first.
        #
        # That is worse than having no chain: an alarm that is always sounding
        # cannot distinguish a real rewrite from a busy Saturday. This is the
        # same serialisation the codebase already uses for wristband numbering
        # (app/services/gate.py) — the identical "append to a sequence" problem.
        #
        # with_for_update() is a no-op on SQLite, which has no row locks; dev is
        # single-writer so it does not bite there, and production is Postgres
        # where the lock is real.
        last = (db.session.query(cls)
                .order_by(cls.timestamp.desc())
                .with_for_update()
                .first())
        prev_hash = last.entry_hash if last else None

        now = datetime.now(timezone.utc)
        entry_hash = cls._compute_hash(actor, action, target, now, prev_hash)

        entry = cls(
            actor=actor,
            action=action,
            target=target,
            details=details,
            timestamp=now,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        db.session.add(entry)
        # Caller is responsible for db.session.commit()
        return entry

    @classmethod
    def verify_chain(cls) -> tuple[bool, str]:
        """
        Walk every row in timestamp order and re-compute each entry_hash.
        Returns (True, "ok") if intact, (False, reason) if broken.
        """
        rows = db.session.query(cls).order_by(cls.timestamp.asc()).all()
        prev_hash = None
        for row in rows:
            expected = cls._compute_hash(
                row.actor, row.action, row.target, row.timestamp, prev_hash
            )
            if expected != row.entry_hash:
                return False, f"Chain broken at entry {row.id} ({row.action} by {row.actor})"
            prev_hash = row.entry_hash
        return True, "ok"

    def __repr__(self):
        return f"<AuditLog {self.actor}:{self.action} @ {self.timestamp}>"
