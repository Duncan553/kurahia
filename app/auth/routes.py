"""
auth/routes.py — Login, PIN setup/change, token refresh, and kill-switch.

Two login flows:
  POST /auth/login      → password login (manager/owner)
  POST /auth/pin-login  → PIN login (tablet/staff)

PIN lifecycle:
  POST /auth/set-pin    → first-time PIN setup (requires temp token from password login)
  POST /auth/change-pin → change own PIN (authenticated)

Account management:
  POST /auth/deactivate/<user_id>  → kill-switch (manager deactivates staff, owner deactivates managers)
  POST /auth/reset-lockout/<user_id> → reset another user's lockout (up-chain only)
"""
import json
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from app.extensions import db, limiter
from app.models.user import User, _ph
from app.models.audit_log import AuditLog
from app.utils.auth import record_failed_attempt, check_active_and_unlocked
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Pre-computed at startup. Burned on every failed lookup so timing is constant
# regardless of whether a username exists — prevents username enumeration via
# response-time measurement.
_DUMMY_HASH = _ph.hash("dummy-password-for-timing-equalization")


# ── Password login (manager / owner) ─────────────────────────────────────────

@auth_bp.post("/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    # Load from DB — re-check active/locked on every login attempt
    user = db.session.query(User).filter_by(username=username).first()

    # Both no-user and inactive-user paths use the same generic error message and
    # run a dummy verify so response time and content can't reveal whether a username
    # exists or is active. Real users who hit this in production should be guided to
    # ask their manager to check users.is_active.
    if not user or not user.is_active:
        try:
            _ph.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return jsonify({"error": "Invalid credentials."}), 401

    # User is active — check lockout only. Locked accounts get the lock message
    # (UX: the real user needs to know how long to wait).
    ok, msg = check_active_and_unlocked(user)
    if not ok:
        return jsonify({"error": msg}), 403

    if not user.check_password(password):
        result = record_failed_attempt(user, "password")
        db.session.commit()
        return jsonify({"error": result["message"]}), 401

    # Success — clear lockout counter, issue tokens
    user.reset_lockout()

    # If PIN not yet set, issue a short-lived "setup-only" token
    if not user.pin_set:
        setup_token = create_access_token(
            identity=user.id,
            additional_claims={"role_level": user.role.level, "requires_pin_setup": True},
            expires_delta=timedelta(minutes=10),
        )
        db.session.flush()
        AuditLog.log(actor=user.username, action="user.login.pending_pin_setup")
        db.session.commit()
        return jsonify({"access_token": setup_token, "requires_pin_setup": True}), 200

    access_token = create_access_token(
        identity=user.id,
        additional_claims={"role_level": user.role.level},
    )
    refresh_token = create_refresh_token(identity=user.id)

    db.session.flush()
    AuditLog.log(actor=user.username, action="user.login", details="password")
    db.session.commit()

    return jsonify({"access_token": access_token, "refresh_token": refresh_token}), 200


# ── PIN login (tablet / staff) ────────────────────────────────────────────────

@auth_bp.post("/pin-login")
def pin_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    pin = data.get("pin", "")

    if not username or not pin:
        return jsonify({"error": "username and pin required"}), 400

    user = db.session.query(User).filter_by(username=username).first()

    # Both no-user and inactive-user paths use the same generic error message and
    # run a dummy verify so response time and content can't reveal whether a username
    # exists or is active. Real users who hit this in production should be guided to
    # ask their manager to check users.is_active.
    if not user or not user.is_active:
        try:
            _ph.verify(_DUMMY_HASH, pin)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return jsonify({"error": "Invalid credentials."}), 401

    ok, msg = check_active_and_unlocked(user)
    if not ok:
        return jsonify({"error": msg}), 403

    if not user.pin_set:
        return jsonify({"error": "PIN not configured. Use password login first."}), 403

    if not user.check_pin(pin):
        result = record_failed_attempt(user, "pin")
        db.session.commit()
        return jsonify({"error": result["message"]}), 401

    user.reset_lockout()
    access_token = create_access_token(
        identity=user.id,
        additional_claims={"role_level": user.role.level},
    )
    refresh_token = create_refresh_token(identity=user.id)

    db.session.flush()
    AuditLog.log(actor=user.username, action="user.login", details="pin")
    db.session.commit()

    return jsonify({"access_token": access_token, "refresh_token": refresh_token}), 200


# ── Token refresh ─────────────────────────────────────────────────────────────

@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    # Re-fetch user from DB — catches deactivation between refresh calls
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    ok, msg = check_active_and_unlocked(user)
    if not ok:
        return jsonify({"error": msg}), 403

    new_token = create_access_token(
        identity=user.id,
        additional_claims={"role_level": user.role.level},
    )
    return jsonify({"access_token": new_token}), 200


# ── First-time PIN setup ──────────────────────────────────────────────────────

@auth_bp.post("/set-pin")
@jwt_required()
def set_pin():
    claims = get_jwt()
    # Only allow if token was issued with the setup flag
    if not claims.get("requires_pin_setup"):
        return jsonify({"error": "PIN already set. Use /change-pin."}), 400

    data = request.get_json(silent=True) or {}
    pin = data.get("pin", "")

    if len(pin) < 4 or not pin.isdigit():
        return jsonify({"error": "PIN must be at least 4 digits."}), 400

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)

    with db.session.begin_nested():
        user.set_pin(pin)

    AuditLog.log(actor=user.username, action="pin.set")
    db.session.commit()

    # Issue real tokens now that setup is complete
    access_token = create_access_token(
        identity=user.id,
        additional_claims={"role_level": user.role.level},
    )
    refresh_token = create_refresh_token(identity=user.id)
    return jsonify({"access_token": access_token, "refresh_token": refresh_token}), 200


