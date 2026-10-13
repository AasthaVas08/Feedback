"""User listing endpoint (dev mode — no auth).

Routes
------
GET /api/users — list all users (for the user selector in the navbar)
"""

from flask import jsonify

from app.api import api_bp
from app.models import User


@api_bp.route("/users", methods=["GET"])
def list_users():
    """Return all users, ordered by role then name."""
    users = User.query.order_by(User.role.desc(), User.name).all()
    return jsonify([
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
        }
        for u in users
    ])
