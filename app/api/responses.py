"""Response submission and listing endpoints.

Routes
------
POST /api/forms/<id>/responses  — submit a response with answers
GET  /api/forms/<id>/responses  — list all responses for a form (owner view)
"""

from flask import jsonify, request

from app import db
from app.api import api_bp
from app.models import Answer, Form, Question, Response, User


def _serialize_response(resp: Response, include_answers: bool = False) -> dict:
    """Convert a Response model to a JSON-safe dict."""
    data = {
        "id": resp.id,
        "form_id": resp.form_id,
        "respondent_id": resp.respondent_id,
        "respondent_name": resp.respondent.name if resp.respondent else None,
        "respondent_email": resp.respondent.email if resp.respondent else None,
        "submitted_at": resp.submitted_at.isoformat() if resp.submitted_at else None,
    }
    if include_answers:
        data["answers"] = [
            {
                "id": a.id,
                "question_id": a.question_id,
                "question_text": a.question.question_text if a.question else None,
                "answer_value": a.answer_value,
            }
            for a in resp.answers
        ]
    return data


# ── POST /api/forms/<id>/responses ─────────────────────────────────

@api_bp.route("/forms/<form_id>/responses", methods=["POST"])
def submit_response(form_id: str):
    """Submit a response to a form.

    Expects JSON body::

        {
            "respondent_id": 2,
            "answers": [
                {"question_id": 1, "answer_value": "5"},
                {"question_id": 2, "answer_value": "Remote work"}
            ]
        }

    Validates:
    - Form exists and is published.
    - Form has not closed (if closes_at is set).
    - Respondent exists and has role 'employee'.
    - Each answer references a valid question in this form.
    - All questions in the form are answered.
    - Respondent has not already submitted for this form.
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    if not form.is_published:
        return jsonify({"error": "Form is not published yet"}), 400

    # Check deadline.  SQLite stores datetimes as strings and may return
    # a naive (tzinfo=None) datetime object even when the column was
    # declared with timezone=True.  We normalise to UTC-aware before
    # comparing so the check works identically on SQLite and PostgreSQL.
    if form.closes_at:
        from datetime import datetime, timezone

        closes = form.closes_at
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > closes:
            return jsonify({"error": "Form has closed and is no longer accepting responses"}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    respondent_id = data.get("respondent_id")
    if respondent_id is None:
        return jsonify({"error": "respondent_id is required"}), 400

    respondent = db.session.get(User, respondent_id)
    if respondent is None:
        return jsonify({"error": f"User {respondent_id} not found"}), 404
    if respondent.role != "employee":
        return jsonify({"error": "Only employees can submit responses"}), 403

    # Check for duplicate submission.
    existing = Response.query.filter_by(
        form_id=form_id, respondent_id=respondent_id
    ).first()
    if existing:
        return jsonify({"error": "You have already submitted a response for this form"}), 409

    # Validate answers.
    answers_data = data.get("answers")
    if not answers_data or not isinstance(answers_data, list):
        return jsonify({"error": "answers must be a non-empty list"}), 400

    # Build a set of valid question IDs for this form.  This is used to
    # validate that (a) every answer references a real question in THIS
    # form, (b) no extra questions from other forms sneak in, and (c) all
    # questions are answered (by comparing against submitted_question_ids).
    form_question_ids = {
        q.id for q in Question.query.filter_by(form_id=form_id).all()
    }

    if not form_question_ids:
        return jsonify({"error": "Form has no questions"}), 400

    # Check that every answer references a valid question.
    submitted_question_ids = set()
    for ans in answers_data:
        qid = ans.get("question_id")
        if qid is None:
            return jsonify({"error": "Each answer must have a question_id"}), 400
        if qid not in form_question_ids:
            return jsonify({"error": f"Question {qid} does not belong to this form"}), 400
        value = ans.get("answer_value")
        if value is None or (isinstance(value, str) and not value.strip()):
            return jsonify({"error": f"answer_value is required for question {qid}"}), 400
        if qid in submitted_question_ids:
            return jsonify({"error": f"Duplicate answer for question {qid}"}), 400
        submitted_question_ids.add(qid)

    # Check all questions are answered.
    missing = form_question_ids - submitted_question_ids
    if missing:
        return jsonify({
            "error": "All questions must be answered",
            "missing_question_ids": sorted(missing),
        }), 400

    # Create the response and answers.  We flush() after adding the
    # response so SQLAlchemy populates response.id (auto-increment PK),
    # which we need as the FK for each Answer row.  The final commit()
    # happens after all answers are added, making the whole submission
    # atomic — if any answer fails, nothing is persisted.
    response = Response(form_id=form_id, respondent_id=respondent_id)
    db.session.add(response)
    db.session.flush()  # populate response.id for Answer FK

    for ans in answers_data:
        answer = Answer(
            response_id=response.id,
            question_id=ans["question_id"],
            answer_value=str(ans["answer_value"]).strip(),
        )
        db.session.add(answer)

    db.session.commit()

    return jsonify(_serialize_response(response, include_answers=True)), 201


# ── GET /api/forms/<id>/responses ──────────────────────────────────

@api_bp.route("/forms/<form_id>/responses", methods=["GET"])
def list_responses(form_id: str):
    """List all responses for a form, ordered by submission time.

    Query params:
    - include_answers=true  — include each response's answers (default: false)
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    include_answers = request.args.get("include_answers", "false").lower() == "true"

    responses = (
        Response.query
        .filter_by(form_id=form_id)
        .order_by(Response.submitted_at.asc())
        .all()
    )

    return jsonify({
        "form_id": form_id,
        "form_title": form.title,
        "total_responses": len(responses),
        "responses": [
            _serialize_response(r, include_answers=include_answers)
            for r in responses
        ],
    })
