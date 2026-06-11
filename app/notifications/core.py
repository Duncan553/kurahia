"""
notifications/core.py — Inbox, mark-read, admin view.
GET /notifications/inbox  → current user's unread DELIVERED items
POST /notifications/:id/mark-read
GET /notifications?employee_id=... → admin/manager view
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
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
@require_active_user
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
@require_active_user
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


@notifications_bp.get("/whatsapp/status")
@require_active_user
def whatsapp_status():
    """Diagnostic: is the WhatsApp socket configured? Manager+ only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    from app.services.notifications.whatsapp import configuration_status
    configured, message = configuration_status()
    return jsonify({"configured": configured, "message": message}), 200


@notifications_bp.get("")
@require_active_user
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

# ── Web Push (F-17) ───────────────────────────────────────────────────────────

@notifications_bp.get("/push-config")
@require_active_user
def push_config():
    """Public VAPID key for PushManager.subscribe(), or dormant status."""
    import os
    from app.services.notifications.webpush import webpush_status
    status = webpush_status()
    if status["configured"]:
        status["public_key"] = os.environ["VAPID_PUBLIC_KEY"]
    return jsonify(status), 200


@notifications_bp.post("/push-subscribe")
@require_active_user
def push_subscribe():
    """Store this browser's push subscription. Idempotent on endpoint."""
    from app.models.push_subscription import PushSubscription
    from app.models.audit_log import AuditLog

    actor = db.session.get(User, get_jwt_identity())
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "endpoint and keys (p256dh, auth) are required. "
                                 "Send the object returned by PushManager.subscribe()."}), 400

    # Idempotency: endpoint is globally unique — same browser re-subscribing
    # updates the existing row (it may now belong to a different user on a shared tablet)
    existing = db.session.query(PushSubscription).filter_by(endpoint=endpoint).first()
    with db.session.begin_nested():
        if existing:
            existing.user_id, existing.p256dh, existing.auth = actor.id, p256dh, auth
            existing.is_active = True
            sub = existing
        else:
            sub = PushSubscription(user_id=actor.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
            db.session.add(sub)

    AuditLog.log(actor=actor.username, action="push.subscribe", target=sub.id)
    db.session.commit()
    return jsonify({"id": sub.id, "duplicate": existing is not None}), 200 if existing else 201


@notifications_bp.post("/push-unsubscribe")
@require_active_user
def push_unsubscribe():
    """Deactivate this browser's subscription (disable, never delete)."""
    from app.models.push_subscription import PushSubscription
    from app.models.audit_log import AuditLog

    actor = db.session.get(User, get_jwt_identity())
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    if not endpoint:
        return jsonify({"error": "endpoint is required."}), 400

    sub = db.session.query(PushSubscription).filter_by(endpoint=endpoint).first()
    if not sub:
        return jsonify({"error": "No subscription found for that endpoint."}), 404

    with db.session.begin_nested():
        sub.is_active = False

    AuditLog.log(actor=actor.username, action="push.unsubscribe", target=sub.id)
    db.session.commit()
    return jsonify({"id": sub.id, "is_active": False}), 200
