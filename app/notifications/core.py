"""
notifications/core.py — Inbox, mark-read, admin view.
GET /notifications/inbox  → current user's unread DELIVERED items
POST /notifications/:id/mark-read
GET /notifications?employee_id=... → admin/manager view
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.notification import Notification, NotificationStatus

notifications_bp = Blueprint("notifications_core", __name__, url_prefix="/notifications")

MANAGER_LEVEL = 5


def _notif_dict(n: Notification) -> dict:
    return {
        "id":             n.id,
        "reference_type": n.reference_type,
        "reference_id":   n.reference_id,
        "subject":        n.subject,
        "body":           n.body,
        "status":         n.status,
        "channel":        n.channel,
        "scheduled_for":  n.scheduled_for_utc.isoformat() if n.scheduled_for_utc else None,
        "sent_at":        n.sent_at_utc.isoformat() if n.sent_at_utc else None,
        "read_at":        n.read_at_utc.isoformat() if n.read_at_utc else None,
    }


@notifications_bp.get("/inbox")
@jwt_required()
def inbox():
    """Current user's unread delivered in-app notifications."""
    user_id = get_jwt_identity()
    items = db.session.query(Notification).filter_by(
        recipient_user_id=user_id,
        status=NotificationStatus.DELIVERED.value,
    ).filter(
        Notification.read_at_utc.is_(None)
    ).order_by(Notification.sent_at_utc.desc()).all()
    return jsonify([_notif_dict(n) for n in items]), 200


@notifications_bp.post("/<notif_id>/mark-read")
@jwt_required()
def mark_read(notif_id):
    user_id = get_jwt_identity()
    notif = db.session.get(Notification, notif_id)
    if not notif:
        return jsonify({"error": "Notification not found."}), 404
    if notif.recipient_user_id != user_id:
        return jsonify({"error": "You can only mark your own notifications as read."}), 403
    if notif.read_at_utc:
        return jsonify(_notif_dict(notif)), 200   # idempotent
    notif.read_at_utc = datetime.now(timezone.utc)
    notif.status = NotificationStatus.READ.value
    db.session.commit()
    return jsonify(_notif_dict(notif)), 200


@notifications_bp.get("")
@jwt_required()
def list_notifications():
    """Admin/manager view — filterable by recipient user_id."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    user_id = request.args.get("user_id") or request.args.get("employee_id")
    q = db.session.query(Notification)
    if user_id:
        q = q.filter_by(recipient_user_id=user_id)
    items = q.order_by(Notification.scheduled_for_utc.desc()).limit(100).all()
    return jsonify([_notif_dict(n) for n in items]), 200
