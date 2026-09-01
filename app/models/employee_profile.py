"""
EmployeeProfile — the real person behind a User token.
1:1 with User via user_id (unique FK).
wage_rate + wage_period feed the payroll-draft endpoint.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class WagePeriod(str, enum.Enum):
    HOURLY  = "HOURLY"
    DAILY   = "DAILY"
    MONTHLY = "MONTHLY"


class EmployeeProfile(db.Model):
    __tablename__ = "employee_profiles"

    id      = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, unique=True)

    full_name   = db.Column(db.String(200), nullable=False)
    photo_path  = db.Column(db.String(500), nullable=True)
    national_id = db.Column(db.String(30),  nullable=True, unique=True)
    phone       = db.Column(db.String(30),  nullable=False)

    emergency_contact_name  = db.Column(db.String(200), nullable=True)
    emergency_contact_phone = db.Column(db.String(30),  nullable=True)

    hire_date   = db.Column(db.Date, nullable=True)
    wage_rate   = db.Column(db.Numeric(12, 4), nullable=True)
    wage_period = db.Column(db.String(10),     nullable=True)   # HOURLY / DAILY / MONTHLY

    # Where payroll pays this employee. Employee sets/edits their own; manager
    # and owner see it read-only on StaffScreen. Plain columns, same as
    # phone/national_id above — nothing in this codebase is encrypted at rest.
    payment_method         = db.Column(db.String(20), nullable=True)   # MPESA / BANK
    payment_account_number = db.Column(db.String(60),  nullable=True)  # phone no. or bank acct no.

    # ── The working pattern this person is normally on ────────────────────────
    # Rostering by hand does not survive contact with a real week: 14 people x 6
    # shifts is 84 rows somebody types every Sunday. So it gets typed once, then
    # never again, and the attendance board quietly stops meaning anything.
    #
    # The pattern is stored ONCE and shifts are generated from it — a recurring
    # template plus copy-forward, which is what every scheduling tool does,
    # reduced to the smallest thing that still gives a true board.
    #
    #   roster_days   "MON,TUE,WED,THU,FRI"  the days they normally work
    #   roster_start  "16:00"                local start (Africa/Nairobi)
    #   roster_end    "00:00"                local end; before start = overnight
    #
    # All NULL means "not on a regular pattern" — casuals, and anyone whose days
    # move around, are rostered by hand exactly as before. Nothing is forced.
    roster_days  = db.Column(db.String(60), nullable=True)
    roster_start = db.Column(db.String(5),  nullable=True)
    roster_end   = db.Column(db.String(5),  nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", foreign_keys=[user_id], lazy="select")

    def __repr__(self):
        return f"<EmployeeProfile {self.full_name} user={self.user_id}>"
