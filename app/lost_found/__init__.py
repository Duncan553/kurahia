"""
lost_found/ — Lost & Found item tracking.

Endpoints:
  GET   /lost-found        — list all items (manager+ level 5)
  POST  /lost-found        — log a found item (any staff level 1+)
  PATCH /lost-found/:id    — update item (mark claimed/disposed, edit notes)
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.lost_found import LostFound, LostFoundStatus
from app.models.audit_log import AuditLog

lost_found_bp = Blueprint("lost_found", __name__, url_prefix="/lost-found")

MANAGER_LEVEL = 5
STAFF_LEVEL   = 1


def _item_dict(item: LostFound) -> dict:
    """Serialise a LostFound row for JSON response."""
    return {
        "id":              item.id,
        "description":     item.description,
        "found_location":  item.found_location,
        "found_by_id":     item.found_by_id,
        "found_by_name":   item.found_by.username if item.found_by else None,
        "found_at":        item.found_at.isoformat() if item.found_at else None,
        "status":          item.status,
        "claimed_by_name": item.claimed_by_name,
        "claimed_at":      item.claimed_at.isoformat() if item.claimed_at else None,
        "notes":           item.notes,
        "is_active":       item.is_active,
    }


# ── GET /lost-found — list all (manager+) ───────────────────────────────────

@lost_found_bp.get("")
@require_active_user
def list_lost_found():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    # Optional filter by status
    status_filter = request.args.get("status")
    query = db.session.query(LostFound).filter_by(is_active=True)
    if status_filter and status_filter in LostFoundStatus.__members__:
        query = query.filter_by(status=status_filter)

    items = query.order_by(LostFound.found_at.desc()).all()
    return jsonify([_item_dict(i) for i in items]), 200


# ── POST /lost-found — log found item (any staff) ───────────────────────────

@lost_found_bp.post("")
@require_active_user
def log_found_item():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Staff login required."}), 403

    data = request.get_json(silent=True) or {}
    description    = (data.get("description") or "").strip()
    found_location = (data.get("found_location") or "").strip()

    if not description or not found_location:
        return jsonify({"error": "description and found_location are required."}), 400

    item = LostFound(
        description=description,
        found_location=found_location,
        found_by_id=actor.id,
        notes=data.get("notes"),
    )
    db.session.add(item)
    db.session.flush()

    AuditLog.log(
        actor=actor.username,
        action="lost_found.create",
        target=item.id,
        details=description[:100],
    )
    db.session.commit()
    return jsonify(_item_dict(item)), 201


# ── PATCH /lost-found/:id — update (mark claimed/disposed, edit) ────────────

@lost_found_bp.patch("/<item_id>")
@require_active_user
def update_lost_found(item_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    item = db.session.get(LostFound, item_id)
    if not item or not item.is_active:
        return jsonify({"error": "Lost & found item not found."}), 404

    data = request.get_json(silent=True) or {}

    # Status transition
    if "status" in data:
        new_status = data["status"]
        if new_status not in LostFoundStatus.__members__:
            return jsonify({"error": f"status must be one of {list(LostFoundStatus.__members__)}."}), 400
        # If marking as CLAIMED, require claimed_by_name
        if new_status == LostFoundStatus.CLAIMED.value:
            claimed_by = (data.get("claimed_by_name") or "").strip()
            if not claimed_by:
                return jsonify({"error": "claimed_by_name is required when marking as CLAIMED."}), 400
            item.claimed_by_name = claimed_by
            item.claimed_at = datetime.now(timezone.utc)
        item.status = new_status

    # Free-form updates
    if "notes" in data:
        item.notes = data["notes"]
    if "description" in data:
        item.description = data["description"].strip()
    if "found_location" in data:
        item.found_location = data["found_location"].strip()

    db.session.flush()
    AuditLog.log(
        actor=actor.username,
        action="lost_found.update",
        target=item_id,
        details=f"status={item.status}",
    )
    db.session.commit()
    return jsonify(_item_dict(item)), 200
