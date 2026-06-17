"""
SystemSetting — owner-configurable key-value pairs.
business_day_start_hour: integer 0-23, the hour (in Africa/Nairobi) when a new business day begins.
Default 6 (6:00 AM). Owner sets the real one in Settings.
"""
from app.extensions import db


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500), nullable=False)

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value}>"
