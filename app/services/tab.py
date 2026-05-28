"""
tab.py — Tab financial state, always derived, never stored.

get_tab_balance(tab_id) → Decimal
  = SUM(charges.amount) - SUM(payments.amount)

Positive  → customer still owes money.
Zero      → fully paid.
Negative  → customer has credit (e.g. band tab started with a gate payment).

is_tab_closable(tab_id) → (bool, reason_string)
  True only when balance ≤ 0 AND every OrderItem is SERVED or CANCELLED.
"""
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.order import Order
from app.models.order_item import OrderItem, OrderItemStatus


def get_tab_balance(tab_id: str) -> Decimal:
    """Derived tab balance. This is the ONLY correct way to read it."""
    charges_total = db.session.query(func.sum(Charge.amount)).filter(
        Charge.tab_id == tab_id
    ).scalar()
    payments_total = db.session.query(func.sum(Payment.amount)).filter(
        Payment.tab_id == tab_id
    ).scalar()
    charges  = Decimal(str(charges_total))  if charges_total  is not None else Decimal("0")
    payments = Decimal(str(payments_total)) if payments_total is not None else Decimal("0")
    return charges - payments


def is_tab_closable(tab_id: str) -> tuple[bool, str]:
    """Returns (True, "") or (False, plain-English reason)."""
    balance = get_tab_balance(tab_id)
    if balance > Decimal("0"):
        return False, f"This tab still has an outstanding balance of {balance}. Collect payment first."

    # Check for unresolved order items
    terminal = {OrderItemStatus.SERVED.value, OrderItemStatus.CANCELLED.value}
    open_orders = db.session.query(Order).filter_by(tab_id=tab_id).all()
    for order in open_orders:
        for item in order.items:
            if item.status not in terminal:
                return False, f"Order item '{item.menu_item.name if item.menu_item else item.id}' is still {item.status}. Resolve all items before closing."

    return True, ""
