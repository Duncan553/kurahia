"""
EventType — the list of event categories is data, not code.
Owner/manager can add new types without a code change.
Seeded via `flask events seed-types`.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class EventType(db.Model):
    __tablename__ = "event_types"

    id        = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name      = db.Column(db.String(60), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<EventType {self.name}>"
