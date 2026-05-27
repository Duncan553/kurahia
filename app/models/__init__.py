# Import all models so Flask-Migrate can discover them for migrations
from .department import Department
from .role import Role
from .user import User
from .audit_log import AuditLog

__all__ = ["Department", "Role", "User", "AuditLog"]
