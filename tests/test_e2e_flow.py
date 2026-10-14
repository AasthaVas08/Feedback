"""End-to-end test for the full feedback form lifecycle.

Flow: create form → add questions → publish → submit responses in order
→ calculate rewards → verify leaderboard order → verify dashboard.

This test exercises the entire stack through the API, simulating a
realistic usage scenario with multiple employees responding at
different times.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models import Form, Notification, Question, Response, Reward, User


class TestFullE2EFlow:
    """Complete lifecycle: create → publish → respond → rewards → dashboard."""

    @patch("app.services.email_service.threading.Thread")
    def test_complete_lifecycle(self, mock_thread, client, db):
        """Walk through the entire form lifecycle via the API."""

        # ── Step 1: Create owner and employees ─────────────────────
        owner = User(name="Manager", email="manager@company.com", role="owner")
        employees = []
        for i in range(1, 6):
            emp = User(
                name=f"Employee {i}",
                email=f"emp{i}@company.com",
                role="employee",
            )
            employees.append(emp)
        db.session.add(owner)
        db.session.add_all(employees)
        db.session.commit()

        # ── Step 2: Create a form via API ──────────────────────────
        resp = client.post("/api/forms", json={
            "title": "Q4 Employee Satisfaction Survey",
            "description": "Annual satisfaction survey for Q4 2026",
            "owner_id": owner.id,
            "closes_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        })
        assert resp.status_code == 201
        form_data = resp.get_json()
        form_id = form_data["id"]
        assert form_data["is_published"] is False
        assert form_data["title"] == "Q4 Employee Satisfaction Survey"

        # ── Step 3: Add questions to the form ──────────────────────
        questions = [
            {
                "question_text": "How satisfied are you with your work environment?",
                "question_type": "rating",
            },
            {
                "question_text": "What is your preferred work arrangement?",
                "question_type": "multiple_choice",
                "options": ["Remote", "Hybrid", "On-site"],
            },
            {
                "question_text": "Any additional feedback?",
                "question_type": "text",
            },
        ]

        question_ids = []
        for i, q in enumerate(questions, start=1):
            resp = client.post(f"/api/forms/{form_id}/questions", json=q)
            assert resp.status_code == 201, f"Question {i} creation failed"
            q_data = resp.get_json()
            question_ids.append(q_data["id"])
            assert q_data["order"] == i

        # Verify form has 3 questions
        resp = client.get(f"/api/forms/{form_id}")
        assert resp.status_code == 200
        assert resp.get_json()["question_count"] == 3

        # ── Step 4: Publish the form ───────────────────────────────
        resp = client.post(f"/api/forms/{form_id}/publish")
        assert resp.status_code == 200
        publish_data = resp.get_json()
        assert publish_data["form"]["is_published"] is True
        assert publish_data["notifications_queued"] == 5  # 5 employees
        assert len(publish_data["notified_employees"]) == 5

        # Verify notification rows were created
        notifs = Notification.query.filter_by(form_id=form_id).all()
        assert len(notifs) == 5

        # Background thread was started for email sending
        mock_thread.assert_called_once()

        # ── Step 5: Submit responses in staggered order ────────────
        # Employee 1 submits first, Employee 5 submits last
        now = datetime.now(timezone.utc)
        for i, emp in enumerate(employees):
            resp = client.post(f"/api/forms/{form_id}/responses", json={
                "respondent_id": emp.id,
                "answers": [
                    {"question_id": question_ids[0], "answer_value": str(5 - i)},
                    {"question_id": question_ids[1], "answer_value": "Remote"},
                    {"question_id": question_ids[2], "answer_value": f"Feedback from emp {i+1}"},
                ],
            })
            assert resp.status_code == 201, (
                f"Employee {i+1} submission failed: {resp.get_json()}"
            )

        # Verify all 5 responses are recorded
        resp = client.get(f"/api/forms/{form_id}/responses")
        assert resp.status_code == 200
        responses_data = resp.get_json()
        assert responses_data["total_responses"] == 5

        # ── Step 6: Calculate rewards ──────────────────────────────
        resp = client.post(f"/api/forms/{form_id}/rewards/calculate")
        assert resp.status_code == 201
        rewards_data = resp.get_json()
        assert rewards_data["total_respondents"] == 5
        assert rewards_data["max_reward"] == 100.0
        assert rewards_data["min_reward"] == 10.0

        rewards = rewards_data["rewards"]
        assert len(rewards) == 5

        # First submitter gets max, last gets min
        assert rewards[0]["rank"] == 1
        assert rewards[0]["reward_points"] == 100.0
        assert rewards[0]["user_id"] == employees[0].id

        assert rewards[4]["rank"] == 5
        assert rewards[4]["reward_points"] == 10.0
        assert rewards[4]["user_id"] == employees[4].id

        # Points are strictly decreasing
        points = [r["reward_points"] for r in rewards]
        for i in range(len(points) - 1):
            assert points[i] > points[i + 1]

        # ── Step 7: Verify leaderboard ─────────────────────────────
        resp = client.get(f"/api/forms/{form_id}/rewards")
        assert resp.status_code == 200
        leaderboard = resp.get_json()
        assert leaderboard["total_respondents"] == 5
        assert len(leaderboard["leaderboard"]) == 5

        # Leaderboard is ordered by rank ascending
        ranks = [entry["rank"] for entry in leaderboard["leaderboard"]]
        assert ranks == [1, 2, 3, 4, 5]

        # First place has highest points
        assert leaderboard["leaderboard"][0]["reward_points"] == 100.0
        assert leaderboard["leaderboard"][0]["user_name"] == "Employee 1"

        # Last place has lowest points
        assert leaderboard["leaderboard"][4]["reward_points"] == 10.0
        assert leaderboard["leaderboard"][4]["user_name"] == "Employee 5"

        # ── Step 8: Verify dashboard ───────────────────────────────
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        dashboard = resp.get_json()

        assert dashboard["total_forms"] == 1
        assert dashboard["published_forms"] == 1
        assert dashboard["draft_forms"] == 0
        assert dashboard["total_responses"] == 5
        assert dashboard["total_employees"] == 5

        form_stats = dashboard["forms"][0]
        assert form_stats["id"] == form_id
        assert form_stats["response_count"] == 5
        assert form_stats["response_rate"] == 100.0
        assert form_stats["rewards_calculated"] is True
        assert form_stats["reward_distribution"]["max_points"] == 100.0
        assert form_stats["reward_distribution"]["min_points"] == 10.0

    @patch("app.services.email_service.threading.Thread")
    def test_duplicate_submission_rejected(self, mock_thread, client, db):
        """An employee cannot submit twice for the same form."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.commit()

        # Create and publish form
        resp = client.post("/api/forms", json={
            "title": "Survey", "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]

        client.post(f"/api/forms/{form_id}/questions", json={
            "question_text": "Q1", "question_type": "text",
        })
        q_id = Question.query.filter_by(form_id=form_id).first().id

        client.post(f"/api/forms/{form_id}/publish")

        # First submission succeeds
        resp = client.post(f"/api/forms/{form_id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q_id, "answer_value": "answer"}],
        })
        assert resp.status_code == 201

        # Second submission is rejected
        resp = client.post(f"/api/forms/{form_id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q_id, "answer_value": "different"}],
        })
        assert resp.status_code == 409

    @patch("app.services.email_service.threading.Thread")
    def test_reward_recalculation_is_idempotent(self, mock_thread, client, db):
        """Recalculating rewards replaces old ones, not duplicates."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp1 = User(name="Emp1", email="emp1@test.com", role="employee")
        emp2 = User(name="Emp2", email="emp2@test.com", role="employee")
        db.session.add_all([owner, emp1, emp2])
        db.session.commit()

        # Create, add question, publish
        resp = client.post("/api/forms", json={
            "title": "Survey", "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]
        client.post(f"/api/forms/{form_id}/questions", json={
            "question_text": "Q1", "question_type": "text",
        })
        q_id = Question.query.filter_by(form_id=form_id).first().id
        client.post(f"/api/forms/{form_id}/publish")

        # Submit responses
        for emp in [emp1, emp2]:
            client.post(f"/api/forms/{form_id}/responses", json={
                "respondent_id": emp.id,
                "answers": [{"question_id": q_id, "answer_value": "ok"}],
            })

        # Calculate rewards twice
        resp1 = client.post(f"/api/forms/{form_id}/rewards/calculate")
        assert resp1.status_code == 201

        resp2 = client.post(f"/api/forms/{form_id}/rewards/calculate")
        assert resp2.status_code == 201

        # Should still have exactly 2 rewards, not 4
        assert Reward.query.filter_by(form_id=form_id).count() == 2

    @patch("app.services.email_service.threading.Thread")
    def test_custom_reward_bounds_in_flow(self, mock_thread, client, db):
        """Custom max/min reward bounds are respected in the full flow."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp1 = User(name="Emp1", email="emp1@test.com", role="employee")
        emp2 = User(name="Emp2", email="emp2@test.com", role="employee")
        emp3 = User(name="Emp3", email="emp3@test.com", role="employee")
        db.session.add_all([owner, emp1, emp2, emp3])
        db.session.commit()

        # Create, add question, publish
        resp = client.post("/api/forms", json={
            "title": "Survey", "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]
        client.post(f"/api/forms/{form_id}/questions", json={
            "question_text": "Q1", "question_type": "text",
        })
        q_id = Question.query.filter_by(form_id=form_id).first().id
        client.post(f"/api/forms/{form_id}/publish")

        # Submit responses
        for emp in [emp1, emp2, emp3]:
            client.post(f"/api/forms/{form_id}/responses", json={
                "respondent_id": emp.id,
                "answers": [{"question_id": q_id, "answer_value": "ok"}],
            })

        # Calculate with custom bounds
        resp = client.post(f"/api/forms/{form_id}/rewards/calculate", json={
            "max_reward": 500,
            "min_reward": 100,
        })
        assert resp.status_code == 201
        rewards = resp.get_json()["rewards"]

        assert rewards[0]["reward_points"] == 500.0
        assert rewards[2]["reward_points"] == 100.0
        # Middle: 500 - 400 * 0.5 = 300
        assert rewards[1]["reward_points"] == 300.0

    @patch("app.services.email_service.threading.Thread")
    def test_responses_include_answers_in_listing(self, mock_thread, client, db):
        """GET /api/forms/<id>/responses?include_answers=true returns answer data."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Survey", "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]
        client.post(f"/api/forms/{form_id}/questions", json={
            "question_text": "Rate us", "question_type": "rating",
        })
        q_id = Question.query.filter_by(form_id=form_id).first().id
        client.post(f"/api/forms/{form_id}/publish")

        client.post(f"/api/forms/{form_id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q_id, "answer_value": "5"}],
        })

        resp = client.get(f"/api/forms/{form_id}/responses?include_answers=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_responses"] == 1
        assert len(data["responses"][0]["answers"]) == 1
        assert data["responses"][0]["answers"][0]["answer_value"] == "5"

    @patch("app.services.email_service.threading.Thread")
    def test_form_deletion_cascades_everything(self, mock_thread, client, db):
        """Deleting a form removes questions, responses, rewards, and notifications."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp = User(name="Emp", email="emp@test.com", role="employee")
        db.session.add_all([owner, emp])
        db.session.commit()

        # Create full lifecycle
        resp = client.post("/api/forms", json={
            "title": "To Delete", "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]
        client.post(f"/api/forms/{form_id}/questions", json={
            "question_text": "Q1", "question_type": "text",
        })
        q_id = Question.query.filter_by(form_id=form_id).first().id
        client.post(f"/api/forms/{form_id}/publish")

        client.post(f"/api/forms/{form_id}/responses", json={
            "respondent_id": emp.id,
            "answers": [{"question_id": q_id, "answer_value": "ok"}],
        })
        client.post(f"/api/forms/{form_id}/rewards/calculate")

        # Verify data exists
        assert Question.query.filter_by(form_id=form_id).count() > 0
        assert Response.query.filter_by(form_id=form_id).count() > 0
        assert Reward.query.filter_by(form_id=form_id).count() > 0
        assert Notification.query.filter_by(form_id=form_id).count() > 0

        # Delete the form
        resp = client.delete(f"/api/forms/{form_id}")
        assert resp.status_code == 200

        # Everything is gone
        assert Form.query.get(form_id) is None
        assert Question.query.filter_by(form_id=form_id).count() == 0
        assert Response.query.filter_by(form_id=form_id).count() == 0
        assert Reward.query.filter_by(form_id=form_id).count() == 0
        assert Notification.query.filter_by(form_id=form_id).count() == 0
