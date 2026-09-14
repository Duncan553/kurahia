"""
The owner's channel allow-list, and both paths that must obey it.

NotificationChannelConfig is invariant-10 configuration: one row per channel,
is_active flips it. Two things were wrong. _channel_active treated a MISSING
row as disabled, so a channel nobody had configured was silently off — harmless
while the sockets are dormant, and a silent failure the day SMS goes live. And
guest_notify called the WhatsApp socket directly, ignoring the switch entirely.
"""
from app.extensions import db
from app.models.notification import NotificationChannelConfig, NotificationChannel
from app.services.notifications.dispatcher import _channel_active


def _set(channel, active):
    row = db.session.query(NotificationChannelConfig).filter_by(channel_name=channel).first()
    if not row:
        row = NotificationChannelConfig(channel_name=channel)
        db.session.add(row)
    row.is_active = active
    db.session.commit()


class TestChannelSwitch:
    def test_absent_row_means_on(self, app):
        """A row is how you override a default, not how you earn one."""
        with app.app_context():
            assert _channel_active("SMS") is True

    def test_explicit_off_is_off(self, app):
        with app.app_context():
            _set(NotificationChannel.WHATSAPP.value, False)
            assert _channel_active(NotificationChannel.WHATSAPP.value) is False

    def test_explicit_on_is_on(self, app):
        with app.app_context():
            _set(NotificationChannel.WHATSAPP.value, True)
            assert _channel_active(NotificationChannel.WHATSAPP.value) is True

    def test_guest_notify_skips_a_switched_off_channel(self, app):
        """The switch has to mean the same thing on the guest path.

        With WhatsApp off and SMS unconfigured, a guest message falls through
        to LOGGED_ONLY — and never reports itself as delivered by WhatsApp."""
        from app.services.notifications.guest_notify import notify_guest
        with app.app_context():
            _set(NotificationChannel.WHATSAPP.value, False)
            channel, _ = notify_guest("+254700000001", "booking_confirmed",
                                      {"guest_name": "Njeri", "resource": "Villa 4",
                                       "date": "2026-09-20"})
            assert channel != "WHATSAPP"

    def test_switched_off_channel_writes_no_attempt_row(self, app):
        """An audit entry for an attempt that never happened is a false entry."""
        from app.models.audit_log import AuditLog
        from app.services.notifications.guest_notify import notify_guest
        with app.app_context():
            _set(NotificationChannel.WHATSAPP.value, False)
            before = db.session.query(AuditLog).filter(
                AuditLog.action.like("%whatsapp%")).count()
            notify_guest("+254700000001", "booking_confirmed",
                         {"guest_name": "Njeri", "resource": "Villa 4",
                          "date": "2026-09-20"})
            after = db.session.query(AuditLog).filter(
                AuditLog.action.like("%whatsapp%")).count()
            assert after == before
