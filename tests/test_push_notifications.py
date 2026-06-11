"""
test_push_notifications.py — Web Push socket (F-17).

Tests:
  1. push-config dormant when VAPID env unset
  2. push-config returns public key when configured
  3. Subscribe stores subscription + audit log
  4. Subscribe is idempotent on endpoint (re-subscribe updates, no duplicate row)
  5. Subscribe rejects missing keys with plain-English error
  6. Unsubscribe deactivates (is_active=False, row kept)
  7. Unsubscribe unknown endpoint → 404 plain-English
  8. Dispatcher: dormant push never breaks inbox delivery
  9. Auth required on all push endpoints
"""
from unittest.mock import patch
from app.extensions import db as _db


def auth(token):
    return {"Authorization": f"Bearer {token}"}


SUB_BODY = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-1",
    "keys": {"p256dh": "test-p256dh-key", "auth": "test-auth-secret"},
}

VAPID_ENV = {
    "VAPID_PRIVATE_KEY": "test-private",
    "VAPID_PUBLIC_KEY": "test-public",
    "VAPID_CLAIM_EMAIL": "owner@kurahia.test",
}

UNSET_ENV = {"VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": "", "VAPID_CLAIM_EMAIL": ""}


# ── 1+2. push-config ──────────────────────────────────────────────────────────

def test_push_config_dormant_when_unset(client, manager_token):
    with patch.dict("os.environ", UNSET_ENV, clear=False):
        rv = client.get("/notifications/push-config", headers=auth(manager_token))
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["configured"] is False
    assert "dormant" in data["message"].lower()
    assert "public_key" not in data


def test_push_config_returns_public_key_when_set(client, manager_token):
    with patch.dict("os.environ", VAPID_ENV, clear=False):
        rv = client.get("/notifications/push-config", headers=auth(manager_token))
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["configured"] is True
    assert data["public_key"] == "test-public"


# ── 3. Subscribe stores + audits ──────────────────────────────────────────────

def test_push_subscribe_stores_subscription(client, manager_token):
    rv = client.post("/notifications/push-subscribe", json=SUB_BODY, headers=auth(manager_token))
    assert rv.status_code == 201
    sub_id = rv.get_json()["id"]

    from app.models.push_subscription import PushSubscription
    from app.models.audit_log import AuditLog
    sub = _db.session.get(PushSubscription, sub_id)
    assert sub.endpoint == SUB_BODY["endpoint"]
    assert sub.is_active is True

    log = _db.session.query(AuditLog).filter_by(action="push.subscribe", target=sub_id).first()
    assert log is not None


# ── 4. Idempotent on endpoint ────────────────────────────────────────────────

def test_push_subscribe_idempotent_on_endpoint(client, manager_token):
    rv1 = client.post("/notifications/push-subscribe", json=SUB_BODY, headers=auth(manager_token))
    rv2 = client.post("/notifications/push-subscribe", json=SUB_BODY, headers=auth(manager_token))
    assert rv1.status_code == 201
    assert rv2.status_code == 200
    assert rv2.get_json()["duplicate"] is True
    assert rv1.get_json()["id"] == rv2.get_json()["id"]

    from app.models.push_subscription import PushSubscription
    count = _db.session.query(PushSubscription).filter_by(endpoint=SUB_BODY["endpoint"]).count()
    assert count == 1


# ── 5. Missing keys rejected ─────────────────────────────────────────────────

def test_push_subscribe_rejects_missing_keys(client, manager_token):
    rv = client.post("/notifications/push-subscribe",
                     json={"endpoint": "https://x.test/e"}, headers=auth(manager_token))
    assert rv.status_code == 400
    assert "required" in rv.get_json()["error"].lower()


# ── 6+7. Unsubscribe ─────────────────────────────────────────────────────────

def test_push_unsubscribe_deactivates_not_deletes(client, manager_token):
    client.post("/notifications/push-subscribe", json=SUB_BODY, headers=auth(manager_token))
    rv = client.post("/notifications/push-unsubscribe",
                     json={"endpoint": SUB_BODY["endpoint"]}, headers=auth(manager_token))
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is False

    from app.models.push_subscription import PushSubscription
    sub = _db.session.query(PushSubscription).filter_by(endpoint=SUB_BODY["endpoint"]).first()
    assert sub is not None          # row kept — disable, never delete
    assert sub.is_active is False


def test_push_unsubscribe_unknown_endpoint_404(client, manager_token):
    rv = client.post("/notifications/push-unsubscribe",
                     json={"endpoint": "https://never.seen/e"}, headers=auth(manager_token))
    assert rv.status_code == 404
    assert "no subscription" in rv.get_json()["error"].lower()


# ── 8. Dispatcher unaffected when dormant ────────────────────────────────────

def test_dispatcher_inbox_delivery_unaffected_by_dormant_push(client, app, manager_token, manager_profile, wifi_allowed):
    """Push unconfigured + user has a subscription → in-app delivery still works."""
    import uuid
    from datetime import datetime, timezone
    from app.models.notification import Notification, NotificationStatus
    from app.models.user import User
    from app.services.notifications.dispatcher import deliver_notification

    # Manager clocks in → "present" → IN_APP path
    client.post("/hr/clock-in", headers=auth(manager_token))

    manager = _db.session.query(User).filter_by(username="manager1").first()
    notif = Notification(
        recipient_user_id=manager.id,
        reference_type="leave_request",
        reference_id=str(uuid.uuid4()),
        subject="Test push fallback",
        body="Body",
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    )
    _db.session.add(notif)
    _db.session.commit()

    with patch.dict("os.environ", UNSET_ENV, clear=False):
        final = deliver_notification(notif)

    assert final == NotificationStatus.DELIVERED.value
    assert notif.channel == "IN_APP"


# ── 9. Auth required ─────────────────────────────────────────────────────────

def test_push_endpoints_require_auth(client):
    assert client.get("/notifications/push-config").status_code == 401
    assert client.post("/notifications/push-subscribe", json=SUB_BODY).status_code == 401
    assert client.post("/notifications/push-unsubscribe", json={"endpoint": "x"}).status_code == 401
