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
    def _compute_hash(actor: str, action: str, target: str, timestamp: datetime,
                      prev_hash: str | None, details: str | None = None) -> str:
        """
        Deterministic hash of row content + chain link.
        Timestamps are normalised to naive UTC ISO strings so SQLite and Postgres
        both produce the same input string (SQLite drops tzinfo on retrieval).

        `details` IS COVERED. It was outside the hash, and that was the worst
        possible place for it to be: everything the trail says about WHAT
        CHANGED lives in details — "price 1800 -> 900", "PASSWORD RESET",
        "value={val}", "qty=… cost=…". Anyone with database write access could
        rewrite every one of those and /audit/verify would still answer
        "history is unaltered".

        That is worse than having no chain at all. With no chain the owner
        knows to be suspicious; with a chain that verifies a rewritten trail,
        the owner is told the lie is clean.
        """
        if timestamp.tzinfo is not None:
            # Convert aware datetime → naive UTC for consistent isoformat
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        raw = (f"{actor}|{action}|{target or ''}|{timestamp.isoformat()}"
               f"|{details or ''}|{prev_hash or ''}")
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
        entry_hash = cls._compute_hash(actor, action, target, now, prev_hash, details)

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
        cls._remember_head(entry_hash)
        # Caller is responsible for db.session.commit()
        return entry

    # ── The head marker: what makes a TRUNCATION visible ──────────────────────
    #
    # Walking the chain forward only proves each surviving row links to the one
    # before it. Delete the LAST n rows and every survivor still hashes
    # correctly, so the chain reports intact — and that is the exact shape a
    # cover-up takes: do the thing, then drop the tail of the log. A deletion in
    # the MIDDLE breaks the links and is caught; the tail was free.
    #
    # So the head is written down separately: the newest entry_hash and how many
    # rows there were. Verification compares the chain it can see against what
    # was last recorded, and a missing tail no longer matches.
    #
    # Honest about the limit: someone with full database write access can edit
    # this marker too. It is not a signed external anchor and does not pretend
    # to be. What it removes is the SILENT single-DELETE — the cheap version of
    # the attack. A real anchor means shipping the head off the box (printed at
    # close of day, mailed, or written to append-only storage), which is an
    # operations decision, not a code one.
    HEAD_KEY = "audit_chain_head"

    @staticmethod
    def _head_store():
        from app.models.system_setting import SystemSetting
        return SystemSetting

    @classmethod
    def _remember_head(cls, entry_hash: str) -> None:
        SystemSetting = cls._head_store()
        # No "+1 for the pending row": count() autoflushes, so the entry added
        # a line earlier is ALREADY counted. Adding one on top made every fresh
        # chain report itself one entry short of itself.
        db.session.flush()
        count = db.session.query(cls).count()
        row = db.session.get(SystemSetting, cls.HEAD_KEY)
        value = f"{entry_hash}:{count}"
        if row:
            row.value = value
        else:
            db.session.add(SystemSetting(key=cls.HEAD_KEY, value=value))

    @classmethod
    def verify_chain(cls) -> tuple[bool, str]:
        """
        Walk every row in timestamp order and re-compute each entry_hash, then
        check the visible chain against the recorded head.
        Returns (True, "ok") if intact, (False, reason) if broken.
        """
        rows = db.session.query(cls).order_by(cls.timestamp.asc()).all()
        prev_hash = None
        for row in rows:
            expected = cls._compute_hash(
                row.actor, row.action, row.target, row.timestamp, prev_hash,
                row.details,
            )
            if expected != row.entry_hash:
                return False, f"Chain broken at entry {row.id} ({row.action} by {row.actor})"
            prev_hash = row.entry_hash

        SystemSetting = cls._head_store()
        marker = db.session.get(SystemSetting, cls.HEAD_KEY)
        if marker and rows:
            want_hash, _, want_count = marker.value.partition(":")
            if want_count.isdigit() and len(rows) < int(want_count):
                return False, (
                    f"The trail is SHORTER than it should be: {len(rows)} entries "
                    f"present, {want_count} recorded. "
                    f"{int(want_count) - len(rows)} entr(ies) have been deleted "
                    f"from the end of the log."
                )
            if rows[-1].entry_hash != want_hash and len(rows) == int(want_count or 0):
                return False, ("The newest entry does not match the recorded head "
                               "— the end of the trail has been rewritten.")
        return True, "ok"

    def __repr__(self):
        return f"<AuditLog {self.actor}:{self.action} @ {self.timestamp}>"
