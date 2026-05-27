"""
User model — all humans in the system regardless of role.
Passwords: argon2 hash, used by manager/owner login.
PINs: argon2 hash, used by tablet/staff quick-login.
Both fields are nullable because:
  - a brand-new account has no PIN until first login
  - staff may never need a password
"""
import uuid
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from app.extensions import db

# Single hasher instance — argon2-cffi manages the expensive KDF parameters
_ph = PasswordHasher()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), nullable=False, unique=True)

    # Nullable: staff may only need a PIN; owner/manager need password
    password_hash = db.Column(db.Text, nullable=True)
    pin_hash = db.Column(db.Text, nullable=True)

    # First-login flag: forces PIN setup before any other action
    pin_set = db.Column(db.Boolean, nullable=False, default=False)

    role_id = db.Column(db.String(36), db.ForeignKey("roles.id"), nullable=False)
    department_id = db.Column(
        db.String(36), db.ForeignKey("departments.id"), nullable=True
    )

    # Kill-switch: owner/manager can flip is_active=False to immediately revoke access
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Lockout tracking
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

    # Who created this account (for hierarchy audit trail)
    created_by_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=True
    )

    # UTC timestamps — server stamps these, never the device
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    role = db.relationship("Role", back_populates="users")
    department = db.relationship("Department", back_populates="users")
    created_by = db.relationship("User", remote_side="User.id", foreign_keys=[created_by_id])

    # ── Password helpers ──────────────────────────────────────────────────────

    def set_password(self, plaintext: str) -> None:
        """Hash and store a password. Call inside a db.session.commit() block."""
        self.password_hash = _ph.hash(plaintext)

    def check_password(self, plaintext: str) -> bool:
        """Returns True if plaintext matches stored hash. False on any mismatch."""
        if not self.password_hash:
            return False
        try:
            return _ph.verify(self.password_hash, plaintext)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # ── PIN helpers ───────────────────────────────────────────────────────────

    def set_pin(self, plaintext: str) -> None:
        """Hash and store a PIN."""
        self.pin_hash = _ph.hash(plaintext)
        self.pin_set = True

    def check_pin(self, plaintext: str) -> bool:
        """Returns True if plaintext matches stored PIN hash."""
        if not self.pin_hash:
            return False
        try:
            return _ph.verify(self.pin_hash, plaintext)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # ── Lockout helpers ───────────────────────────────────────────────────────

    def is_locked(self) -> bool:
        """True if the account is currently in a timed lockout."""
        if self.locked_until is None:
            return False
        locked = self.locked_until
        # SQLite returns naive datetimes — treat as UTC for comparison
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < locked

    def reset_lockout(self) -> None:
        """Clear failed attempts and lockout — called on successful auth."""
        self.failed_attempts = 0
        self.locked_until = None

    def __repr__(self):
        return f"<User {self.username} role={self.role_id}>"
