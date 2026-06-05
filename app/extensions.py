"""
extensions.py — Extension instances created here (not tied to any app yet).
The factory imports these and calls .init_app(app) to bind them.
This breaks the circular-import problem: models import db from here,
not from the factory.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate()
# In-memory backend — appropriate for single-server LAN deployment (no Redis needed)
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
