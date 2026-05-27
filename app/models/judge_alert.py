"""
JudgeAlert — an anomaly the judge engine flagged.
Owner-only. Append-only — corrections are new rows.
Will be empty until POS sales data arrives (Layer 2 stays dormant by design).
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class AlertStatus(str, enum.Enum):
    OPEN         = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED     = "RESOLVED"
    DISMISSED    = "DISMISSED"


class AlertSeverity(str, enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class JudgeAlert(db.Model):
    __tablename__ = "judge_alerts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=True)

    # Type of anomaly the judge detected
    alert_type = db.Column(db.String(50), nullable=False)   # VARIANCE / SPOILAGE_SPIKE / RATIO

    severity   = db.Column(db.String(10), nullable=False, default=AlertSeverity.MEDIUM)
    description = db.Column(db.Text, nullable=False)

    # The analysis window that triggered this alert
    period_start = db.Column(db.DateTime(timezone=True), nullable=True)
    period_end   = db.Column(db.DateTime(timezone=True), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=AlertStatus.OPEN)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    acknowledged_at = db.Column(db.DateTime(timezone=True), nullable=True)
    acknowledged_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    item             = db.relationship("InventoryItem", lazy="select")
    acknowledged_by  = db.relationship("User", foreign_keys=[acknowledged_by_id], lazy="select")

    def __repr__(self):
        return f"<JudgeAlert {self.alert_type} {self.severity} {self.status}>"
