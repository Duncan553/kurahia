"""
Budget — per-department monthly spending cap.
period: "YYYY-MM" string. One budget per department per period (unique constraint).
Spend is derived: SUM(purchases.actual_cost) for that dept in that period.
Editable/disable-able by owner. PATCH to change amount; disable to suspend.
"""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Budget(db.Model):
    __tablename__ = "budgets"

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), nullable=False)
    period        = db.Column(db.String(7),  nullable=False)   # "YYYY-MM"
    amount        = db.Column(db.Numeric(14, 2), nullable=False)
    set_by_id     = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    department = db.relationship("Department", lazy="select")
    set_by     = db.relationship("User", foreign_keys=[set_by_id], lazy="select")

    __table_args__ = (
        db.CheckConstraint("amount >= 0", name="ck_budget_amount_nonneg"),
        db.UniqueConstraint("department_id", "period", name="uq_budget_dept_period"),
    )

    def __repr__(self):
        return f"<Budget dept={self.department_id} period={self.period} amount={self.amount}>"
