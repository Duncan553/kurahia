"""
utils/money.py — one place to turn user input into a Decimal amount safely.

WHY THIS EXISTS. The same bug was found in six endpoints, written six times by
the same hands, and it is not an obvious bug:

    try:
        amount = Decimal(str(raw))
    except InvalidOperation:
        return error
    if amount < 0:                      # <-- raises on NaN, outside the try
        return error

`Decimal('NaN')` CONSTRUCTS FINE. The try only guards the constructor, and then
every comparison against NaN raises `decimal.InvalidOperation` — which nothing
catches, so it surfaces as a bare 500 on a cash-count, a budget, an end-of-day
close, an order quantity. `is_finite()` has to be checked BEFORE any comparison,
and once you know that, the fix reads as obvious. It was not obvious six times.

Two more holes lived in the same lines, so they are closed here too:

  NO UPPER BOUND. Amount columns are Numeric(14,2) — maximum 999,999,999,999.99.
  A fat-fingered 1e15 is a numeric-field-overflow 500 on PostgreSQL, and on
  SQLite it silently records a trillion-shilling balance.

  SUB-CENT SCALE. A payment of 0.004 returned 201 and echoed 0.004, while the
  ledger stored 0.00 — the receipt and the ledger disagreed. 0.4999 rounded UP
  to 0.50, crediting the guest more than they handed over.

Returns (value, error) — exactly one of them is None. Callers stay one line:

    amount, err = parse_amount(raw, "amount")
    if err:
        return jsonify({"error": err}), 400
"""
from decimal import Decimal, InvalidOperation

# Numeric(14,2): 12 digits before the point. Anything at or above this cannot
# be stored, so it is refused with a sentence rather than a database error.
MAX_AMOUNT = Decimal("999999999999.99")

# Money here is shillings and cents. A third decimal place is not a smaller
# amount, it is a mistake — and silently rounding somebody's money is worse
# than telling them.
CENTS = Decimal("0.01")


def parse_amount(raw, field="amount", *, allow_zero=False,
                 allow_negative=False, maximum=MAX_AMOUNT):
    """Parse a money/quantity value from request JSON.

    Order matters and is the whole point: construct, then check FINITE, and
    only then compare. Comparing first is the bug this module exists to end.
    """
    if raw is None:
        return None, f"{field} is required."

    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None, f"{field} must be a valid number."

    # BEFORE any comparison. Decimal('NaN') and Decimal('Infinity') both build
    # cleanly and then raise on <, >, <=, >=.
    if not value.is_finite():
        return None, f"{field} must be a real number."

    if not allow_negative and value < 0:
        return None, f"{field} cannot be negative."
    if not allow_zero and not allow_negative and value == 0:
        return None, f"{field} must be more than zero."

    if abs(value) > maximum:
        return None, (f"{field} is too large. The most that can be recorded is "
                      f"KSh {maximum:,}. Check for an extra digit.")

    # Reject sub-cent rather than rounding it. Quantizing here would make the
    # receipt and the ledger agree on a number the customer never handed over.
    if value != value.quantize(CENTS) and value.as_tuple().exponent < -2:
        return None, (f"{field} cannot be smaller than one cent. "
                      f"Round to 2 decimal places.")

    return value, None


def parse_quantity(raw, field="quantity", *, maximum=Decimal("100000")):
    """Same guarantees for a countable quantity, which may carry more decimal
    places than money (a recipe uses 0.0833 of a cake) but still must be real,
    positive and sane."""
    if raw is None:
        return None, f"{field} is required."
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None, f"{field} must be a valid number."
    if not value.is_finite():
        return None, f"{field} must be a real number."
    if value <= 0:
        return None, f"{field} must be a positive number."
    if value > maximum:
        return None, (f"{field} is too large. The most that can be recorded at "
                      f"once is {maximum:,}. Check for an extra digit.")
    return value, None
