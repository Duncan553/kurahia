from .profiles    import profiles_bp
from .wifi        import wifi_bp
from .shifts      import shifts_bp
from .clock       import clock_bp
from .leave       import leave_bp
from .absence     import absence_bp
from .attendance  import attendance_bp
from .performance import performance_bp

__all__ = [
    "profiles_bp", "wifi_bp", "shifts_bp", "clock_bp",
    "leave_bp", "absence_bp", "attendance_bp", "performance_bp",
]
