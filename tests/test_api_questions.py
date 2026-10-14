"""Tests for the questions API endpoints."""

import uuid

import pytest

from app.models import Form, Question, User


def _setup_form(db, published=False):
    """Helper: create an owner and a form, return (owner, form)."""
    owner = User(name="Owner", email="owner@test.com", role="owner")
    db.session.add(owner)
    db.session.flush()
    form = Form(title="Test Form", owner_id=owner.id, is_published=published)
    db.session.add(form)
    db.session.commit()
    return owner, form


class TestAddQuestion:
    """POST /api/forms/<id>/questions"""

    def test_add_text_question(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "What do you think?",
            "question_type": "text",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["question_text"] == "What do you think?"
        assert data["question_type"] == "text"
        assert data["order"] == 1

    def test_add_multiple_choice_question(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Pick one",
            "question_type": "multiple_choice",
            "options": ["A", "B", "C"],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["options"] == ["A", "B", "C"]

    def test_add_question_auto_order(self, client, db):
        _, form = _setup_form(db)
        client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Q1", "question_type": "text",
        })
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Q2", "question_type": "text",
        })
        assert resp.status_code == 201
        assert resp.get_json()["order"] == 2

    def test_add_question_missing_text(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_type": "text",
        })
        assert resp.status_code == 400

    def test_add_question_invalid_type(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Q",
            "question_type": "invalid_type",
        })
        assert resp.status_code == 400

    def test_add_question_mc_without_options(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Pick",
            "question_type": "multiple_choice",
        })
        assert resp.status_code == 400

    def test_add_question_mc_too_few_options(self, client, db):
        _, form = _setup_form(db)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Pick",
            "question_type": "multiple_choice",
            "options": ["Only one"],
        })
        assert resp.status_code == 400

    def test_add_question_to_published_form(self, client, db):
        _, form = _setup_form(db, published=True)
        resp = client.post(f"/api/forms/{form.id}/questions", json={
            "question_text": "Q", "question_type": "text",
        })
        assert resp.status_code == 409

    def test_add_question_form_not_found(self, client, db):
        resp = client.post(f"/api/forms/{uuid.uuid4()}/questions", json={
            "question_text": "Q", "question_type": "text",
        })
        assert resp.status_code == 404


class TestUpdateQuestion:
    """PUT /api/forms/<id>/questions/<qid>"""

    def test_update_question_text(self, client, db):
        _, form = _setup_form(db)
        q = Question(form_id=form.id, question_text="Old", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()

        resp = client.put(
            f"/api/forms/{form.id}/questions/{q.id}",
            json={"question_text": "New"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["question_text"] == "New"

    def test_update_question_type_and_options(self, client, db):
        _, form = _setup_form(db)
        q = Question(form_id=form.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()

        resp = client.put(
            f"/api/forms/{form.id}/questions/{q.id}",
            json={
                "question_type": "multiple_choice",
                "options": ["X", "Y"],
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["question_type"] == "multiple_choice"
        assert data["options"] == ["X", "Y"]

    def test_update_question_on_published_form(self, client, db):
        _, form = _setup_form(db, published=True)
        q = Question(form_id=form.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()

        resp = client.put(
            f"/api/forms/{form.id}/questions/{q.id}",
            json={"question_text": "Changed"},
        )
        assert resp.status_code == 409

    def test_update_question_not_found(self, client, db):
        _, form = _setup_form(db)
        resp = client.put(
            f"/api/forms/{form.id}/questions/999",
            json={"question_text": "X"},
        )
        assert resp.status_code == 404

    def test_update_question_wrong_form(self, client, db):
        _, form1 = _setup_form(db)
        owner2 = User(name="O2", email="o2@test.com", role="owner")
        db.session.add(owner2)
        db.session.flush()
        form2 = Form(title="Form2", owner_id=owner2.id)
        db.session.add(form2)
        db.session.flush()
        q = Question(form_id=form2.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()

        resp = client.put(
            f"/api/forms/{form1.id}/questions/{q.id}",
            json={"question_text": "X"},
        )
        assert resp.status_code == 404


class TestDeleteQuestion:
    """DELETE /api/forms/<id>/questions/<qid>"""

    def test_delete_question_success(self, client, db):
        _, form = _setup_form(db)
        q = Question(form_id=form.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()
        qid = q.id

        resp = client.delete(f"/api/forms/{form.id}/questions/{qid}")
        assert resp.status_code == 200
        assert Question.query.get(qid) is None

    def test_delete_question_published_form(self, client, db):
        _, form = _setup_form(db, published=True)
        q = Question(form_id=form.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.commit()

        resp = client.delete(f"/api/forms/{form.id}/questions/{q.id}")
        assert resp.status_code == 409

    def test_delete_question_not_found(self, client, db):
        _, form = _setup_form(db)
        resp = client.delete(f"/api/forms/{form.id}/questions/999")
        assert resp.status_code == 404
