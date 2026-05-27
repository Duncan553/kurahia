"""
extensions.py — Extension instances created here (not tied to any app yet).
The factory imports these and calls .init_app(app) to bind them.
This breaks the circular-import problem: models import db from here,
not from the factory.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate()
