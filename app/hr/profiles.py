"""
hr/profiles.py — EmployeeProfile CRUD.
Manager+ creates/edits; owner disables/enables.
Each profile is a 1:1 extension of a User record.
"""
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile, WagePeriod
from app.models.audit_log import AuditLog

profiles_bp = Blueprint("hr_profiles", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


@profiles_bp.post("/profiles")
@require_active_user
def create_profile():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to create employee profiles."}), 403

    data     = request.get_json(silent=True) or {}
    user_id  = data.get("user_id")
    full_name = (data.get("full_name") or "").strip()
    phone    = (data.get("phone") or "").strip()

    if not user_id or not full_name or not phone:
        return jsonify({"error": "user_id, full_name, and phone are required."}), 400

    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({"error": "User not found."}), 404

    existing = db.session.query(EmployeeProfile).filter_by(user_id=user_id).first()
    if existing:
        return jsonify({"error": "An employee profile already exists for this user."}), 409

    # Optional fields
    wage_rate   = data.get("wage_rate")
    wage_period = (data.get("wage_period") or "").upper() or None
    if wage_period and wage_period not in WagePeriod.__members__:
        return jsonify({"error": f"wage_period must be one of {list(WagePeriod.__members__)}."}), 400
    if wage_rate is not None:
        try:
            wage_rate = Decimal(str(wage_rate))
        except InvalidOperation:
            return jsonify({"error": "wage_rate must be a number."}), 400

    hire_date_raw = data.get("hire_date")
    hire_date = None
    if hire_date_raw:
        try:
            hire_date = date.fromisoformat(hire_date_raw)
        except ValueError:
            return jsonify({"error": "hire_date must be YYYY-MM-DD."}), 400

    profile = EmployeeProfile(
        user_id=user_id,
        full_name=full_name,
        phone=phone,
        photo_path=data.get("photo_path"),
        national_id=data.get("national_id"),
        emergency_contact_name=data.get("emergency_contact_name"),
        emergency_contact_phone=data.get("emergency_contact_phone"),
        hire_date=hire_date,
        wage_rate=wage_rate,
        wage_period=wage_period,
    )
    db.session.add(profile)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.profile.create", target=user_id,
                 details=full_name)
    db.session.commit()
    return jsonify({"id": profile.id, "user_id": user_id, "full_name": full_name}), 201


@profiles_bp.get("/profiles")
@require_active_user
def list_profiles():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    query = db.session.query(EmployeeProfile)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    profiles = query.all()
    return jsonify([{
        "id":        p.id,
        "user_id":   p.user_id,
        "full_name": p.full_name,
        # Needed by every staff LIST that shows a face. It was on the single
        # profile response but not here, so a roster could never show a photo.
        "photo_path": p.photo_path,
        "phone":     p.phone,
        "hire_date": p.hire_date.isoformat() if p.hire_date else None,
        "is_active": p.is_active,
        "wage_rate": str(p.wage_rate) if p.wage_rate else None,
        "wage_period": p.wage_period,
        "payment_method":         p.payment_method,
        "payment_account_number": p.payment_account_number,
    } for p in profiles]), 200


@profiles_bp.get("/profiles/me")
@require_active_user
def get_my_profile():
    """Own profile — no manager check, any staff can read their own record.
    Used by employee_pwa's Profile screen (payment account section)."""
    actor = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id, is_active=True).first()
    if not profile:
        return jsonify({"error": "No employee profile found. Ask your manager to create one."}), 404
    return jsonify({
        "id":                     profile.id,
        "full_name":              profile.full_name,
        "photo_path":             profile.photo_path,
        "phone":                  profile.phone,
        "payment_method":         profile.payment_method,
        "payment_account_number": profile.payment_account_number,
    }), 200


PAYMENT_METHODS = {"MPESA", "BANK"}


@profiles_bp.patch("/profiles/me/payment")
@require_active_user
def set_my_payment_account():
    """Employee sets/edits their OWN payroll payment account. Deliberately a
    narrow endpoint (not the full edit_profile below) — an employee must never
    be able to touch wage_rate, hire_date, etc. on themselves; only manager+
    can via PATCH /hr/profiles/<id>."""
    actor = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id, is_active=True).first()
    if not profile:
        return jsonify({"error": "No employee profile found. Ask your manager to create one."}), 404

    data   = request.get_json(silent=True) or {}
    method = (data.get("payment_method") or "").strip().upper()
    number = (data.get("payment_account_number") or "").strip()

    if method not in PAYMENT_METHODS:
        return jsonify({"error": f"payment_method must be one of {sorted(PAYMENT_METHODS)}."}), 400
    if not number:
        return jsonify({"error": "payment_account_number is required."}), 400
    if len(number) > 60:
        return jsonify({"error": "payment_account_number is too long."}), 400

    profile.payment_method = method
    profile.payment_account_number = number
    profile.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    # Audit log only — never logs the account number itself (avoids putting
    # payroll PII in a log every manager/owner can read via /audit).
    AuditLog.log(actor=actor.username, action="hr.profile.set_payment",
                 target=profile.id, details=f"method={method}")
    db.session.commit()
    return jsonify({
        "payment_method": profile.payment_method,
        "payment_account_number": profile.payment_account_number,
    }), 200


