"""Tests for the responses API endpoints."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Form, Question, Response, User


def _setup_published_form(db):
    """Helper: create owner, employee, published form with one question."""
    owner = User(name="Owner", email="owner@test.com", role="owner")
    emp = User(name="Emp", email="emp@test.com", role="employee")
    db.session.add_all([owner, emp])
    db.session.flush()
    form = Form(title="Survey", owner_id=owner.id, is_published=True)
    db.session.add(form)
    db.session.flush()
    q = Question(
        form_id=form.id, question_text="Rate us",
        question_type="rating", order=1,
    )
    db.session.add(q)
    db.session.commit()
    return owner, emp, form, q


class TestSubmitResponse:
    """POST /api/forms/<id>/responses"""

    def test_submit_response_success(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [
                {"question_id": q.id, "answer_value": "5"},
            ],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["respondent_id"] == emp.id
        assert data["form_id"] == form.id
        assert len(data["answers"]) == 1
        assert data["answers"][0]["answer_value"] == "5"

    def test_submit_response_unpublished_form(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.flush()
        form = Form(title="Draft", owner_id=owner.id, is_published=False)
        db.session.add(form)
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [],
        })
        assert resp.status_code == 400

    def test_submit_response_closed_form(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.flush()
        form = Form(
            title="Closed", owner_id=owner.id, is_published=True,
            closes_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.session.add(form)
        db.session.flush()
        q = Question(
            form_id=form.id, question_text="Q",
            question_type="text", order=1,
        )
        db.session.add(q)
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "x"}],
        })
        assert resp.status_code == 400
        assert "closed" in resp.get_json()["error"].lower()

    def test_submit_response_duplicate(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        # First submission
        client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })
        # Second submission
        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "4"}],
        })
        assert resp.status_code == 409

    def test_submit_response_owner_cannot_submit(self, client, db):
        owner, _, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": owner.id,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })
        assert resp.status_code == 403

    def test_submit_response_missing_answers(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
        })
        assert resp.status_code == 400

    def test_submit_response_wrong_question_id(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": 9999, "answer_value": "5"}],
        })
        assert resp.status_code == 400

    def test_submit_response_missing_question(self, client, db):
        """All questions must be answered."""
        owner, emp, form, q = _setup_published_form(db)
        # Add a second question
        q2 = Question(
            form_id=form.id, question_text="Q2",
            question_type="text", order=2,
        )
        db.session.add(q2)
        db.session.commit()

        # Only answer one of two questions
        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })
        assert resp.status_code == 400
        assert "missing_question_ids" in resp.get_json()

    def test_submit_response_duplicate_answer(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [
                {"question_id": q.id, "answer_value": "5"},
                {"question_id": q.id, "answer_value": "4"},
            ],
        })
        assert resp.status_code == 400

    def test_submit_response_empty_answer_value(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": ""}],
        })
        assert resp.status_code == 400

    def test_submit_response_form_not_found(self, client, db):
        resp = client.post(f"/api/forms/{uuid.uuid4()}/responses", json={
            "respondent_id": 1,
            "answers": [],
        })
        assert resp.status_code == 404

    def test_submit_response_user_not_found(self, client, db):
        owner, _, form, q = _setup_published_form(db)

        resp = client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": 9999,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })
        assert resp.status_code == 404


class TestListResponses:
    """GET /api/forms/<id>/responses"""

    def test_list_responses_empty(self, client, db):
        owner, _, form, _ = _setup_published_form(db)

        resp = client.get(f"/api/forms/{form.id}/responses")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_responses"] == 0
        assert data["responses"] == []

    def test_list_responses_with_data(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })

        resp = client.get(f"/api/forms/{form.id}/responses")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_responses"] == 1
        # By default, answers are not included
        assert "answers" not in data["responses"][0]

    def test_list_responses_include_answers(self, client, db):
        owner, emp, form, q = _setup_published_form(db)

        client.post(f"/api/forms/{form.id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q.id, "answer_value": "5"}],
        })

        resp = client.get(
            f"/api/forms/{form.id}/responses?include_answers=true"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "answers" in data["responses"][0]
        assert len(data["responses"][0]["answers"]) == 1

    def test_list_responses_form_not_found(self, client, db):
        resp = client.get(f"/api/forms/{uuid.uuid4()}/responses")
        assert resp.status_code == 404
