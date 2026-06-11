"""
webpush.py — Web Push delivery socket (dormant pattern, like WhatsApp/SMS).

Dormant until VAPID env vars are set:
  VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIM_EMAIL

Generate keys once:  vapid --gen   (from py-vapid, installed with pywebpush)
Unconfigured → every send returns ("UNCONFIGURED", ...) and inbox delivery
is completely unaffected. Push is supplementary, never the primary channel.
"""
import os
import json


def webpush_configured() -> bool:
    return bool(os.environ.get("VAPID_PRIVATE_KEY") and os.environ.get("VAPID_PUBLIC_KEY"))


def webpush_status() -> dict:
    if webpush_configured():
        return {"configured": True, "message": "Web Push is active."}
    return {"configured": False,
            "message": "Web Push is dormant. Set VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY "
                       "and VAPID_CLAIM_EMAIL to activate."}


def send_webpush(subscription, title: str, body: str, reference_type: str) -> tuple[str, str]:
    """
    Send one push to one PushSubscription row.
    Returns (status, message): SENT | UNCONFIGURED | GONE | FAILED.
    GONE means the browser revoked the subscription — caller should deactivate it.
    """
    if not webpush_configured():
        return "UNCONFIGURED", "VAPID keys not set"

    from pywebpush import webpush, WebPushException

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body, "reference_type": reference_type}),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": f"mailto:{os.environ.get('VAPID_CLAIM_EMAIL', 'admin@kurahia.local')}"},
        )
        return "SENT", "ok"
    except WebPushException as e:
        # 404/410 = endpoint dead (browser unsubscribed / cleared data)
        if e.response is not None and e.response.status_code in (404, 410):
            return "GONE", f"endpoint gone ({e.response.status_code})"
        return "FAILED", str(e)
    except Exception as e:  # noqa: BLE001 — push must never break delivery
        return "FAILED", str(e)


def push_to_user(user_id: str, title: str, body: str, reference_type: str) -> int:
    """
    Best-effort push to all of a user's active subscriptions.
    Deactivates dead endpoints. Returns count sent. NEVER raises.
    """
    if not webpush_configured():
        return 0

    from app.extensions import db
    from app.models.push_subscription import PushSubscription

    sent = 0
    subs = db.session.query(PushSubscription).filter_by(user_id=user_id, is_active=True).all()
    for sub in subs:
        status, _ = send_webpush(sub, title, body, reference_type)
        if status == "SENT":
            sent += 1
        elif status == "GONE":
            sub.is_active = False  # browser revoked it — disable, never delete
    return sent
