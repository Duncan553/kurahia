"""
services/payroll.py — Payroll wage calculations.

Derives gross pay from clock events + wage config, deducts staff meals
(valued at cost_per_unit), returns net pay. All values are Decimal —
never float — matching the codebase invariant.

Wage logic by period type:
  HOURLY  → hours_worked * wage_rate
  DAILY   → (hours_worked / 8) * wage_rate  (8-hour standard day)
  MONTHLY → wage_rate flat (regardless of hours)
"""
from decimal import Decimal
from datetime import datetime, timezone
from app.extensions import db
from app.models.employee_profile import EmployeeProfile
from app.models.stock_movement import StockMovement, MovementReason
from app.models.inventory_item import InventoryItem
from app.services.hr import compute_hours_worked

# Standard working day = 8 hours (used for DAILY wage conversion)
STANDARD_DAY_HOURS = Decimal("8")


def _staff_meal_deductions(user_id: str,
                           period_start: datetime,
                           period_end: datetime) -> Decimal:
    """
    Sum the cost of staff-meal movements logged by this user in the period.

    StockMovement.actor_id = the user who logged the meal (the employee eating).
    Deduction per movement = |change_amount| * item.cost_per_unit.
    Items with no cost_per_unit yet (never purchased) contribute 0.
    """
    # Query all STAFF_MEAL movements by this user in the date range
    movements = (
        db.session.query(StockMovement, InventoryItem)
        .join(InventoryItem, StockMovement.item_id == InventoryItem.id)
        .filter(
            StockMovement.actor_id == user_id,
            StockMovement.reason == MovementReason.STAFF_MEAL.value,
            StockMovement.timestamp_utc >= period_start,
            StockMovement.timestamp_utc < period_end,
        )
        .all()
    )

    total = Decimal("0")
    for mov, item in movements:
        if item.cost_per_unit is not None:
            # change_amount is negative for consumption — use abs
            qty = abs(Decimal(str(mov.change_amount)))
            cost = Decimal(str(item.cost_per_unit))
            total += qty * cost
    return total


def _compute_gross(hours: Decimal, wage_rate: Decimal | None,
                   wage_period: str | None) -> Decimal | None:
    """
    Calculate gross pay from hours worked and wage config.
    Returns None if wage info is missing (employee not yet configured).
    """
    if wage_rate is None or wage_period is None:
        return None

    rate = Decimal(str(wage_rate))

    if wage_period == "HOURLY":
        return hours * rate
    elif wage_period == "DAILY":
        # Convert hours to days (8-hour standard), multiply by daily rate
        days_worked = hours / STANDARD_DAY_HOURS
        return days_worked * rate
    elif wage_period == "MONTHLY":
        # Flat monthly salary regardless of hours
        return rate
    # Unknown wage_period — shouldn't happen, but be safe
    return None


def calculate_payroll(period_start: datetime,
                      period_end: datetime) -> list[dict]:
    """
    Calculate payroll for all active employees in the given period.

    Returns a list of dicts, one per employee:
      {employee_id, employee_name, hours_worked, wage_rate, wage_period,
       gross_pay, deductions, meal_deduction, net_pay}

    All monetary values are Decimal strings (never float).
    """
    profiles = (
        db.session.query(EmployeeProfile)
        .filter_by(is_active=True)
        .all()
    )

    results = []
    for p in profiles:
        # Hours from clock events
        hours = compute_hours_worked(p.id, period_start, period_end)

        # Gross pay from wage config
        gross = _compute_gross(hours, p.wage_rate, p.wage_period)

        # Staff meal deduction (uses user_id since StockMovement.actor_id = user)
        meal_cost = _staff_meal_deductions(p.user_id, period_start, period_end)

        # Net = gross minus deductions (never go below zero)
        net = None
        if gross is not None:
            net = max(gross - meal_cost, Decimal("0"))

        results.append({
            "employee_id":   p.id,
            "employee_name": p.full_name,
            "hours_worked":  str(hours),
            "wage_rate":     str(p.wage_rate) if p.wage_rate else None,
            "wage_period":   p.wage_period,
            "gross_pay":     str(gross) if gross is not None else None,
            "meal_deduction": str(meal_cost),
            "deductions":    str(meal_cost),
            "net_pay":       str(net) if net is not None else None,
        })

    return results
