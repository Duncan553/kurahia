# Import all models so Flask-Migrate can discover them for migrations
from .department import Department
from .role import Role
from .user import User
from .audit_log import AuditLog
from .inventory_item import InventoryItem
from .stock_movement import StockMovement, MovementReason, CONSUMPTION_REASONS
from .stock_count import StockCount, CountType
from .purchase_request import PurchaseRequest, RequestStatus
from .purchase import Purchase
from .judge_baseline import JudgeBaseline
from .judge_alert import JudgeAlert, AlertStatus, AlertSeverity

__all__ = [
    "Department", "Role", "User", "AuditLog",
    "InventoryItem",
    "StockMovement", "MovementReason", "CONSUMPTION_REASONS",
    "StockCount", "CountType",
    "PurchaseRequest", "RequestStatus",
    "Purchase",
    "JudgeBaseline",
    "JudgeAlert", "AlertStatus", "AlertSeverity",
]
