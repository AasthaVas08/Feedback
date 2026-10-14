"""Question CRUD endpoints for a form.

Routes
------
POST   /api/forms/<id>/questions              — add a question
PUT    /api/forms/<id>/questions/<qid>         — update a question
DELETE /api/forms/<id>/questions/<qid>         — delete a question
"""

from flask import jsonify, request

from app import db
from app.api import api_bp
from app.models import Form, Question


def _serialize_question(q: Question) -> dict:
    """Convert a Question model to a JSON-safe dict."""
    return {
        "id": q.id,
        "form_id": q.form_id,
        "question_text": q.question_text,
        "question_type": q.question_type,
        "options": q.get_options(),
        "order": q.order,
    }


def _validate_question_data(data: dict) -> str | None:
    """Return an error message if the question payload is invalid, else None."""
    question_text = (data.get("question_text") or "").strip()
    if not question_text:
        return "question_text is required"

    question_type = data.get("question_type", "text")
    if question_type not in Question.ALLOWED_TYPES:
        return (
            f"question_type must be one of: {', '.join(Question.ALLOWED_TYPES)}"
        )

    # Options are required for multiple_choice and checkbox types.
    if question_type in ("multiple_choice", "checkbox"):
        options = data.get("options")
        if not options or not isinstance(options, list) or len(options) < 2:
            return (
                f"options must be a list with at least 2 items "
                f"for type '{question_type}'"
            )

    return None


# ── POST /api/forms/<id>/questions ─────────────────────────────────

@api_bp.route("/forms/<form_id>/questions", methods=["POST"])
def add_question(form_id: str):
    """Add a question to a form.

    Expects JSON body::

        {
            "question_text": "How satisfied are you?",
            "question_type": "rating",
            "options": ["A", "B", "C"],   // required for multiple_choice/checkbox
            "order": 1                     // optional, defaults to next
        }
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if form.is_published:
        return jsonify({"error": "Cannot add questions to a published form"}), 409

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    error = _validate_question_data(data)
    if error:
        return jsonify({"error": error}), 400

    # Default order: append after the last question.
    order = data.get("order")
    if order is None:
        last = (
            Question.query
            .filter_by(form_id=form_id)
            .order_by(Question.order.desc())
            .first()
        )
        order = (last.order + 1) if last else 1

    question = Question(
        form_id=form_id,
        question_text=data["question_text"].strip(),
        question_type=data.get("question_type", "text"),
        order=int(order),
    )

    # Set options for choice-based types.
    options = data.get("options")
    if options and isinstance(options, list):
        question.set_options(options)

    db.session.add(question)
    db.session.commit()

    return jsonify(_serialize_question(question)), 201


# ── PUT /api/forms/<id>/questions/<qid> ────────────────────────────

@api_bp.route("/forms/<form_id>/questions/<int:question_id>", methods=["PUT"])
def update_question(form_id: str, question_id: int):
    """Update a question's text, type, options, or order."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if form.is_published:
        return jsonify({"error": "Cannot update questions on a published form"}), 409

    question = db.session.get(Question, question_id)
    if question is None or question.form_id != form_id:
        return jsonify({"error": "Question not found in this form"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Build a merged payload for validation: current values + incoming changes.
    # This ensures that partial updates are validated in context — e.g. if
    # the type changes to "multiple_choice" but no options are provided,
    # the existing options (if any) are checked.  Without merging, a PATCH-
    # style update could leave the question in an invalid state.
    merged = {
        "question_text": data.get("question_text", question.question_text),
        "question_type": data.get("question_type", question.question_type),
        "options": data.get("options", question.get_options()),
    }
    error = _validate_question_data(merged)
    if error:
        return jsonify({"error": error}), 400

    if "question_text" in data:
        question.question_text = data["question_text"].strip()

    if "question_type" in data:
        question.question_type = data["question_type"]

    if "options" in data:
        if data["options"] and isinstance(data["options"], list):
            question.set_options(data["options"])
        else:
            question.options = None

    if "order" in data:
        question.order = int(data["order"])

    db.session.commit()
    return jsonify(_serialize_question(question))


# ── DELETE /api/forms/<id>/questions/<qid> ─────────────────────────

@api_bp.route("/forms/<form_id>/questions/<int:question_id>", methods=["DELETE"])
def delete_question(form_id: str, question_id: int):
    """Delete a question from a form."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if form.is_published:
        return jsonify({"error": "Cannot delete questions from a published form"}), 409

    question = db.session.get(Question, question_id)
    if question is None or question.form_id != form_id:
        return jsonify({"error": "Question not found in this form"}), 404

    db.session.delete(question)
    db.session.commit()

    return jsonify({"message": "Question deleted successfully"}), 200
