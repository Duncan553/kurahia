"""
StationRoster — which department/station each employee is working TODAY.

Every employee has a fixed home department on their User record (set at
account creation). This table is the day-to-day override on top of that: a
manager can put someone on a different station for a shift (e.g. a waiter
covering Front Desk today) without touching their permanent account.

One active row per (user, roster_date) — reassigning the same person on the
same day updates the row in place rather than piling up duplicates; history
of who-was-reassigned-when lives in AuditLog, same as Tab/CleaningStatus
assignment (see app/pos/tabs.py, app/housekeeping/__init__.py).
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class StationRoster(db.Model):
    __tablename__ = "station_rosters"
    __table_args__ = (
        db.UniqueConstraint("user_id", "roster_date", name="uq_roster_user_date"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id       = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=False)
    roster_date   = db.Column(db.Date, nullable=False, index=True)

    assigned_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user         = db.relationship("User", foreign_keys=[user_id], lazy="select")
    department   = db.relationship("Department", foreign_keys=[department_id], lazy="select")
    assigned_by  = db.relationship("User", foreign_keys=[assigned_by_id], lazy="select")

    def __repr__(self):
        return f"<StationRoster {self.user_id} -> {self.department_id} on {self.roster_date}>"
