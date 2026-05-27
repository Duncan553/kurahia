"""
Department model — organisational unit (e.g. Kitchen, Bar, Front-of-House).
Roles and users belong to departments.
"""
import uuid
from app.extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    # Internal UUID primary key — never expose sequence integers to clients
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Back-references: department.roles / department.users
    roles = db.relationship("Role", back_populates="department", lazy="dynamic")
    users = db.relationship("User", back_populates="department", lazy="dynamic")

    def __repr__(self):
        return f"<Department {self.name}>"
