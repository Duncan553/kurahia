"""
hr/leave.py — Leave request lifecycle.
Employee creates; manager+ approves/rejects (not their own).
Approved leave makes an absence "with-notice" in attendance reports.
"""
import uuid
from datetime import datetime, timezone, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.leave_request import LeaveRequest, LeaveType, LeaveStatus
from app.models.audit_log import AuditLog

leave_bp = Blueprint("hr_leave", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


@leave_bp.post("/leave-requests")
@require_active_user
def create_leave_request():
    actor   = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id, is_active=True).first()
    if not profile:
        return jsonify({"error": "No employee profile found. Ask your manager to create one."}), 403

    data     = request.get_json(silent=True) or {}
    ltype    = (data.get("leave_type") or "").upper()
    start_s  = data.get("start_date")
    end_s    = data.get("end_date")
    reason   = (data.get("reason") or "").strip() or None
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    if ltype not in LeaveType.__members__:
        return jsonify({"error": f"leave_type must be one of {list(LeaveType.__members__)}."}), 400
    if not start_s or not end_s:
        return jsonify({"error": "start_date and end_date are required (YYYY-MM-DD)."}), 400
    try:
        start_date = date.fromisoformat(start_s)
        end_date   = date.fromisoformat(end_s)
    except ValueError:
        return jsonify({"error": "Dates must be YYYY-MM-DD."}), 400
    if end_date < start_date:
        return jsonify({"error": "end_date must be on or after start_date."}), 400

    existing = db.session.query(LeaveRequest).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    lr = LeaveRequest(
        employee_id=profile.id,
        leave_type=ltype,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        idempotency_key=idem_key,
    )
    db.session.add(lr)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.leave.create",
                 details=f"{ltype} {start_date}–{end_date}")
    db.session.commit()
    return jsonify({"id": lr.id, "status": lr.status, "leave_type": ltype}), 201


@leave_bp.post("/leave-requests/<lr_id>/approve")
@require_active_user
def approve_leave(lr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to approve leave."}), 403

    lr = db.session.get(LeaveRequest, lr_id)
    if not lr:
        return jsonify({"error": "Leave request not found."}), 404
    if lr.status != LeaveStatus.PENDING.value:
        return jsonify({"error": f"This leave request is already {lr.status}."}), 400

    # Prevent self-approval
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
    if profile and profile.id == lr.employee_id:
        return jsonify({"error": "You cannot approve your own leave request."}), 403

    data = request.get_json(silent=True) or {}
    lr.status          = LeaveStatus.APPROVED.value
    lr.reviewed_by_id  = actor.id
    lr.reviewed_at_utc = datetime.now(timezone.utc)
    lr.notes           = data.get("notes")
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.leave.approve", target=lr_id)
    db.session.commit()
    return jsonify({"id": lr.id, "status": lr.status}), 200


@leave_bp.post("/leave-requests/<lr_id>/reject")
@require_active_user
def reject_leave(lr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to reject leave."}), 403

    lr = db.session.get(LeaveRequest, lr_id)
    if not lr:
        return jsonify({"error": "Leave request not found."}), 404
    if lr.status != LeaveStatus.PENDING.value:
        return jsonify({"error": f"This leave request is already {lr.status}."}), 400

    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
    if profile and profile.id == lr.employee_id:
        return jsonify({"error": "You cannot reject your own leave request."}), 403

    data = request.get_json(silent=True) or {}
    lr.status          = LeaveStatus.REJECTED.value
    lr.reviewed_by_id  = actor.id
    lr.reviewed_at_utc = datetime.now(timezone.utc)
    lr.notes           = data.get("notes")
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.leave.reject", target=lr_id)
    db.session.commit()
    return jsonify({"id": lr.id, "status": lr.status}), 200


@leave_bp.post("/leave-requests/<lr_id>/cancel")
@require_active_user
def cancel_leave(lr_id):
    actor   = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()

    lr = db.session.get(LeaveRequest, lr_id)
    if not lr:
        return jsonify({"error": "Leave request not found."}), 404

    # Only the employee themselves or a manager can cancel
    is_own = profile and profile.id == lr.employee_id
    if not is_own and actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "You can only cancel your own leave request."}), 403
    if lr.status in (LeaveStatus.CANCELLED.value, LeaveStatus.REJECTED.value):
        return jsonify({"error": f"This leave request is already {lr.status}."}), 400

    lr.status = LeaveStatus.CANCELLED.value
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.leave.cancel", target=lr_id)
    db.session.commit()
    return jsonify({"id": lr.id, "status": lr.status}), 200


@leave_bp.get("/leave-requests")
@require_active_user
def list_leave():
    actor = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()

    if actor.role.level >= MANAGER_LEVEL:
        requests = db.session.query(LeaveRequest).order_by(
            LeaveRequest.created_at_utc.desc()
        ).all()
    elif profile:
        requests = db.session.query(LeaveRequest).filter_by(
            employee_id=profile.id
        ).order_by(LeaveRequest.created_at_utc.desc()).all()
    else:
        return jsonify([]), 200

    return jsonify([{
        "id":         lr.id,
        "employee":   lr.employee.full_name if lr.employee else None,
        "leave_type": lr.leave_type,
        "start_date": lr.start_date.isoformat(),
        "end_date":   lr.end_date.isoformat(),
        "status":     lr.status,
        "reason":     lr.reason,
    } for lr in requests]), 200
