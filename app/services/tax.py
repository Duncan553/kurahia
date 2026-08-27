"""
tax.py — VAT, kept configurable rather than hardcoded.

Kenya's standard VAT rate is 16% and applies to accommodation, restaurant and
bar sales; a bundled package (room + meals + drinks at one price) is a single
composite supply taxed at the standard rate rather than split.

Two things are deliberate here.

RATE LIVES IN THE DATABASE, NOT THIS FILE. Invariant 10 — configuration through
data. Rates change by statute, some items are zero-rated or exempt, and the
owner's accountant is the authority on which is which. A constant in code would
mean a deploy every time the law moves, and would quietly encode a tax opinion
this system is not qualified to hold.

PRICES ARE VAT-INCLUSIVE. That is the norm in Kenyan hospitality and, more
importantly, it is what the existing data already assumes: every menu price is
what the guest actually pays. Treating those figures as net would raise every
price on the menu by 16% the moment tax was switched on.
"""
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models.system_setting import SystemSetting

VAT_RATE_KEY = "vat_rate_percent"

# Kenya's standard rate. Used only when the setting has never been written —
# the value in the database always wins.
DEFAULT_VAT_RATE = Decimal("16")


def get_vat_rate() -> Decimal:
    """The current VAT rate as a percentage, e.g. Decimal('16')."""
    row = db.session.get(SystemSetting, VAT_RATE_KEY)
    if row is None:
        return DEFAULT_VAT_RATE
    try:
        return Decimal(str(row.value))
    except (ArithmeticError, ValueError):
        # A malformed setting must not silently become 0% and under-report tax.
        return DEFAULT_VAT_RATE


def rate_for_menu_item(menu_item) -> Decimal:
    """The rate that applies to one item.

    A hook for zero-rated and exempt lines. Today everything takes the standard
    rate; when the accountant identifies exceptions this is the single place
    that has to learn about them, rather than every call site.
    """
    return get_vat_rate()


def split_inclusive(gross, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Split a VAT-INCLUSIVE amount into (net, tax).

    gross = net x (1 + rate)   =>   tax = gross x rate / (1 + rate)

    Rounded half-up to the cent, which is the convention KRA invoices use, and
    net is taken as gross - tax so the two always add back to exactly the amount
    the guest paid. Computing both independently is how a receipt ends up a
    cent short of itself.
    """
    gross = Decimal(str(gross))
    r = Decimal(str(rate)) / Decimal("100")
    tax = (gross * r / (Decimal("1") + r)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return gross - tax, tax
