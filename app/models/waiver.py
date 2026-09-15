"""
Waiver — safety gate for water activities.
Required before any water-activity session charge can be posted on a booking's tab.
is_active allows revocation (e.g. expired waiver) without losing the record.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class WaiverActivityType(str, enum.Enum):
    WATER_ACTIVITY = "WATER_ACTIVITY"
    GENERAL        = "GENERAL"


class Waiver(db.Model):
    __tablename__ = "waivers"

    id                = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # A waiver attaches to a BOOKING (a villa guest who reserved) or to a TAB
    # (a day guest holding a wristband). Exactly one, never both.
    #
    # booking_id used to be the only link and NOT NULL, which meant a day guest
    # could not sign a waiver at all — there was nothing to attach it to. At a
    # resort that sells jet skis to day visitors that is the wrong way round:
    # the people most likely to ride were the ones who could not be recorded as
    # having signed. The waiver form asking for a Booking ID was the symptom.
    booking_id        = db.Column(db.String(36), db.ForeignKey("bookings.id"),
                                  nullable=True, index=True)
    tab_id            = db.Column(db.String(36), db.ForeignKey("tabs.id"),
                                  nullable=True, index=True)
    activity_type     = db.Column(db.String(20), nullable=False)   # WATER_ACTIVITY / GENERAL
    signed_by_name    = db.Column(db.String(200), nullable=False)
    signature_proof   = db.Column(db.Text, nullable=True)   # base64 PNG of drawn signature
    is_active         = db.Column(db.Boolean, nullable=False, default=True)
    # Nullable so pre-existing rows (created before this column existed) don't need
    # a backfill — SQLite/Postgres both allow multiple NULLs under a UNIQUE constraint.
    # Every new waiver is required to carry one (see create_waiver in bookings/waivers.py).
    idempotency_key   = db.Column(db.String(100), nullable=True, unique=True)

    signed_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking = db.relationship("Booking", back_populates="waivers", lazy="select")
    tab     = db.relationship("Tab", foreign_keys=[tab_id], lazy="select")

    __table_args__ = (
        # Structural, not app-level: a waiver that belongs to nobody protects
        # nobody, and one claiming both a booking and a wristband is ambiguous
        # about which guest actually signed.
        db.CheckConstraint(
            "(booking_id IS NOT NULL AND tab_id IS NULL) OR "
            "(booking_id IS NULL AND tab_id IS NOT NULL)",
            name="ck_waiver_booking_xor_tab",
        ),
    )

    def __repr__(self):
        who = f"booking={self.booking_id}" if self.booking_id else f"tab={self.tab_id}"
        return f"<Waiver {self.activity_type} {who}>"
