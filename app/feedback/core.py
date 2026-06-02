"""
feedback/core.py — Guest feedback recording and aggregation.
POST /feedback          — front desk records a rating (1-5).
GET  /feedback          — aggregate: avg score, count, recent comments.
GET  /feedback/staff/:id — per-staff: avg, count, recent comments.
served_by_employee_id feeds the performance guest_rating component (Chunk 5 socket).
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from sqlalchemy import func
from app.extensions import db
from app.models.user import User
from app.models.guest_feedback import GuestFeedback
from app.models.employee_profile import EmployeeProfile
from app.models.audit_log import AuditLog

feedback_bp = Blueprint("feedback_core", __name__, url_prefix="/feedback")

STAFF_LEVEL   = 1
MANAGER_LEVEL = 5


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.strptime(val, "%Y-%m-%d")
        return dt
    except ValueError:
        return None


# ── Create ─────────────────────────────────────────────────────────────────────

@feedback_bp.post("")
@require_active_user
def create_feedback():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required to record feedback."}), 403

    data       = request.get_json(silent=True) or {}
    guest_name = (data.get("guest_name") or "anonymous").strip()
    score      = data.get("score")
    idem       = data.get("idempotency_key") or str(uuid.uuid4())

    try:
        score = int(score)
        if score < 1 or score > 5:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "score must be an integer between 1 and 5."}), 400

    existing = db.session.query(GuestFeedback).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    fb = GuestFeedback(
        guest_name=guest_name,
        guest_phone=data.get("guest_phone"),
        score=score,
        comments=data.get("comments"),
        booking_id=data.get("booking_id"),
        event_id=data.get("event_id"),
        department_id=data.get("department_id"),
        served_by_employee_id=data.get("served_by_employee_id"),
        idempotency_key=idem,
    )
    db.session.add(fb)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="feedback.create",
                 details=f"score={score} dept={data.get('department_id')}")
    db.session.commit()
    return jsonify({
        "id": fb.id, "score": fb.score, "guest_name": fb.guest_name,
        "created_at": fb.created_at_utc.isoformat(),
    }), 201


# ── Aggregate list ─────────────────────────────────────────────────────────────

@feedback_bp.get("")
@require_active_user
def list_feedback():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    dept_id  = request.args.get("department_id")
    from_dt  = _parse_dt(request.args.get("from"))
    to_dt    = _parse_dt(request.args.get("to"))

    q = db.session.query(GuestFeedback)
    if dept_id:
        q = q.filter_by(department_id=dept_id)
    if from_dt:
        q = q.filter(GuestFeedback.created_at_utc >= from_dt)
    if to_dt:
        q = q.filter(GuestFeedback.created_at_utc < to_dt + timedelta(days=1))

    items = q.order_by(GuestFeedback.created_at_utc.desc()).all()
    avg = None
    if items:
        total = sum(f.score for f in items)
        avg = str(round(Decimal(str(total)) / Decimal(str(len(items))), 2))

    return jsonify({
        "count": len(items),
        "average_score": avg,
        "recent": [{
            "id": f.id, "score": f.score, "guest_name": f.guest_name,
            "comments": f.comments,
            "created_at": f.created_at_utc.isoformat(),
        } for f in items[:20]],
    }), 200


# ── Per-staff ──────────────────────────────────────────────────────────────────

@feedback_bp.get("/staff/<employee_id>")
@require_active_user
def staff_feedback(employee_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    from_dt = _parse_dt(request.args.get("from"))
    to_dt   = _parse_dt(request.args.get("to"))

    q = db.session.query(GuestFeedback).filter_by(served_by_employee_id=employee_id)
    if from_dt:
        q = q.filter(GuestFeedback.created_at_utc >= from_dt)
    if to_dt:
        q = q.filter(GuestFeedback.created_at_utc < to_dt + timedelta(days=1))

    items = q.order_by(GuestFeedback.created_at_utc.desc()).all()
    avg = None
    if items:
        total = sum(f.score for f in items)
        avg = str(round(Decimal(str(total)) / Decimal(str(len(items))), 2))

    profile = db.session.get(EmployeeProfile, employee_id)
    return jsonify({
        "employee_id":   employee_id,
        "employee_name": profile.full_name if profile else None,
        "count":         len(items),
        "average_score": avg,
        "recent_comments": [f.comments for f in items[:10] if f.comments],
    }), 200
