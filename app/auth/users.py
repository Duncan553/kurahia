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
from app.extensions import db
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.models.audit_log import AuditLog

users_bp = Blueprint("users", __name__, url_prefix="/auth/users")


@users_bp.post("")
@jwt_required()
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

    db.session.commit()
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


@users_bp.get("")
@jwt_required()
def list_users():
    actor_id = get_jwt_identity()
    actor = db.session.get(User, actor_id)

    query = db.session.query(User)

    # Managers see only their department; owners see everyone
    MANAGER_LEVEL = 5
    if actor.role.level < 10:  # not owner
        if actor.department_id:
            query = query.filter_by(department_id=actor.department_id)

    users = query.all()
    return jsonify([
        {
            "id": u.id,
            "username": u.username,
            "role": u.role.name,
            "department": u.department.name if u.department else None,
            "is_active": u.is_active,
            "pin_set": u.pin_set,
        }
        for u in users
    ]), 200


@users_bp.post("/<user_id>/activate")
@jwt_required()
def activate_user(user_id):
    actor_id = get_jwt_identity()
    actor = db.session.get(User, actor_id)
    target = db.session.get(User, user_id)

    if not target:
        return jsonify({"error": "User not found."}), 404

    if actor.role.level <= target.role.level:
        return jsonify({"error": "Insufficient authority."}), 403

    with db.session.begin_nested():
        target.is_active = True

    db.session.commit()
    AuditLog.log(actor=actor.username, action="user.activate", target=target.username)
    db.session.commit()

    return jsonify({"message": f"{target.username} activated."}), 200
