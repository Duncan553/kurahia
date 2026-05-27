"""
config.py — All environment-aware settings live here.
The app factory reads from this; nothing else touches env vars directly.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    # Flask secret for session signing (not JWT)
    SECRET_KEY = os.environ["SECRET_KEY"]

    # JWT config — access token is short-lived, refresh is longer
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    # SQLAlchemy — disable modification tracking (saves memory)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Auth lockout policy
    FAILED_ATTEMPTS_LOCKOUT: int = int(os.getenv("FAILED_ATTEMPTS_LOCKOUT", 5))
    LOCKOUT_MINUTES: int = int(os.getenv("LOCKOUT_MINUTES", 15))

    # Business day starts at this UTC hour (e.g. 6 = 6am UTC = 9am EAT)
    BUSINESS_DAY_START_HOUR: int = int(os.getenv("BUSINESS_DAY_START_HOUR", 6))


class DevelopmentConfig(BaseConfig):
    # SQLite lives in instance/ which is gitignored
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///kurahia_dev.db"
    )
    DEBUG = True


class ProductionConfig(BaseConfig):
    # Postgres required in prod; validated at app startup in create_app()
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    # Fresh in-memory DB per test run; no filesystem state
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Use lower thresholds so lockout tests don't need 5 attempts
    FAILED_ATTEMPTS_LOCKOUT = 3
    LOCKOUT_MINUTES = 1


# Map name → class so the factory can do config[env_name]
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
