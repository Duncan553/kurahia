"""
hr/profiles.py — EmployeeProfile CRUD.
Manager+ creates/edits; owner disables/enables.
Each profile is a 1:1 extension of a User record.
"""
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile, WagePeriod
from app.models.audit_log import AuditLog

profiles_bp = Blueprint("hr_profiles", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


@profiles_bp.post("/profiles")
@jwt_required()
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
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.profile.create", target=user_id,
                 details=full_name)
    db.session.commit()
    return jsonify({"id": profile.id, "user_id": user_id, "full_name": full_name}), 201


@profiles_bp.get("/profiles")
@jwt_required()
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
        "phone":     p.phone,
        "hire_date": p.hire_date.isoformat() if p.hire_date else None,
        "is_active": p.is_active,
        "wage_rate": str(p.wage_rate) if p.wage_rate else None,
        "wage_period": p.wage_period,
    } for p in profiles]), 200


@profiles_bp.get("/profiles/<profile_id>")
@jwt_required()
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
    }), 200


@profiles_bp.patch("/profiles/<profile_id>")
@jwt_required()
def edit_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404

    data = request.get_json(silent=True) or {}
    if "full_name" in data:
        profile.full_name = data["full_name"].strip()
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
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.profile.edit", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "full_name": profile.full_name, "is_active": profile.is_active}), 200


@profiles_bp.post("/profiles/<profile_id>/disable")
@jwt_required()
def disable_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can disable employee profiles."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404
    profile.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.profile.disable", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "is_active": False}), 200


@profiles_bp.post("/profiles/<profile_id>/enable")
@jwt_required()
def enable_profile(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can enable employee profiles."}), 403
    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404
    profile.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.profile.enable", target=profile_id)
    db.session.commit()
    return jsonify({"id": profile.id, "is_active": True}), 200