@profiles_bp.get("/profiles/<profile_id>")
@require_active_user
def get_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404
    return jsonify({
        "id":            profile.id,
        "user_id":       profile.user_id,
        "full_name":     profile.full_name,
        "phone":         profile.phone,
        "national_id":   profile.national_id,
        "emergency_contact_name":  profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "hire_date":     profile.hire_date.isoformat() if profile.hire_date else None,
        "wage_rate":     str(profile.wage_rate) if profile.wage_rate else None,
        "wage_period":   profile.wage_period,
        "is_active":     profile.is_active,
        "photo_path":    profile.photo_path,
        "payment_method":         profile.payment_method,
        "payment_account_number": profile.payment_account_number,
    }), 200


@profiles_bp.patch("/profiles/<profile_id>")
@require_active_user
def edit_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404

    data = request.get_json(silent=True) or {}

    # ── Who may edit WHOSE file ───────────────────────────────────────────────
    # This checked the actor's level and nothing else — not whose file it was.
    # Two things fell out of that, and the same self-dealing rule already exists
    # two files away on smaller stakes: a manager may not override their own
    # clock (app/hr/clock.py) and may not approve their own leave
    # (app/hr/leave.py). Wages are the bigger number.
    target_user = profile.user
    editing_self = target_user is not None and target_user.id == actor.id
    pay_fields = {"wage_rate", "wage_period"}

    # 1. Nobody sets their own pay. A manager could set wage_rate to anything
    #    and /hr/payroll-draft would duly report it. Owner-only, and the owner
    #    is not exempt from being asked to have someone else do it either —
    #    but with one owner account that would deadlock the resort, so the
    #    owner keeps it and the audit row carries the name.
    if editing_self and pay_fields & data.keys() and actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "You cannot change your own pay. Ask the owner "
                                 "to do it, so the change has a second name on it."}), 403

    # 2. Nobody edits the file of somebody at or above their own level. Pointed
    #    upward, the missing check let a manager rewrite the OWNER's name, phone,
    #    emergency contact and wage.
    if (not editing_self and target_user is not None
            and target_user.role.level >= actor.role.level):
        return jsonify({"error": "You cannot edit the file of someone at or above "
                                 "your own role level."}), 403

    if "full_name" in data:
        profile.full_name = data["full_name"].strip()
    # A photo could be set at hire time and then never changed — create accepted
    # photo_path, this did not. Constrained to a path this system produced:
    # the value lands in an <img src>, so a free-text field here would let
    # somebody point a staff photo at an external URL (a tracking pixel that
    # fires every time a manager opens the roster) or at a javascript: scheme.
    if "photo_path" in data:
        raw = (data["photo_path"] or "").strip()
        if raw and not raw.startswith("/images/"):
            return jsonify({"error": "photo_path must be an uploaded image path "
                                     "(POST the file to /uploads/profile first)."}), 400
        profile.photo_path = raw or None
    if "phone" in data:
        profile.phone = data["phone"].strip()
    if "emergency_contact_name" in data:
        profile.emergency_contact_name = data["emergency_contact_name"]
    if "emergency_contact_phone" in data:
        profile.emergency_contact_phone = data["emergency_contact_phone"]
    if "wage_rate" in data:
        try:
            profile.wage_rate = Decimal(str(data["wage_rate"]))
        except InvalidOperation:
            return jsonify({"error": "wage_rate must be a number."}), 400
    if "wage_period" in data:
        wp = (data["wage_period"] or "").upper()
        if wp and wp not in WagePeriod.__members__:
            return jsonify({"error": f"wage_period must be one of {list(WagePeriod.__members__)}."}), 400
        profile.wage_period = wp or None
    if "hire_date" in data:
        try:
            profile.hire_date = date.fromisoformat(data["hire_date"])
        except (ValueError, TypeError):
            return jsonify({"error": "hire_date must be YYYY-MM-DD."}), 400

    profile.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.profile.edit", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "full_name": profile.full_name, "is_active": profile.is_active}), 200


@profiles_bp.post("/profiles/<profile_id>/disable")
@require_active_user
def disable_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can disable employee profiles."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404
    if profile.user_id == actor.id:
        return jsonify({"error": "You can't disable your own profile — several owner-lookup routines "
                                  "(judge alerts, low-stock notices) would silently stop finding an active "
                                  "owner. Have another owner-level account do this, or use flask seed owner first."}), 403
    profile.is_active = False
    # Kill-switch invariant: a disabled profile must also lock the login account,
    # or the still-valid JWT keeps working on every non-clock-gated endpoint
    # (require_active_user only checks User.is_active, never EmployeeProfile.is_active).
    if profile.user:
        profile.user.is_active = False
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.profile.disable", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "is_active": False}), 200


@profiles_bp.post("/profiles/<profile_id>/enable")
@require_active_user
def enable_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can enable employee profiles."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404
    profile.is_active = True
    # Mirror disable_profile's cascade so re-enabling a profile also restores login.
    if profile.user:
        profile.user.is_active = True
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.profile.enable", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "is_active": True}), 200
