"""Application configuration.

Switch between SQLite (dev) and PostgreSQL (prod) via the DATABASE_URL
environment variable.  See .env.example for the format.
"""

import os
from pathlib import Path

basedir = Path(__file__).resolve().parent


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Default to SQLite in an ``instance/`` directory next to this file.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{basedir / 'instance' / 'feedback.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Reward defaults
    DEFAULT_MAX_REWARD = int(os.environ.get("DEFAULT_MAX_REWARD", 100))
    DEFAULT_MIN_REWARD = int(os.environ.get("DEFAULT_MIN_REWARD", 10))

    # Email (Microsoft 365 Graph API)
    MAIL_SENDER_EMAIL = os.environ.get("MAIL_SENDER_EMAIL", "")
    MAIL_SENDER_NAME = os.environ.get("MAIL_SENDER_NAME", "Feedback Platform")
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "false").lower() in ("true", "1", "yes")

    # Microsoft 365 Graph API credentials (OAuth2 client credentials flow)
    MS_GRAPH_CLIENT_ID = os.environ.get("MS_GRAPH_CLIENT_ID", "")
    MS_GRAPH_CLIENT_SECRET = os.environ.get("MS_GRAPH_CLIENT_SECRET", "")
    MS_GRAPH_TENANT_ID = os.environ.get("MS_GRAPH_TENANT_ID", "")

    # Base URL for form links in emails (no trailing slash)
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")


class DevelopmentConfig(Config):
    DEBUG = True
    # Emails disabled by default in dev — set MAIL_ENABLED=true to test
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "false").lower() in ("true", "1", "yes")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Always disabled in tests — the email service is mocked
    MAIL_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    # Emails enabled by default in production
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "true").lower() in ("true", "1", "yes")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
