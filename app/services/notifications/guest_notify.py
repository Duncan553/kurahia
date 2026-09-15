"""
guest_notify.py — Unified guest communication dispatcher.

Tries WhatsApp first (if configured), falls back to SMS, falls back to
in-app notification log. Every attempt is audit-logged regardless of outcome.

This is for GUEST-facing messages (booking confirmations, check-in reminders,
receipts). Internal employee notifications use dispatcher.py instead.

Usage:
    from app.services.notifications.guest_notify import notify_guest, MessageType
    notify_guest("+254712345678", MessageType.BOOKING_CONFIRMED, {
        "resource": "Villa 1", "checkin": "2026-07-01", "checkout": "2026-07-03",
        "booking_id": "abc-123",
    })
"""
import enum
import logging
from datetime import datetime, timezone
from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class MessageType(str, enum.Enum):
    BOOKING_CONFIRMED  = "BOOKING_CONFIRMED"
    CHECKIN_REMINDER   = "CHECKIN_REMINDER"
    CHECKOUT_REMINDER  = "CHECKOUT_REMINDER"
    RECEIPT            = "RECEIPT"


def _kind(message_type) -> str:
    """The enum's VALUE, lower-cased — never the member.

    `f"{MessageType.BOOKING_CONFIRMED}"` renders as
    "MessageType.BOOKING_CONFIRMED" on Python 3.12, so the audit trail carried
    an internal class name where a message kind belonged. Existing rows keep
    what they were written with, because the log is append-only and rewriting
    history is the one thing it exists to prevent.
    """
    return getattr(message_type, "value", str(message_type)).lower()


# ── Message templates ────────────────────────────────────────────────────────
# Each key maps to a format string. The caller passes a context dict whose
# keys must match the {placeholders} in the template.

TEMPLATES: dict[str, str] = {
    MessageType.BOOKING_CONFIRMED: (
        "Your booking at Waterfront Country Club is confirmed. "
        "{resource} from {checkin} to {checkout}. Reference: {booking_id}."
    ),
    MessageType.CHECKIN_REMINDER: (
        "Welcome to Waterfront Country Club! Your check-in for {resource} "
        "is today. Please present valid ID at the front desk."
    ),
    MessageType.CHECKOUT_REMINDER: (
        "Checkout reminder: {resource} checkout is at {time} today. "
        "Please settle any outstanding balance at the front desk."
    ),
    MessageType.RECEIPT: (
        "Thank you for visiting Waterfront Country Club! Your receipt for "
        "KSh {total} has been recorded. Reference: {tab_ref}."
    ),
}


def _render(message_type: str, context: dict) -> str:
    """Fill the template. Raises KeyError if a required placeholder is missing."""
    template = TEMPLATES[message_type]
    return template.format(**context)


def notify_guest(
    guest_phone: str,
    message_type: str,
    context: dict,
) -> tuple[str, str]:
    """
    Send a guest-facing message via the best available channel.

    Cascade: WhatsApp → SMS → logged-only (in-app audit record).

    Returns (channel, detail):
      "WHATSAPP"     — delivered via WhatsApp
      "SMS"          — delivered via SMS
      "LOGGED_ONLY"  — no delivery channel available; message audit-logged only
      "RENDER_ERROR" — template rendering failed (bad context dict)
    """
    # Render the message body from template + context
    try:
        body = _render(message_type, context)
    except (KeyError, IndexError) as exc:
        detail = f"Template render failed for {message_type}: {exc}"
        logger.error(detail)
        AuditLog.log(
            actor="guest_notify",
            action=f"guest.notify.{_kind(message_type)}.render_error",
            target=guest_phone,
            details=detail,
        )
        return ("RENDER_ERROR", detail)

    # ── Try WhatsApp, IF the owner still has that channel switched on ────
    # NotificationChannelConfig is the owner's allow-list — invariant 10, one
    # row per channel, flip is_active to pause it. The dispatcher has always
    # honoured it (_channel_active). This path did not: it called the socket
    # directly, so a channel the owner had switched OFF was still attempted for
    # every guest message, and the audit log filled with attempts at a channel
    # the resort had decided against. The switch has to mean the same thing on
    # both paths or it does not mean anything.
    from app.services.notifications.dispatcher import _channel_active
    from app.models.notification import NotificationChannel

    if _channel_active(NotificationChannel.WHATSAPP.value):
        from app.services.notifications.whatsapp import send_whatsapp
        wa_status, wa_msg = send_whatsapp(guest_phone, body)
    else:
        wa_status, wa_msg = ("DISABLED", "WhatsApp channel is switched off.")

    # A channel that was never tried leaves no audit row — recording an
    # "attempt" that did not happen would be a false entry on a chained log.
    if wa_status != "DISABLED":
        AuditLog.log(
            actor="guest_notify",
            action=f"guest.notify.{_kind(message_type)}.whatsapp",
            target=guest_phone,
            details=f"status={wa_status} | {wa_msg}",
        )
    if wa_status == "SENT":
        logger.info("WhatsApp sent to %s: %s", guest_phone, message_type)
        return ("WHATSAPP", wa_msg)

    if wa_status == "UNCONFIGURED":
        logger.info("UNCONFIGURED — would send via WhatsApp to %s: %s", guest_phone, body)

    # ── Try SMS fallback ─────────────────────────────────────────────────
    from app.services.notifications.sms import send_sms

    sms_status, sms_msg = send_sms(guest_phone, body)
    AuditLog.log(
        actor="guest_notify",
        action=f"guest.notify.{_kind(message_type)}.sms",
        target=guest_phone,
        details=f"status={sms_status} | {sms_msg}",
    )
    if sms_status == "SENT":
        logger.info("SMS sent to %s: %s", guest_phone, message_type)
        return ("SMS", sms_msg)

    if sms_status == "UNCONFIGURED":
        logger.info("UNCONFIGURED — would send via SMS to %s: %s", guest_phone, body)

    # ── Fallback: logged only ────────────────────────────────────────────
    AuditLog.log(
        actor="guest_notify",
        action=f"guest.notify.{_kind(message_type)}.logged_only",
        target=guest_phone,
        details=f"No delivery channel available. Message: {body}",
    )
    logger.info("No channel available for %s. Logged only: %s", guest_phone, body)
    return ("LOGGED_ONLY", f"No delivery channel. Message logged: {body}")
