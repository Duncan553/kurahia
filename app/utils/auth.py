"""
auth.py — Shared auth helpers used by login and PIN endpoints.
Keeping lockout logic here means both auth paths (password + PIN)
use identical rules without duplication.
"""
from datetime import datetime, timezone, timedelta
from flask import current_app
from app.extensions import db
from app.models.audit_log import AuditLog


def record_failed_attempt(user, credential_type: str) -> dict:
    """
    Increment failed_attempts. Lock the account if threshold is reached.
    Returns a dict with 'locked' bool and 'message' string.
    Call inside a db transaction; caller commits.
    """
    max_attempts = current_app.config["FAILED_ATTEMPTS_LOCKOUT"]
    lockout_minutes = current_app.config["LOCKOUT_MINUTES"]

    user.failed_attempts += 1

    if user.failed_attempts >= max_attempts:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
        AuditLog.log(
            actor=user.username,
            action=f"{credential_type}.lockout",
            target=user.username,
            details=f"Locked for {lockout_minutes}min after {user.failed_attempts} failed attempts",
        )
        return {"locked": True, "message": f"Account locked for {lockout_minutes} minutes."}

    return {"locked": False, "message": "Invalid credentials."}


def check_active_and_unlocked(user) -> tuple[bool, str]:
    """
    Returns (ok, error_message).
    Checks: is_active (kill-switch) and timed lockout.
    Call this at the top of every protected request, not just login.
    """
    if not user.is_active:
        return False, "Your account is disabled. Contact your manager to re-enable it."
    if user.is_locked():
        locked = user.locked_until
        # SQLite returns naive datetimes — treat as UTC
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        remaining = (locked - datetime.now(timezone.utc)).seconds // 60
        return False, f"Account locked after too many failed attempts. Try again in ~{remaining} minutes."
    return True, ""
