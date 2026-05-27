"""
admin/departments.py — Full CRUD for departments. Owner only.
GET    /admin/departments
POST   /admin/departments
PATCH  /admin/departments/:id
POST   /admin/departments/:id/disable
POST   /admin/departments/:id/enable
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.department import Department
from app.models.user import User
from app.models.audit_log import AuditLog

dept_bp = Blueprint("admin_dept", __name__, url_prefix="/admin/departments")

OWNER_LEVEL = 10


def _require_owner(actor):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can manage departments."}), 403
    return None


@dept_bp.get("")
@jwt_required()
def list_departments():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < 5:
        return jsonify({"error": "Manager or above required."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    query = db.session.query(Department)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    return jsonify([
        {"id": d.id, "name": d.name, "is_active": d.is_active}
        for d in query.all()
    ]), 200


@dept_bp.post("")
@jwt_required()
def create_department():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Department name is required."}), 400
    if db.session.query(Department).filter_by(name=name).first():
        return jsonify({"error": f"A department named '{name}' already exists."}), 409
    with db.session.begin_nested():
        dept = Department(name=name)
        db.session.add(dept)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.dept.create", target=name)
    db.session.commit()
    return jsonify({"id": dept.id, "name": dept.name}), 201


@dept_bp.patch("/<dept_id>")
@jwt_required()
def edit_department(dept_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        if "name" in data:
            dept.name = data["name"].strip()
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.dept.edit", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "name": dept.name}), 200


@dept_bp.post("/<dept_id>/disable")
@jwt_required()
def disable_department(dept_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    with db.session.begin_nested():
        dept.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.dept.disable", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "is_active": False}), 200


@dept_bp.post("/<dept_id>/enable")
@jwt_required()
def enable_department(dept_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    with db.session.begin_nested():
        dept.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.dept.enable", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "is_active": True}), 200
