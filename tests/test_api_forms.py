"""Tests for the forms API endpoints."""

import json
import uuid

import pytest

from app.models import Form, Question, User


class TestCreateForm:
    """POST /api/forms"""

    def test_create_form_success(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Test Form",
            "description": "A test form",
            "owner_id": owner.id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == "Test Form"
        assert data["description"] == "A test form"
        assert data["owner_id"] == owner.id
        assert data["is_published"] is False
        # id is a valid UUID
        uuid.UUID(data["id"], version=4)

    def test_create_form_with_closes_at(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Timed Form",
            "owner_id": owner.id,
            "closes_at": "2026-12-31T23:59:59+00:00",
        })
        assert resp.status_code == 201
        assert resp.get_json()["closes_at"] is not None

    def test_create_form_missing_title(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        resp = client.post("/api/forms", json={"owner_id": owner.id})
        assert resp.status_code == 400
        assert "title" in resp.get_json()["error"]

    def test_create_form_missing_owner(self, client, db):
        resp = client.post("/api/forms", json={"title": "No Owner"})
        assert resp.status_code == 400
        assert "owner_id" in resp.get_json()["error"]

    def test_create_form_nonexistent_owner(self, client, db):
        resp = client.post("/api/forms", json={
            "title": "Bad Owner",
            "owner_id": 999,
        })
        assert resp.status_code == 404

    def test_create_form_employee_cannot_create(self, client, db):
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add(emp)
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Emp Form",
            "owner_id": emp.id,
        })
        assert resp.status_code == 403

    def test_create_form_invalid_json(self, client, db):
        resp = client.post("/api/forms", data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400

    def test_create_form_invalid_closes_at(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Bad Date",
            "owner_id": owner.id,
            "closes_at": "not-a-date",
        })
        assert resp.status_code == 400


class TestListForms:
    """GET /api/forms"""

    def test_list_forms_empty(self, client, db):
        resp = client.get("/api/forms")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_forms_returns_all(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        for i in range(3):
            db.session.add(Form(
                title=f"Form {i}", owner_id=owner.id,
            ))
        db.session.commit()

        resp = client.get("/api/forms")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3


class TestGetForm:
    """GET /api/forms/<id>"""

    def test_get_form_with_questions(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="My Form", owner_id=owner.id)
        db.session.add(form)
        db.session.flush()
        db.session.add(Question(
            form_id=form.id, question_text="Q1",
            question_type="text", order=1,
        ))
        db.session.commit()

        resp = client.get(f"/api/forms/{form.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["title"] == "My Form"
        assert len(data["questions"]) == 1
        assert data["questions"][0]["question_text"] == "Q1"

    def test_get_form_not_found(self, client, db):
        resp = client.get(f"/api/forms/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateForm:
    """PUT /api/forms/<id>"""

    def test_update_form_title(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Old Title", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()

        resp = client.put(f"/api/forms/{form.id}", json={
            "title": "New Title",
        })
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "New Title"

    def test_update_published_form_rejected(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Published", owner_id=owner.id, is_published=True)
        db.session.add(form)
        db.session.commit()

        resp = client.put(f"/api/forms/{form.id}", json={
            "title": "Changed",
        })
        assert resp.status_code == 409

    def test_update_form_not_found(self, client, db):
        resp = client.put(f"/api/forms/{uuid.uuid4()}", json={
            "title": "X",
        })
        assert resp.status_code == 404

    def test_update_form_empty_title(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Good", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()

        resp = client.put(f"/api/forms/{form.id}", json={"title": ""})
        assert resp.status_code == 400


class TestPublishForm:
    """POST /api/forms/<id>/publish"""

    def test_publish_form_success(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.flush()
        form = Form(title="To Publish", owner_id=owner.id)
        db.session.add(form)
        db.session.flush()
        db.session.add(Question(
            form_id=form.id, question_text="Q1",
            question_type="text", order=1,
        ))
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["form"]["is_published"] is True
        assert data["notifications_queued"] == 1
        assert data["notified_employees"][0]["email"] == "emp@test.com"

    def test_publish_already_published(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Already", owner_id=owner.id, is_published=True)
        db.session.add(form)
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 409

    def test_publish_form_no_questions(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Empty", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 400

    def test_publish_form_not_found(self, client, db):
        resp = client.post(f"/api/forms/{uuid.uuid4()}/publish")
        assert resp.status_code == 404


class TestDeleteForm:
    """DELETE /api/forms/<id>"""

    def test_delete_form_success(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="To Delete", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()
        form_id = form.id

        resp = client.delete(f"/api/forms/{form_id}")
        assert resp.status_code == 200
        assert Form.query.get(form_id) is None

    def test_delete_form_not_found(self, client, db):
        resp = client.delete(f"/api/forms/{uuid.uuid4()}")
        assert resp.status_code == 404
