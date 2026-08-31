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


BAND_CREDIT_CEILING_MULTIPLIER = Decimal("2")  # allow up to 2x the entry fee (KSh 6,000)


def check_band_credit(tab_id: str, new_charge: Decimal) -> tuple[bool, str]:
    """
    For band tabs: block charges that would put the running balance more than
    2× the entry fee above zero (i.e. the guest would owe more than KSh 6,000).
    Normal tabs (villa, walk-in) have no ceiling — returns (True, "").
    Returns (ok, plain-English error message).
    """
    from app.models.tab import Tab
    from app.models.wristband import Wristband
    from app.services.gate import ENTRY_FEE

    tab = db.session.get(Tab, tab_id)
    if not tab:
        return True, ""  # let the main path handle missing tab

    # Only enforce ceiling on band tabs (wristbands), not villa/booking tabs
    band = db.session.query(Wristband).filter_by(tab_id=tab_id).first()
    if not band:
        return True, ""  # not a band tab

    ceiling = ENTRY_FEE * BAND_CREDIT_CEILING_MULTIPLIER  # KSh 6,000
    current_balance = get_tab_balance(tab_id)
    if current_balance + new_charge > ceiling:
        return False, (
            f"This wristband has reached its spending limit. "
            f"Current balance: KSh {current_balance}. "
            f"Ask the guest to add more credit at the gate."
        )
    return True, ""


def is_tab_closable(tab_id: str) -> tuple[bool, str]:
    """Returns (True, "") or (False, plain-English reason)."""
    balance = get_tab_balance(tab_id)
    if balance > Decimal("0"):
        return False, f"This tab still has an outstanding balance of {balance}. Collect payment first."

    # Check for unresolved order items.
    #
    # REFUNDED belongs here and was missing. It is terminal in VALID_TRANSITIONS
    # (app/models/order_item.py:41) and terminal in _maybe_complete_order, but
    # this set listed only SERVED and CANCELLED — so refunding a served item
    # trapped the tab forever: "Order item X is still REFUNDED", with no
    # transition left that could clear it. The guest walks out and the table
    # stays open for good, which is exactly the state a refund is meant to end.
    terminal = {OrderItemStatus.SERVED.value,
                OrderItemStatus.CANCELLED.value,
                OrderItemStatus.REFUNDED.value}
    open_orders = db.session.query(Order).filter_by(tab_id=tab_id).all()
    for order in open_orders:
        for item in order.items:
            if item.status not in terminal:
                return False, f"Order item '{item.menu_item.name if item.menu_item else item.id}' is still {item.status}. Resolve all items before closing."

    return True, ""
