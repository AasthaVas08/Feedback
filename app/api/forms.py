"""Form CRUD and publish endpoints.

Routes
------
POST   /api/forms              — create a new form (UUID auto-assigned)
GET    /api/forms              — list all forms
GET    /api/forms/<id>         — single form with its questions
PUT    /api/forms/<id>         — update title / description / closes_at
POST   /api/forms/<id>/publish — mark as published (trigger email job)
DELETE /api/forms/<id>         — delete a form and all related data
"""

from datetime import datetime, timezone

from flask import jsonify, request

from app import db
from app.api import api_bp
from app.models import Form, User


def _serialize_form(form: Form, include_questions: bool = False) -> dict:
    """Convert a Form model to a JSON-safe dict."""
    data = {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "owner_id": form.owner_id,
        "owner_name": form.owner.name if form.owner else None,
        "is_published": form.is_published,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "closes_at": form.closes_at.isoformat() if form.closes_at else None,
        "question_count": form.questions.count(),
        "response_count": form.responses.count(),
    }
    if include_questions:
        data["questions"] = [
            {
                "id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.get_options(),
                "order": q.order,
            }
            for q in form.questions.order_by(None).order_by("order").all()
        ]
    return data


# ── POST /api/forms ────────────────────────────────────────────────

@api_bp.route("/forms", methods=["POST"])
def create_form():
    """Create a new feedback form.

    Expects JSON body::

        {
            "title": "Q3 Survey",
            "description": "Optional description",
            "owner_id": 1,
            "closes_at": "2026-12-31T23:59:59+00:00"   // optional
        }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    owner_id = data.get("owner_id")
    if owner_id is None:
        return jsonify({"error": "owner_id is required"}), 400

    owner = db.session.get(User, owner_id)
    if owner is None:
        return jsonify({"error": f"User {owner_id} not found"}), 404
    if owner.role != "owner":
        return jsonify({"error": "Only users with role 'owner' can create forms"}), 403

    closes_at = None
    if data.get("closes_at"):
        try:
            closes_at = datetime.fromisoformat(data["closes_at"])
        except (ValueError, TypeError):
            return jsonify({"error": "closes_at must be a valid ISO-8601 datetime"}), 400

    form = Form(
        title=title,
        description=(data.get("description") or "").strip() or None,
        owner_id=owner.id,
        closes_at=closes_at,
    )
    db.session.add(form)
    db.session.commit()

    return jsonify(_serialize_form(form)), 201


# ── GET /api/forms ─────────────────────────────────────────────────

@api_bp.route("/forms", methods=["GET"])
def list_forms():
    """List all forms, newest first."""
    forms = Form.query.order_by(Form.created_at.desc()).all()
    return jsonify([_serialize_form(f) for f in forms])


# ── GET /api/forms/<id> ────────────────────────────────────────────

@api_bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id: str):
    """Get a single form with its questions."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404
    return jsonify(_serialize_form(form, include_questions=True))


# ── PUT /api/forms/<id> ────────────────────────────────────────────

@api_bp.route("/forms/<form_id>", methods=["PUT"])
def update_form(form_id: str):
    """Update a form's title, description, or closes_at.

    Published forms cannot be updated.
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if form.is_published:
        return jsonify({"error": "Cannot update a published form"}), 409

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "title cannot be empty"}), 400
        form.title = title

    if "description" in data:
        form.description = (data["description"] or "").strip() or None

    if "closes_at" in data:
        if data["closes_at"] is None:
            form.closes_at = None
        else:
            try:
                form.closes_at = datetime.fromisoformat(data["closes_at"])
            except (ValueError, TypeError):
                return jsonify({"error": "closes_at must be a valid ISO-8601 datetime"}), 400

    db.session.commit()
    return jsonify(_serialize_form(form))


# ── POST /api/forms/<id>/publish ───────────────────────────────────

@api_bp.route("/forms/<form_id>/publish", methods=["POST"])
def publish_form(form_id: str):
    """Mark a form as published.

    A published form becomes visible to employees and triggers email
    notifications.  Email sending runs in a background thread so this
    endpoint returns immediately.  Each notification is logged in the
    ``notifications`` table.
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if form.is_published:
        return jsonify({"error": "Form is already published"}), 409

    if form.questions.count() == 0:
        return jsonify({"error": "Cannot publish a form with no questions"}), 400

    form.is_published = True
    db.session.commit()

    # Collect employees who should receive the notification email.
    # This list is returned in the response so the owner can see who
    # will be notified, regardless of whether email sending succeeds.
    employees = User.query.filter_by(role="employee").all()
    notified = [{"id": e.id, "name": e.name, "email": e.email} for e in employees]

    # Queue email notifications in a background thread.
    # queue_publish_notifications creates Notification rows synchronously
    # (so the count is accurate in the response), then spawns a daemon
    # thread for the actual Graph API calls.  We pass the real app object
    # via _get_current_object() because the thread needs its own context.
    from flask import current_app
    from app.services.email_service import queue_publish_notifications

    notifications_created = queue_publish_notifications(
        current_app._get_current_object(), form_id
    )

    return jsonify({
        "message": "Form published successfully",
        "form": _serialize_form(form),
        "notifications_queued": notifications_created,
        "notified_employees": notified,
    })


# ── DELETE /api/forms/<id> ─────────────────────────────────────────

@api_bp.route("/forms/<form_id>", methods=["DELETE"])
def delete_form(form_id: str):
    """Delete a form and all related questions, responses, answers, and rewards."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    db.session.delete(form)
    db.session.commit()

    return jsonify({"message": "Form deleted successfully"}), 200
