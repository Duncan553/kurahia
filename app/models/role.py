"""
Role model — named permission level within a department.
The three root roles (owner, manager, staff) are seeded by CLI.
`level` encodes hierarchy: owner=10, manager=5, staff=1.
Higher = more authority. Used for creation/reset enforcement.
"""
import uuid
from app.extensions import db


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(50), nullable=False, unique=True)
    # level enforces who can create/reset whom — checked in code, not just display
    level = db.Column(db.Integer, nullable=False)
    department_id = db.Column(
        db.String(36), db.ForeignKey("departments.id"), nullable=True
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    department = db.relationship("Department", back_populates="roles")
    users = db.relationship("User", back_populates="role", lazy="dynamic")

    # DB constraint: level must be positive
    __table_args__ = (
        db.CheckConstraint("level > 0", name="ck_role_level_positive"),
    )

    def __repr__(self):
        return f"<Role {self.name} level={self.level}>"
