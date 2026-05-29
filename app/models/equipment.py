"""
Equipment — anything with a maintenance schedule: jetskis, boats, generators.
MaintenanceLog: append-only log of every service event.
SafetyCheck: pass/fail checklist per equipment per check date.
is_due_service: derived — (now - last_service_utc).days >= service_interval_days.
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class EquipmentStatus(str, enum.Enum):
    ACTIVE      = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED     = "RETIRED"


class Equipment(db.Model):
    __tablename__ = "equipment"

    id                   = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name                 = db.Column(db.String(100), nullable=False)
    equipment_type       = db.Column(db.String(60),  nullable=False)  # e.g. "Jetski", "Generator"
    department_id        = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=True)
    last_service_utc     = db.Column(db.DateTime(timezone=True), nullable=True)
    service_interval_days = db.Column(db.Integer, nullable=True)       # days between services
    status               = db.Column(db.String(15), nullable=False, default=EquipmentStatus.ACTIVE.value)
    notes                = db.Column(db.Text, nullable=True)
    is_active            = db.Column(db.Boolean, nullable=False, default=True)

    created_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    department = db.relationship("Department", lazy="select")
    created_by = db.relationship("User",       foreign_keys=[created_by_id], lazy="select")
    maintenance_logs = db.relationship("MaintenanceLog", back_populates="equipment",
                                       lazy="dynamic", cascade="all, delete-orphan")
    safety_checks    = db.relationship("SafetyCheck",    back_populates="equipment",
                                       lazy="dynamic", cascade="all, delete-orphan")

    @property
    def is_due_service(self) -> bool:
        if not self.service_interval_days or not self.last_service_utc:
            return False
        now = datetime.now(timezone.utc)
        last = self.last_service_utc
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last).days >= self.service_interval_days

    def __repr__(self):
        return f"<Equipment {self.name} {self.status}>"


class MaintenanceLog(db.Model):
    __tablename__ = "maintenance_logs"

    id               = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    equipment_id     = db.Column(db.String(36), db.ForeignKey("equipment.id"),
                                 nullable=False, index=True)
    performed_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    performed_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    notes            = db.Column(db.Text, nullable=True)
    cost             = db.Column(db.Numeric(12, 2), nullable=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    equipment    = db.relationship("Equipment", back_populates="maintenance_logs", lazy="select")
    performed_by = db.relationship("User", foreign_keys=[performed_by_id], lazy="select")

    def __repr__(self):
        return f"<MaintenanceLog eq={self.equipment_id} {self.performed_at_utc}>"


class SafetyCheck(db.Model):
    __tablename__ = "safety_checks"

    id               = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    equipment_id     = db.Column(db.String(36), db.ForeignKey("equipment.id"),
                                 nullable=False, index=True)
    performed_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    performed_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    passed           = db.Column(db.Boolean, nullable=False)
    checklist_notes  = db.Column(db.Text, nullable=True)  # JSON string or plain notes

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    equipment    = db.relationship("Equipment", back_populates="safety_checks", lazy="select")
    performed_by = db.relationship("User", foreign_keys=[performed_by_id], lazy="select")

    def __repr__(self):
        return f"<SafetyCheck eq={self.equipment_id} passed={self.passed}>"
