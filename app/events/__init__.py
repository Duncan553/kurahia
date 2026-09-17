from .core import events_bp, event_types_bp
from . import bill  # noqa: F401 — registers the menu/bill routes on events_bp

__all__ = ["events_bp", "event_types_bp"]
