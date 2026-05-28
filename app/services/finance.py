"""
services/finance.py — Pure calculation helpers for finance reports.

All numbers are derived from immutable transaction records.
Nothing is stored-and-overwritten here — these are query functions only.
"""
from calendar import monthrange
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.purchase import Purchase
from app.models.inventory_item import InventoryItem
from app.models.cash_reconciliation import CashReconciliation, cash_recon_payments
from app.models.order_item import OrderItem, OrderItemStatus
from app.models.order import Order
from app.models.charge import Charge


def parse_date_bounds(date_str: str) -> tuple[datetime, datetime]:
    """'YYYY-MM-DD' → (start_of_day UTC, start_of_next_day UTC)."""
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d, d + timedelta(days=1)


def parse_month_bounds(period_str: str) -> tuple[datetime, datetime]:
    """'YYYY-MM' → (first of month UTC, first of next month UTC)."""
    year, month = map(int, period_str.split("-"))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    _, days_in_month = monthrange(year, month)
    end = start + timedelta(days=days_in_month)
    return start, end


def get_staff_pending_cash(staff_id: str) -> tuple[Decimal, list]:
    """
    Returns (total_pending, payments) — all unreconciled CASH payments
    received by this staff member. A payment is reconciled when its id
    appears in cash_recon_payments.
    """
    reconciled_ids = db.session.query(cash_recon_payments.c.payment_id).scalar_subquery()
    pending = db.session.query(Payment).filter(
        Payment.received_by_id == staff_id,
        Payment.method == PaymentMethod.CASH.value,
        ~Payment.id.in_(reconciled_ids),
    ).order_by(Payment.created_at_utc).all()

    total = sum(Decimal(str(p.amount)) for p in pending) if pending else Decimal("0")
    return total, pending


def get_budget_spend(dept_id: str, period_start: datetime, period_end: datetime) -> Decimal:
    """
    Sum of purchase actual_cost for a department in a time window.
    Joins through InventoryItem to get the department.
    """
    raw = db.session.query(func.sum(Purchase.actual_cost)).join(
        InventoryItem, Purchase.item_id == InventoryItem.id
    ).filter(
        InventoryItem.department_id == dept_id,
        Purchase.timestamp_added >= period_start,
        Purchase.timestamp_added < period_end,
    ).scalar()
    return Decimal(str(raw)) if raw is not None else Decimal("0")


def get_period_revenue_by_method(period_start: datetime, period_end: datetime) -> dict:
    """Total revenue split by payment method for a period."""
    rows = db.session.query(
        Payment.method, func.sum(Payment.amount)
    ).filter(
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc < period_end,
    ).group_by(Payment.method).all()

    result = {m.value: Decimal("0") for m in PaymentMethod}
    for method, total in rows:
        result[method] = Decimal(str(total)) if total else Decimal("0")
    result["total"] = sum(result.values())
    return result


def get_period_cash_reconciled_total(period_start: datetime, period_end: datetime) -> Decimal:
    """
    Sum of actual_amount from all CashReconciliations that closed within
    this period. This is what the cashier should have placed in the safe.
    """
    raw = db.session.query(func.sum(CashReconciliation.actual_amount)).filter(
        CashReconciliation.period_end_utc >= period_start,
        CashReconciliation.period_end_utc < period_end,
    ).scalar()
    return Decimal(str(raw)) if raw is not None else Decimal("0")


def count_staff_shortfalls(staff_id: str, last_n: int = 3) -> int:
    """
    Count how many of the last N cash reconciliations for this staff are SHORT.
    Used to detect chronic shortfall patterns.
    """
    from app.models.cash_reconciliation import ReconciliationStatus
    recent = (
        db.session.query(CashReconciliation)
        .filter_by(staff_id=staff_id)
        .order_by(CashReconciliation.created_at_utc.desc())
        .limit(last_n)
        .all()
    )
    return sum(1 for r in recent if r.status == ReconciliationStatus.SHORT.value)


def get_void_rates(period_start: datetime, period_end: datetime) -> list[dict]:
    """
    Per-staff void rate: cancelled items / total items sent in the period.
    Returns list sorted by void_rate desc.
    """
    items = (
        db.session.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.sent_at >= period_start,
            Order.sent_at < period_end,
        )
        .all()
    )
    if not items:
        return []

    # Aggregate by who created the order (proxy for staff responsible)
    from collections import defaultdict
    sent_counts    = defaultdict(int)
    void_counts    = defaultdict(int)
    staff_ids_seen = {}

    for oi in items:
        actor_id = oi.order.created_by_id if oi.order else None
        if not actor_id:
            continue
        sent_counts[actor_id]  += 1
        staff_ids_seen[actor_id] = oi.order.created_by if oi.order else None
        if oi.status == OrderItemStatus.CANCELLED.value:
            void_counts[actor_id] += 1

    total_items   = sum(sent_counts.values())
    total_voids   = sum(void_counts.values())
    avg_rate      = (total_voids / total_items) if total_items > 0 else 0

    results = []
    for staff_id, total in sent_counts.items():
        voids = void_counts[staff_id]
        rate  = voids / total if total > 0 else 0
        staff = staff_ids_seen.get(staff_id)
        results.append({
            "staff_id":   staff_id,
            "staff_name": staff.username if staff else "unknown",
            "total_items":  total,
            "void_count":   voids,
            "void_rate_pct": round(rate * 100, 1),
            "avg_rate_pct":  round(avg_rate * 100, 1),
            "flagged":       total >= 5 and rate > avg_rate * 2,
        })
    results.sort(key=lambda x: x["void_rate_pct"], reverse=True)
    return results
