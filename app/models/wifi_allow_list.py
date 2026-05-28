"""
WiFiAllowList — defines which networks are "on the hotel WiFi."
Owner edits this; the clock-in endpoint validates source_ip against active rows.
ip_cidr: standard CIDR notation, e.g. "192.168.1.0/24" or "10.0.0.0/8".
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class WiFiAllowList(db.Model):
    __tablename__ = "wifi_allow_list"

    id        = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ssid      = db.Column(db.String(100), nullable=False)
    ip_cidr   = db.Column(db.String(50),  nullable=False)   # "192.168.1.0/24"
    label     = db.Column(db.String(200), nullable=True)    # human description
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<WiFiAllowList ssid={self.ssid} cidr={self.ip_cidr}>"
