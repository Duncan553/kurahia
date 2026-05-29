"""
Wristband — gate entry token for a day visitor.
One band = one paying customer (1:1 policy, locked).
band_number is unique per issue_date, enforced by DB constraint + app allocator.
Append-only on creation; only status field transitions after that.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class WristbandStatus(str, enum.Enum):
    ACTIVE      = "ACTIVE"       # band in use
    DEACTIVATED = "DEACTIVATED"  # manually closed by gate staff (customer left)
    FORFEITED   = "FORFEITED"    # EOD sweep — unused credit becomes resort revenue


class Wristband(db.Model):
    __tablename__ = "wristbands"

    id             = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    band_number    = db.Column(db.Integer, nullable=False)
    issue_date     = db.Column(db.String(10), nullable=False)     # "YYYY-MM-DD" — reset daily

    issued_by_id   = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    # Payment that recorded the 3,000 entry fee (also the tab credit — one record)
    entry_payment_id = db.Column(db.String(36), db.ForeignKey("payments.id"), nullable=False)
    tab_id           = db.Column(db.String(36), db.ForeignKey("tabs.id"), nullable=False)

    status              = db.Column(db.String(15), nullable=False, default=WristbandStatus.ACTIVE.value)
    deactivated_at_utc  = db.Column(db.DateTime(timezone=True), nullable=True)
    deactivated_by_id   = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    notes               = db.Column(db.Text, nullable=True)
    idempotency_key     = db.Column(db.String(128), nullable=False, unique=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    issued_by      = db.relationship("User", foreign_keys=[issued_by_id],     lazy="select")
    deactivated_by = db.relationship("User", foreign_keys=[deactivated_by_id], lazy="select")
    entry_payment  = db.relationship("Payment", foreign_keys=[entry_payment_id], lazy="select")
    tab            = db.relationship("Tab", lazy="select")

    # DB-level uniqueness: same band number can't be issued twice on the same day
    __table_args__ = (
        db.UniqueConstraint("band_number", "issue_date", name="uq_wristband_number_date"),
        db.CheckConstraint("band_number > 0", name="ck_wristband_number_pos"),
    )

    def __repr__(self):
        return f"<Wristband #{self.band_number} {self.issue_date} {self.status}>"
