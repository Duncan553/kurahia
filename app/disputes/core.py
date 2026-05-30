"""
disputes/core.py — Formal dispute lifecycle.

Query-layer confidentiality (is_owner_only=True):
  manager: query adds WHERE is_owner_only=FALSE — owner-only disputes don't exist for them.
  owner:   no filter.
Same pattern as OWNER_PRIVATE suggestions.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.dispute import (
    Dispute, DisputeSubject, DisputeStatus, DisputeCategory,
    DisputePriority, VALID_DISPUTE_TRANSITIONS,
)
from app.models.employee_profile import EmployeeProfile
from app.models.audit_log import AuditLog

disputes_bp = Blueprint("disputes_core", __name__, url_prefix="/disputes")

OWNER_LEVEL   = 10
MANAGER_LEVEL = 5


def _transition(dispute: Dispute, new_status: str) -> tuple[bool, str]:
    allowed = VALID_DISPUTE_TRANSITIONS.get(dispute.status, set())
    if new_status not in allowed:
        return False, (
            f"Cannot move dispute from {dispute.status} to {new_status}. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}."
        )
    return True, ""


def _dispute_dict(d: Dispute) -> dict:
    return {
        "id":         d.id,
        "category":   d.category,
        "status":     d.status,
        "priority":   d.priority,
        "is_owner_only": d.is_owner_only,
        "description":   d.description,
        "reporter":   d.reporter.full_name if d.reporter else None,
        "subjects":   [s.employee.full_name for s in d.subjects.all() if s.employee],
        "assigned_to": d.assigned_to.full_name if d.assigned_to else None,
        "resolution_notes": d.resolution_notes,
        "created_at": d.created_at_utc.isoformat(),
    }


def _get_reporter_profile(actor: User) -> EmployeeProfile | None:
    return db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()


# ── Create ─────────────────────────────────────────────────────────────────────

@disputes_bp.post("")
@require_active_user
def create_dispute():
    actor = db.session.get(User, get_jwt_identity())
    profile = _get_reporter_profile(actor)
    if not profile:
        return jsonify({"error": "Employee profile required to file a dispute."}), 400

    data          = request.get_json(silent=True) or {}
    category      = (data.get("category") or "").upper()
    description   = (data.get("description") or "").strip()
    priority      = (data.get("priority") or DisputePriority.MEDIUM.value).upper()
    is_owner_only = data.get("is_owner_only", False)
    idem          = data.get("idempotency_key") or str(uuid.uuid4())
    subject_ids   = data.get("subject_employee_ids") or []

    if not description:
        return jsonify({"error": "description is required."}), 400
    if category not in DisputeCategory.__members__:
        return jsonify({"error": f"category must be one of {list(DisputeCategory.__members__)}."}), 400
    if priority not in DisputePriority.__members__:
        return jsonify({"error": f"priority must be one of {list(DisputePriority.__members__)}."}), 400

    existing = db.session.query(Dispute).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify({**_dispute_dict(existing), "duplicate": True}), 200

    dispute = Dispute(
        reporter_employee_id=profile.id,
        category=category, description=description,
        priority=priority, is_owner_only=bool(is_owner_only),
        idempotency_key=idem,
    )
    db.session.add(dispute)
    db.session.flush()

    for emp_id in subject_ids:
        subj_profile = db.session.get(EmployeeProfile, emp_id)
        if subj_profile:
            db.session.add(DisputeSubject(dispute_id=dispute.id, employee_id=emp_id))

    db.session.commit()
    AuditLog.log(actor=actor.username, action="dispute.create",
                 target=dispute.id, details=f"category={category}")
    db.session.commit()
    return jsonify(_dispute_dict(dispute)), 201


# ── Lifecycle transitions ──────────────────────────────────────────────────────

def _get_dispute_visible(dispute_id: str, actor: User) -> Dispute | None:
    """Returns dispute only if actor has access (owner_only filter)."""
    dispute = db.session.get(Dispute, dispute_id)
    if not dispute:
        return None
    if dispute.is_owner_only and actor.role.level < OWNER_LEVEL:
        return None   # structural 404
    return dispute


@disputes_bp.post("/<dispute_id>/claim")
@require_active_user
def claim_dispute(dispute_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to claim disputes."}), 403
    dispute = _get_dispute_visible(dispute_id, actor)
    if not dispute:
        return jsonify({"error": "Dispute not found."}), 404
    ok, err = _transition(dispute, DisputeStatus.UNDER_REVIEW.value)
    if not ok:
        return jsonify({"error": err}), 400
    profile = _get_reporter_profile(actor)
    dispute.status = DisputeStatus.UNDER_REVIEW.value
    dispute.assigned_to_employee_id = profile.id if profile else None
    dispute.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="dispute.claim", target=dispute_id)
    db.session.commit()
    return jsonify(_dispute_dict(dispute)), 200


@disputes_bp.post("/<dispute_id>/resolve")
@require_active_user
def resolve_dispute(dispute_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    dispute = _get_dispute_visible(dispute_id, actor)
    if not dispute:
        return jsonify({"error": "Dispute not found."}), 404
    ok, err = _transition(dispute, DisputeStatus.RESOLVED.value)
    if not ok:
        return jsonify({"error": err}), 400
    data = request.get_json(silent=True) or {}
    resolution = (data.get("resolution_notes") or "").strip()
    if not resolution:
        return jsonify({"error": "resolution_notes are required to resolve a dispute."}), 400
    dispute.status = DisputeStatus.RESOLVED.value
    dispute.resolution_notes = resolution
    dispute.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="dispute.resolve", target=dispute_id)
    db.session.commit()
    return jsonify(_dispute_dict(dispute)), 200


@disputes_bp.post("/<dispute_id>/dismiss")
@require_active_user
def dismiss_dispute(dispute_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    dispute = _get_dispute_visible(dispute_id, actor)
    if not dispute:
        return jsonify({"error": "Dispute not found."}), 404
    ok, err = _transition(dispute, DisputeStatus.DISMISSED.value)
    if not ok:
        return jsonify({"error": err}), 400
    data = request.get_json(silent=True) or {}
    dispute.status = DisputeStatus.DISMISSED.value
    dispute.resolution_notes = (data.get("reason") or "Dismissed.").strip()
    dispute.updated_at_utc = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="dispute.dismiss", target=dispute_id)
    db.session.commit()
    return jsonify(_dispute_dict(dispute)), 200


# ── List ──────────────────────────────────────────────────────────────────────

@disputes_bp.get("")
@require_active_user
def list_disputes():
    actor = db.session.get(User, get_jwt_identity())
    q = db.session.query(Dispute)

    if actor.role.level >= OWNER_LEVEL:
        pass  # sees everything
    elif actor.role.level >= MANAGER_LEVEL:
        q = q.filter_by(is_owner_only=False)   # query-layer filter
    else:
        # Employee: only see disputes they filed
        profile = _get_reporter_profile(actor)
        if not profile:
            return jsonify([]), 200
        q = q.filter_by(reporter_employee_id=profile.id)

    status = (request.args.get("status") or "").upper() or None
    if status:
        q = q.filter_by(status=status)

    return jsonify([_dispute_dict(d) for d in
                    q.order_by(Dispute.created_at_utc.desc()).all()]), 200
