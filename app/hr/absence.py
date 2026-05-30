"""
hr/absence.py — Absence and late-notice management.
Employee sends notice for their own upcoming/missed shift.
Manager+ sees all notices for a given date.
"""
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.absence_notice import AbsenceNotice, NoticeType
from app.models.shift import Shift
from app.models.audit_log import AuditLog

absence_bp = Blueprint("hr_absence", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


@absence_bp.post("/absence-notices")
@require_active_user
def create_absence_notice():
    actor   = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id, is_active=True).first()
    if not profile:
        return jsonify({"error": "No employee profile found. Ask your manager to create one."}), 403

    data          = request.get_json(silent=True) or {}
    ntype         = (data.get("notice_type") or "").upper()
    reason        = (data.get("reason") or "").strip() or None
    shift_id      = data.get("expected_shift_id")
    late_minutes  = data.get("expected_late_minutes")
    idem_key      = data.get("idempotency_key") or str(uuid.uuid4())

    if ntype not in NoticeType.__members__:
        return jsonify({"error": f"notice_type must be one of {list(NoticeType.__members__)}."}), 400

    if ntype == NoticeType.LATE.value and late_minutes is not None:
        try:
            late_minutes = int(late_minutes)
        except (ValueError, TypeError):
            return jsonify({"error": "expected_late_minutes must be an integer."}), 400

    # If a shift_id was provided, verify it belongs to this employee
    if shift_id:
        shift = db.session.get(Shift, shift_id)
        if not shift or shift.employee_id != profile.id:
            return jsonify({"error": "Shift not found or does not belong to you."}), 404

    existing = db.session.query(AbsenceNotice).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    notice = AbsenceNotice(
        employee_id=profile.id,
        notice_type=ntype,
        expected_shift_id=shift_id,
        expected_late_minutes=late_minutes,
        reason=reason,
        idempotency_key=idem_key,
    )
    db.session.add(notice)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.absence.create",
                 details=f"type={ntype} shift={shift_id}")
    db.session.commit()
    return jsonify({
        "id":           notice.id,
        "notice_type":  notice.notice_type,
        "sent_at":      notice.sent_at_utc.isoformat(),
    }), 201


@absence_bp.get("/absence-notices")
@require_active_user
def list_absence_notices():
    actor = db.session.get(User, get_jwt_identity())

    date_str    = request.args.get("date")
    employee_id = request.args.get("employee_id")

    # Non-managers can only see their own notices
    if actor.role.level < MANAGER_LEVEL:
        profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
        if not profile:
            return jsonify([]), 200
        employee_id = profile.id

    query = db.session.query(AbsenceNotice)
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400
        query = query.filter(
            AbsenceNotice.sent_at_utc >= d,
            AbsenceNotice.sent_at_utc < d + timedelta(days=1),
        )

    notices = query.order_by(AbsenceNotice.sent_at_utc.desc()).all()
    return jsonify([{
        "id":                    n.id,
        "employee_id":           n.employee_id,
        "employee_name":         n.employee.full_name if n.employee else None,
        "notice_type":           n.notice_type,
        "expected_shift_id":     n.expected_shift_id,
        "expected_late_minutes": n.expected_late_minutes,
        "reason":                n.reason,
        "sent_at":               n.sent_at_utc.isoformat(),
    } for n in notices]), 200
