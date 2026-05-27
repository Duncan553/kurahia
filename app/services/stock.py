"""
stock.py — The single place that computes derived stock levels.
Stock level is NEVER stored. It is always computed from StockMovement rows.

Two functions:
  get_current_stock(item_id)    → stock right now
  get_stock_at(item_id, ts)     → stock as of a specific UTC timestamp

Both return a Decimal. Callers must be inside an app context.
"""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import func
from app.extensions import db
from app.models.stock_movement import StockMovement


def get_current_stock(item_id: str) -> Decimal:
    """Sum every movement for this item. The result IS the current stock."""
    result = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id
    ).scalar()
    # Wrap via str to avoid float conversion loss (SQLite may return float)
    return Decimal(str(result)) if result is not None else Decimal("0")


def get_stock_at(item_id: str, as_of: datetime) -> Decimal:
    """Stock level as of a point in time — used by variance math as the opening."""
    result = db.session.query(func.sum(StockMovement.change_amount)).filter(
        StockMovement.item_id == item_id,
        StockMovement.timestamp_utc <= as_of,
    ).scalar()
    return Decimal(str(result)) if result is not None else Decimal("0")
