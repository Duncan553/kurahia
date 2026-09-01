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

    # ── May this role submit a stock count? ───────────────────────────────────
    # Counting used to require manager level (5+) AND, below owner, the item's
    # own department. Nobody in this resort satisfies both: the manager sits in
    # Management, which holds ZERO inventory, and every department that DOES
    # hold stock is led at level 3 or below (bar_lead 3, head_chef 3, water_lead
    # 2, spa_attendant 2, housekeeping 1, grounds 1). The result was that all 38
    # stock items could only be counted by the owner, personally — so either
    # Amara counts the whole resort every night or nobody counts anything.
    #
    # A level threshold cannot fix it: dropping to level 1 to include the
    # housekeeping and grounds leads would also hand the bar's count to a waiter
    # (peter.mwendwa is a waiter IN the Bar department). "Responsible for the
    # department" is not the same fact as "senior enough", and only the first
    # one is what counting requires.
    #
    # So it is stated as data, per invariant 10 — the owner can grant or revoke
    # it per role from the admin screen without a deploy. Counting is the theft
    # check; who performs it should be a decision the owner makes and can change
    # when somebody is promoted, not a number compiled into a route.
    can_count_stock = db.Column(db.Boolean, nullable=False, default=False)

    department = db.relationship("Department", back_populates="roles")
    users = db.relationship("User", back_populates="role", lazy="dynamic")

    # DB constraint: level must be positive
    __table_args__ = (
        db.CheckConstraint("level > 0", name="ck_role_level_positive"),
    )

    def __repr__(self):
        return f"<Role {self.name} level={self.level}>"
