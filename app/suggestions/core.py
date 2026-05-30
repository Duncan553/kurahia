"""
suggestions/core.py — Two-tier confidential feedback.

QUERY-LAYER AUTHORIZATION:
  manager: only sees MANAGEMENT suggestions (query WHERE category='MANAGEMENT')
  owner:   sees everything (no filter)

OWNER_PRIVATE suggestions are structurally invisible to managers — they don't
appear in lists AND a direct GET by ID returns 404. Not "hidden in a list" —
they don't exist for that session.

Anonymous OWNER_PRIVATE is allowed. MANAGEMENT suggestions require attribution.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.suggestion import Suggestion, SuggestionCategory, SuggestionStatus
from app.models.notification import (
    Notification, NotificationStatus, NotificationReferenceType,
)
from app.models.audit_log import AuditLog

suggestions_bp = Blueprint("suggestions_core", __name__, url_prefix="/suggestions")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


def _suggestion_dict(s: Suggestion) -> dict:
    return {
        "id":              s.id,
        "category":        s.category,
        "subject":         s.subject,
        "body":            s.body,
        "status":          s.status,
        "submitted_by":    s.submitted_by_name or "anonymous",
        "reviewed_by":     s.reviewed_by.username if s.reviewed_by else None,
        "reviewed_at":     s.reviewed_at_utc.isoformat() if s.reviewed_at_utc else None,
        "response":        s.response_to_submitter,
        "created_at":      s.created_at_utc.isoformat(),
    }


@suggestions_bp.post("")
@require_active_user
def submit_suggestion():
    actor = db.session.get(User, get_jwt_identity())
    data  = request.get_json(silent=True) or {}

    category = (data.get("category") or "").upper()
    subject  = (data.get("subject") or "").strip()
    body     = (data.get("body") or "").strip()
    idem     = data.get("idempotency_key") or str(uuid.uuid4())

    if category not in SuggestionCategory.__members__:
        return jsonify({"error": f"category must be one of {list(SuggestionCategory.__members__)}."}), 400
    if not subject or not body:
        return jsonify({"error": "subject and body are required."}), 400

    # Anonymous only allowed for OWNER_PRIVATE
    anonymous = data.get("anonymous", False)
    if anonymous and category != SuggestionCategory.OWNER_PRIVATE.value:
        return jsonify({"error": "Anonymous submission is only allowed for OWNER_PRIVATE suggestions."}), 400

    existing = db.session.query(Suggestion).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify({**_suggestion_dict(existing), "duplicate": True}), 200

    suggestion = Suggestion(
        submitted_by_user_id=None if anonymous else actor.id,
        submitted_by_name="anonymous" if anonymous else actor.username,
        category=category,
        subject=subject,
        body=body,
        idempotency_key=idem,
    )
    db.session.add(suggestion)
    db.session.flush()

    # OWNER_PRIVATE → notify the owner immediately
    if category == SuggestionCategory.OWNER_PRIVATE.value:
        _notify_owner(suggestion)

    db.session.commit()
    AuditLog.log(actor=actor.username, action="suggestion.submit",
                 details=f"category={category}")
    db.session.commit()
    return jsonify(_suggestion_dict(suggestion)), 201


def _notify_owner(suggestion: Suggestion):
    """Create a QUEUED Notification to all owner-level users."""
    now = datetime.now(timezone.utc)
    owners = db.session.query(User).join(User.role).filter(
        User.role.has(level=OWNER_LEVEL)
    ).all()
    for owner in owners:
        idem = f"sugg-owner-{suggestion.id}-{owner.id}"
        if db.session.query(Notification).filter_by(idempotency_key=idem).first():
            continue
        notif = Notification(
            recipient_user_id=owner.id,
            reference_type=NotificationReferenceType.SUGGESTION_OWNER.value,
            reference_id=suggestion.id,
            subject=f"[Private suggestion] {suggestion.subject}",
            body=f"A new private suggestion was submitted: {suggestion.body[:200]}",
            status=NotificationStatus.QUEUED.value,
            scheduled_for_utc=now,
            idempotency_key=idem,
        )
        db.session.add(notif)
    db.session.flush()


@suggestions_bp.get("")
@require_active_user
def list_suggestions():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    q = db.session.query(Suggestion)

    # QUERY-LAYER FILTER: managers only see MANAGEMENT; owners see both
    if actor.role.level < OWNER_LEVEL:
        q = q.filter_by(category=SuggestionCategory.MANAGEMENT.value)

    status = (request.args.get("status") or "").upper() or None
    if status:
        q = q.filter_by(status=status)

    return jsonify([_suggestion_dict(s) for s in
                    q.order_by(Suggestion.created_at_utc.desc()).all()]), 200


@suggestions_bp.get("/<suggestion_id>")
@require_active_user
def get_suggestion(suggestion_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    suggestion = db.session.get(Suggestion, suggestion_id)
    if not suggestion:
        return jsonify({"error": "Suggestion not found."}), 404

    # Structural 404 for managers trying to access OWNER_PRIVATE
    if (suggestion.category == SuggestionCategory.OWNER_PRIVATE.value
            and actor.role.level < OWNER_LEVEL):
        return jsonify({"error": "Suggestion not found."}), 404

    return jsonify(_suggestion_dict(suggestion)), 200


@suggestions_bp.post("/<suggestion_id>/review")
@require_active_user
def review_suggestion(suggestion_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    suggestion = db.session.get(Suggestion, suggestion_id)
    if not suggestion:
        return jsonify({"error": "Suggestion not found."}), 404

    # Structural 404 for managers trying to review OWNER_PRIVATE
    if (suggestion.category == SuggestionCategory.OWNER_PRIVATE.value
            and actor.role.level < OWNER_LEVEL):
        return jsonify({"error": "Suggestion not found."}), 404

    data   = request.get_json(silent=True) or {}
    status = (data.get("status") or "").upper()
    if status not in SuggestionStatus.__members__:
        return jsonify({"error": f"status must be one of {list(SuggestionStatus.__members__)}."}), 400

    suggestion.status               = status
    suggestion.reviewed_by_id       = actor.id
    suggestion.reviewed_at_utc      = datetime.now(timezone.utc)
    suggestion.response_to_submitter = data.get("response")
    db.session.commit()
    AuditLog.log(actor=actor.username, action="suggestion.review",
                 target=suggestion_id, details=f"status={status}")
    db.session.commit()
    return jsonify(_suggestion_dict(suggestion)), 200