# ── Change own PIN ────────────────────────────────────────────────────────────

@auth_bp.post("/change-pin")
@jwt_required()
def change_pin():
    data = request.get_json(silent=True) or {}
    current_pin = data.get("current_pin", "")
    new_pin = data.get("new_pin", "")

    if len(new_pin) < 4 or not new_pin.isdigit():
        return jsonify({"error": "New PIN must be at least 4 digits."}), 400

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)

    ok, msg = check_active_and_unlocked(user)
    if not ok:
        return jsonify({"error": msg}), 403

    if not user.check_pin(current_pin):
        return jsonify({"error": "Current PIN is incorrect."}), 401

    with db.session.begin_nested():
        user.set_pin(new_pin)

    AuditLog.log(actor=user.username, action="pin.changed")
    db.session.commit()

    return jsonify({"message": "PIN updated."}), 200


# ── Kill-switch (deactivate account) ─────────────────────────────────────────

@auth_bp.post("/deactivate/<target_user_id>")
@jwt_required()
def deactivate_user(target_user_id):
    actor_id = get_jwt_identity()
    actor = db.session.get(User, actor_id)
    target = db.session.get(User, target_user_id)

    if not target:
        return jsonify({"error": "User not found."}), 404

    # Hierarchy check: actor's role.level must be strictly higher than target's
    if actor.role.level <= target.role.level:
        return jsonify({"error": "Insufficient authority to deactivate this account."}), 403

    with db.session.begin_nested():
        target.is_active = False

    AuditLog.log(
        actor=actor.username,
        action="user.deactivate",
        target=target.username,
    )
    db.session.commit()

    return jsonify({"message": f"{target.username} deactivated."}), 200


# ── Reset lockout (up-chain only, no self-reset) ──────────────────────────────

@auth_bp.post("/reset-lockout/<target_user_id>")
@jwt_required()
def reset_lockout(target_user_id):
    actor_id = get_jwt_identity()
    actor = db.session.get(User, actor_id)
    target = db.session.get(User, target_user_id)

    if not target:
        return jsonify({"error": "User not found."}), 404

    # No self-reset
    if actor.id == target.id:
        return jsonify({"error": "Cannot reset your own lockout."}), 403

    # Must outrank the target
    if actor.role.level <= target.role.level:
        return jsonify({"error": "Insufficient authority."}), 403

    with db.session.begin_nested():
        target.reset_lockout()

    AuditLog.log(
        actor=actor.username,
        action="lockout.reset",
        target=target.username,
    )
    db.session.commit()

    return jsonify({"message": f"Lockout cleared for {target.username}."}), 200
