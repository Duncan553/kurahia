"""
admin/roles.py — Full CRUD for roles. Owner only.
GET    /admin/roles
POST   /admin/roles
PATCH  /admin/roles/:id
POST   /admin/roles/:id/disable
POST   /admin/roles/:id/enable

Disabling a role does NOT affect existing users assigned to it — they keep
their role and history intact. It only prevents new users from being assigned it.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.role import Role
from app.models.user import User
from app.models.audit_log import AuditLog

roles_bp = Blueprint("admin_roles", __name__, url_prefix="/admin/roles")

OWNER_LEVEL = 10


def _require_owner(actor):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can manage roles."}), 403
    return None


@roles_bp.get("")
@jwt_required()
def list_roles():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < 5:
        return jsonify({"error": "Manager or above required."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    query = db.session.query(Role)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    return jsonify([
        {"id": r.id, "name": r.name, "level": r.level, "is_active": r.is_active}
        for r in query.all()
    ]), 200


@roles_bp.post("")
@jwt_required()
def create_role():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    data = request.get_json(silent=True) or {}
    name  = (data.get("name") or "").strip()
    level = data.get("level")
    if not name or level is None:
        return jsonify({"error": "name and level are required."}), 400
    try:
        level = int(level)
    except (TypeError, ValueError):
        return jsonify({"error": "level must be a positive integer."}), 400
    if level <= 0:
        return jsonify({"error": "Role level must be greater than zero."}), 400
    if db.session.query(Role).filter_by(name=name).first():
        return jsonify({"error": f"A role named '{name}' already exists."}), 409
    with db.session.begin_nested():
        role = Role(name=name, level=level)
        db.session.add(role)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.role.create", target=name)
    db.session.commit()
    return jsonify({"id": role.id, "name": role.name, "level": role.level}), 201


@roles_bp.patch("/<role_id>")
@jwt_required()
def edit_role(role_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404
    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        if "name" in data:
            role.name = data["name"].strip()
        if "level" in data:
            try:
                role.level = int(data["level"])
            except (TypeError, ValueError):
                return jsonify({"error": "level must be a positive integer."}), 400
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.role.edit", target=role.name)
    db.session.commit()
    return jsonify({"id": role.id, "name": role.name, "level": role.level}), 200


@roles_bp.post("/<role_id>/disable")
@jwt_required()
def disable_role(role_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404
    with db.session.begin_nested():
        role.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.role.disable", target=role.name)
    db.session.commit()
    return jsonify({"id": role.id, "is_active": False}), 200


@roles_bp.post("/<role_id>/enable")
@jwt_required()
def enable_role(role_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404
    with db.session.begin_nested():
        role.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.role.enable", target=role.name)
    db.session.commit()
    return jsonify({"id": role.id, "is_active": True}), 200
