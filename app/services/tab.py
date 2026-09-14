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


# A villa has no natural ceiling the way a wristband does — nobody pre-pays a
# room account the way they top up a band. But "no ceiling" measured out as
# genuinely unlimited: a KSh 3,000 day wristband is stopped at KSh 6,000 while
# an overnight villa, the far more expensive account, would accept a KSh 500,000
# charge without a word. Proved by asking both: BAND refused, VILLA allowed.
#
# What actually backs a villa is the deposit. So the limit is what the guest has
# already put down plus a headroom the resort sets, and it is a STOP, not a
# block — front house can take a payment or raise the booking's own limit, and
# the message says so rather than leaving a waiter stuck at the bar.
VILLA_DEFAULT_HEADROOM = Decimal("20000")


def check_tab_credit(tab_id: str, new_charge: Decimal) -> tuple[bool, str]:
    """Ceiling check for any tab. Band rules unchanged; villas now have one too."""
    from app.models.tab import Tab, TabType
    from app.models.booking import Booking

    tab = db.session.get(Tab, tab_id)
    if not tab:
        return True, ""

    if tab.tab_type == TabType.VILLA.value:
        booking = db.session.query(Booking).filter_by(tab_id=tab_id).first()
        if not booking:
            return True, ""
        # Front house may set a limit per booking; otherwise deposit + headroom.
        limit = getattr(booking, "credit_limit", None)
        if limit is None:
            limit = Decimal(str(booking.deposit_required or 0)) + VILLA_DEFAULT_HEADROOM
        limit = Decimal(str(limit))
        balance = get_tab_balance(tab_id)
        if balance + new_charge > limit:
            return False, (
                f"This room has reached its charging limit of KSh {limit:,.2f}. "
                f"Current balance: KSh {balance:,.2f}. "
                f"Send the guest to front house to settle part of the bill or "
                f"raise the limit."
            )
        return True, ""

    return check_band_credit(tab_id, new_charge)


def check_band_credit(tab_id: str, new_charge: Decimal) -> tuple[bool, str]:
    """
    For band tabs: block charges that would put the running balance more than
    2× the entry fee above zero (i.e. the guest would owe more than KSh 6,000).
    Walk-in tabs have no ceiling — returns (True, ""). Villas are handled by
    check_tab_credit above.
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
