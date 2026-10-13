"""API blueprint — registers all route modules under /api."""

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Import route modules so their @api_bp.route decorators register.
from app.api import dashboard, forms, notifications, questions, responses, rewards, users  # noqa: E402, F401
