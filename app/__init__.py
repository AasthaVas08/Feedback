"""Flask application factory."""

import os

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Parameters
    ----------
    config_name:
        One of ``development``, ``testing``, ``production``.
        Falls back to the ``FLASK_ENV`` env-var, then ``development``.
    """
    from config import config_by_name

    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    # Ensure the instance folder exists (SQLite file lives here).
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialise extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Import every model module inside an app context so that:
    # 1. Alembic's autogenerate can detect all tables for migrations.
    # 2. SQLAlchemy's metadata is populated before create_all() or
    #    db.session queries run.
    # The noqa suppresses "imported but unused" — the import itself
    # is the side effect we need (class registration on db.metadata).
    with app.app_context():
        from app.models import answer, form, question, response, reward, user, notification  # noqa: F401

    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp)

    from app.views import views_bp
    app.register_blueprint(views_bp)

    # Register CLI commands
    from app.cli import notify_cli
    app.cli.add_command(notify_cli)

    # Register a minimal health-check route
    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app
