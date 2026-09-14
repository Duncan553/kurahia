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
from app.utils.auth_decorators import require_active_user
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
@require_active_user
def list_departments():
    """Reading the list of departments is not an admin act.

    This was manager-only, and the cost was a silent lie rather than a refusal.
    The chef's own inventory screen calls it to turn a department_id into a
    name, gets 403, and falls back to `?? "Other"` — so a head chef looking at
    her own kitchen stock saw the group labelled "Other". No error, no empty
    state, just a mildly wrong word, which is the hardest kind of wrong to
    notice.

    Department NAMES are not sensitive — they are printed on the nav bar of
    every station tablet. Creating, renaming and disabling them stays with the
    owner (_require_owner, below); only this read is opened, and only to
    somebody already signed in and active.
    """
    actor = db.session.get(User, get_jwt_identity())
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    # Disabled departments are administrative history, not floor information.
    if include_disabled and actor.role.level < 5:
        return jsonify({"error": "Manager or above required to list disabled "
                                 "departments."}), 403
    query = db.session.query(Department)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    return jsonify([
        {"id": d.id, "name": d.name, "is_active": d.is_active}
        for d in query.all()
    ]), 200


@dept_bp.post("")
@require_active_user
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
    AuditLog.log(actor=actor.username, action="admin.dept.create", target=name)
    db.session.commit()
    return jsonify({"id": dept.id, "name": dept.name}), 201


@dept_bp.patch("/<dept_id>")
@require_active_user
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
    AuditLog.log(actor=actor.username, action="admin.dept.edit", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "name": dept.name}), 200


@dept_bp.post("/<dept_id>/disable")
@require_active_user
def disable_department(dept_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    with db.session.begin_nested():
        dept.is_active = False
    AuditLog.log(actor=actor.username, action="admin.dept.disable", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "is_active": False}), 200


@dept_bp.post("/<dept_id>/enable")
@require_active_user
def enable_department(dept_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    with db.session.begin_nested():
        dept.is_active = True
    AuditLog.log(actor=actor.username, action="admin.dept.enable", target=dept.name)
    db.session.commit()
    return jsonify({"id": dept.id, "is_active": True}), 200
