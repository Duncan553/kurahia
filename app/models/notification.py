"""
Notification — every alert, reminder, and suggestion ping lives here.
recipient_user_id: FK to users.id (covers employees + owner — everyone is a User).
channel: set at delivery time (dispatcher decides IN_APP vs WhatsApp vs SMS).
status: QUEUED (waiting) → DELIVERED (sent) → READ (acknowledged) | FAILED (all paths down).
scheduled_for_utc: when the dispatcher should send it (alert cascade uses offsets from event start).

NotificationChannelConfig: owner-togglable per-channel allow-list.
  Disabling WHATSAPP here pauses all WhatsApp sends without breaking anything else.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class NotificationChannel(str, enum.Enum):
    IN_APP               = "IN_APP"
    WHATSAPP             = "WHATSAPP"
    SMS                  = "SMS"
    WHATSAPP_FALLBACK_SMS = "WHATSAPP_FALLBACK_SMS"


class NotificationReferenceType(str, enum.Enum):
    EVENT_ALERT      = "EVENT_ALERT"
    ASSIGNMENT       = "ASSIGNMENT"
    SUGGESTION_OWNER = "SUGGESTION_OWNER"
    GENERAL          = "GENERAL"


class NotificationStatus(str, enum.Enum):
    QUEUED    = "QUEUED"
    DELIVERED = "DELIVERED"
    FAILED    = "FAILED"
    READ      = "READ"


class Notification(db.Model):
    __tablename__ = "notifications"

    id                  = db.Column(db.String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    recipient_user_id   = db.Column(db.String(36), db.ForeignKey("users.id"),
                                    nullable=False, index=True)
    channel             = db.Column(db.String(25), nullable=True)    # set at delivery
    reference_type      = db.Column(db.String(25), nullable=False)
    reference_id        = db.Column(db.String(36), nullable=True)    # event.id, suggestion.id, etc.
    subject             = db.Column(db.String(200), nullable=False)
    body                = db.Column(db.Text, nullable=False)
    status              = db.Column(db.String(10), nullable=False,
                                    default=NotificationStatus.QUEUED.value)
    scheduled_for_utc   = db.Column(db.DateTime(timezone=True), nullable=False)
    sent_at_utc         = db.Column(db.DateTime(timezone=True), nullable=True)
    read_at_utc         = db.Column(db.DateTime(timezone=True), nullable=True)
    notes               = db.Column(db.Text, nullable=True)   # failure reason, override notes
    idempotency_key     = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    recipient = db.relationship("User", foreign_keys=[recipient_user_id], lazy="select")

    def __repr__(self):
        return f"<Notification {self.reference_type} {self.status} user={self.recipient_user_id}>"


class NotificationChannelConfig(db.Model):
    """Owner-configurable allow-list. One row per channel. Disable a channel here to pause it."""
    __tablename__ = "notification_channel_configs"

    id           = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_name = db.Column(db.String(25), nullable=False, unique=True)
    is_active    = db.Column(db.Boolean,    nullable=False, default=True)
    notes        = db.Column(db.Text, nullable=True)

    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<NotificationChannelConfig {self.channel_name} active={self.is_active}>"
