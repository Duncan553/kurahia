"""
PushSubscription — one browser's Web Push endpoint for one user.
A user can hold several (phone + tablet). endpoint is globally unique —
re-subscribing the same browser updates the existing row (idempotent).
Disable, never delete: unsubscribe flips is_active.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id       = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)

    # The three values the browser's PushManager.subscribe() returns
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh   = db.Column(db.Text, nullable=False)
    auth     = db.Column(db.Text, nullable=False)

    is_active      = db.Column(db.Boolean, nullable=False, default=True)
    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", lazy="select")

    def __repr__(self):
        return f"<PushSubscription user={self.user_id} active={self.is_active}>"
