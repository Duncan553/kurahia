"""
auth_decorators.py — Drop-in replacement for @jwt_required() that adds
the kill-switch check on every protected endpoint.

Usage:
    from app.utils.auth_decorators import require_active_user

    @blueprint.get("/some-route")
    @require_active_user
    def my_view():
        user_id = get_jwt_identity()   # still works normally
        ...

Why this exists:
    @jwt_required() only validates the token's signature and expiry.
    It does NOT check is_active or timed lockout. Without this decorator,
    a fired employee's still-valid JWT can access every non-auth endpoint.
    This decorator adds one DB fetch + the same check that login uses,
    so deactivation takes effect within milliseconds on every endpoint.
"""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.utils.auth import check_active_and_unlocked


def require_active_user(fn):
    @wraps(fn)
    def _inner(*args, **kwargs):
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found."}), 401
        ok, msg = check_active_and_unlocked(user)
        if not ok:
            return jsonify({"error": msg}), 403
        return fn(*args, **kwargs)
    # Apply jwt_required LAST so it runs FIRST — token validated before kill-switch check
    return jwt_required()(_inner)
