from .resources  import resources_bp
from .core       import bookings_bp
from .deposits   import deposits_bp
from .waivers    import waivers_bp
from .guests     import guests_bp
from .dashboard  import dashboard_bp

__all__ = [
    "resources_bp", "bookings_bp", "deposits_bp",
    "waivers_bp", "guests_bp", "dashboard_bp",
]
