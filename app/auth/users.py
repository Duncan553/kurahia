"""
users.py — Account creation, hierarchy enforcement, and user management.

Hierarchy rule: you can only create accounts for roles BELOW your own level.
  owner (10) → can create managers (5) and staff (1)
  manager (5) → can only create staff (1)
  staff (1)   → cannot create anyone

POST /auth/users        → create account
GET  /auth/users        → list users (manager sees own dept; owner sees all)
POST /auth/users/<id>/activate → re-activate a deactivated account
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.models.employee_profile import EmployeeProfile
from app.models.audit_log import AuditLog

users_bp = Blueprint("users", __name__, url_prefix="/auth/users")

OWNER_LEVEL   = 10
MANAGER_LEVEL = 5


@users_bp.post("")
@require_active_user
def create_user():
    actor_id = get_jwt_identity()
    actor = db.session.get(User, actor_id)

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password")  # Optional for staff-only accounts
    role_id = data.get("role_id")
    department_id = data.get("department_id")

    if not username or not role_id:
        return jsonify({"error": "username and role_id are required"}), 400

    target_role = db.session.get(Role, role_id)
    if not target_role:
        return jsonify({"error": "Role not found"}), 404

    # Core hierarchy rule: creator must outrank the new account's role
    if actor.role.level <= target_role.level:
        return jsonify({"error": "Cannot create an account at or above your own role level."}), 403

    # Username must be unique
    if db.session.query(User).filter_by(username=username).first():
        return jsonify({"error": "Username already exists."}), 409

    # Validate department if provided
    if department_id:
        dept = db.session.get(Department, department_id)
        if not dept or not dept.is_active:
            return jsonify({"error": "Department not found or inactive."}), 404

    with db.session.begin_nested():
        new_user = User(
            username=username,
            role_id=role_id,
            department_id=department_id,
            created_by_id=actor.id,
        )
        if password:
            new_user.set_password(password)
        db.session.add(new_user)

    AuditLog.log(
        actor=actor.username,
        action="user.create",
        target=new_user.username,
        details=f"role={target_role.name}",
    )
    db.session.commit()

    return jsonify({
        "id": new_user.id,
        "username": new_user.username,
        "role": target_role.name,
        "pin_set": new_user.pin_set,
    }), 201


@users_bp.patch("/<user_id>")
@require_active_user
def edit_user(user_id):
    """Edit username, password, role, or department. Actor must outrank the target."""
    actor = db.session.get(User, get_jwt_identity())
    target = db.session.get(User, user_id)

    if not target:
        return jsonify({"error": "User not found."}), 404
    if actor.role.level <= target.role.level:
        return jsonify({"error": "You can only edit users below your own role level."}), 403

    data = request.get_json(silent=True) or {}

    with db.session.begin_nested():
        if "username" in data:
            new_name = data["username"].strip().lower()
            clash = db.session.query(User).filter_by(username=new_name).first()
            if clash and clash.id != target.id:
                return jsonify({"error": "That username is already taken."}), 409
            target.username = new_name
        if "password" in data:
            target.set_password(data["password"])
        if "role_id" in data:
            new_role = db.session.get(Role, data["role_id"])
            if not new_role:
                return jsonify({"error": "Role not found."}), 404
            if actor.role.level <= new_role.level:
                return jsonify({"error": "Cannot assign a role at or above your own level."}), 403
            target.role_id = new_role.id
        if "department_id" in data:
            dept = db.session.get(Department, data["department_id"])
            if not dept or not dept.is_active:
                return jsonify({"error": "Department not found or disabled."}), 404
            target.department_id = dept.id

    AuditLog.log(actor=actor.username, action="user.edit", target=target.username)
    db.session.commit()

    return jsonify({"id": target.id, "username": target.username}), 200


@users_bp.get("")
@require_active_user
def list_users():
    actor = db.session.get(User, get_jwt_identity())
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"

    q = (request.args.get("q") or "").strip()

    query = db.session.query(User)
    if q:
        query = query.filter(User.username.ilike(f"%{q}%"))
    if not include_disabled:
        query = query.filter_by(is_active=True)

    # Department leads (level 3, e.g. head_chef/bar_lead) only need to see
    # their own team — scope them. Manager (5) and owner (10) run the whole
    # floor across every department, so neither gets scoped: a manager whose
    # own department is "Management" would otherwise never see a single
    # waiter/kitchen/bar/housekeeping user, which broke every cross-department
    # assignment flow (waiter table assignment, housekeeping assignment) the
    # moment the actor was a manager rather than the owner.
    if actor.role.level < MANAGER_LEVEL and actor.department_id:
        query = query.filter_by(department_id=actor.department_id)

    return jsonify([
        {
            "id":         u.id,
            "username":   u.username,
            "role":       u.role.name,
            "department": u.department.name if u.department else None,
            "is_active":  u.is_active,
            "pin_set":    u.pin_set,
        }
        for u in query.all()
    ]), 200


@users_bp.get("/meta")
@require_active_user
def get_meta():
    """Return roles and departments — used by manager account-creation UI."""
    from app.models.role import Role
    from app.models.department import Department
    actor = db.session.get(User, get_jwt_identity())
    # Only return roles the actor is allowed to assign (strictly below their own level)
    roles = db.session.query(Role).filter(Role.level < actor.role.level).all()
    depts = db.session.query(Department).filter_by(is_active=True).all()
    return jsonify({
        "roles": [{"id": r.id, "name": r.name, "level": r.level} for r in roles],
        "departments": [{"id": d.id, "name": d.name} for d in depts],
    }), 200


@users_bp.post("/<user_id>/activate")
@require_active_user
def activate_user(user_id):
    actor = db.session.get(User, get_jwt_identity())
    target = db.session.get(User, user_id)

    if not target:
        return jsonify({"error": "User not found."}), 404
    if actor.role.level <= target.role.level:
        return jsonify({"error": "You don't have the authority to activate this account."}), 403

    # If this account was locked out via a disabled EmployeeProfile — an
    # owner-only action (hr/profiles.py disable_profile) — only the owner can
    # undo it here too. Without this, any outranking manager could silently
    # reverse a decision the system otherwise reserves for the owner.
    profile = db.session.query(EmployeeProfile).filter_by(user_id=target.id).first()
    if profile and not profile.is_active and actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "This account was disabled at the profile level — only the owner can re-activate it."}), 403

    with db.session.begin_nested():
        target.is_active = True
        if profile and not profile.is_active:
            profile.is_active = True

    AuditLog.log(actor=actor.username, action="user.activate", target=target.username)
    db.session.commit()

    return jsonify({"message": f"{target.username} has been re-activated."}), 200
