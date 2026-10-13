"""Tests for the dashboard API endpoint."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Form, Question, Response, Reward, User


class TestDashboard:
    """GET /api/dashboard"""

    def test_dashboard_empty(self, client, db):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_forms"] == 0
        assert data["published_forms"] == 0
        assert data["draft_forms"] == 0
        assert data["total_responses"] == 0
        assert data["total_employees"] == 0
        assert data["forms"] == []

    def test_dashboard_with_data(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        emp1 = User(name="Emp1", email="emp1@test.com", role="employee")
        emp2 = User(name="Emp2", email="emp2@test.com", role="employee")
        db.session.add_all([owner, emp1, emp2])
        db.session.flush()

        # Published form with responses
        form1 = Form(title="Published", owner_id=owner.id, is_published=True)
        db.session.add(form1)
        db.session.flush()

        q = Question(
            form_id=form1.id, question_text="Q",
            question_type="text", order=1,
        )
        db.session.add(q)
        db.session.flush()

        now = datetime.now(timezone.utc)
        r1 = Response(
            form_id=form1.id, respondent_id=emp1.id,
            submitted_at=now - timedelta(hours=2),
        )
        r2 = Response(
            form_id=form1.id, respondent_id=emp2.id,
            submitted_at=now - timedelta(hours=1),
        )
        db.session.add_all([r1, r2])
        db.session.flush()

        # Add rewards
        db.session.add(Reward(
            form_id=form1.id, user_id=emp1.id,
            rank=1, reward_points=100.0,
        ))
        db.session.add(Reward(
            form_id=form1.id, user_id=emp2.id,
            rank=2, reward_points=10.0,
        ))

        # Draft form
        form2 = Form(title="Draft", owner_id=owner.id, is_published=False)
        db.session.add(form2)
        db.session.commit()

        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_forms"] == 2
        assert data["published_forms"] == 1
        assert data["draft_forms"] == 1
        assert data["total_responses"] == 2
        assert data["total_employees"] == 2

        # Find the published form stats
        pub = next(f for f in data["forms"] if f["is_published"])
        assert pub["response_count"] == 2
        assert pub["response_rate"] == 100.0
        assert pub["rewards_calculated"] is True
        assert pub["reward_distribution"]["max_points"] == 100.0
        assert pub["reward_distribution"]["min_points"] == 10.0
        assert pub["reward_distribution"]["avg_points"] == 55.0

        # Draft form
        draft = next(f for f in data["forms"] if not f["is_published"])
        assert draft["response_count"] == 0
        assert draft["rewards_calculated"] is False
        assert draft["reward_distribution"] is None

    def test_dashboard_response_rate_calculation(self, client, db):
        """Response rate = responses / total employees × 100."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()

        # 4 employees, 1 response → 25%
        for i in range(1, 5):
            db.session.add(User(
                name=f"Emp{i}", email=f"emp{i}@test.com", role="employee",
            ))
        db.session.flush()

        form = Form(title="Rate Test", owner_id=owner.id, is_published=True)
        db.session.add(form)
        db.session.flush()

        emp1 = User.query.filter_by(email="emp1@test.com").first()
        db.session.add(Response(
            form_id=form.id, respondent_id=emp1.id,
        ))
        db.session.commit()

        resp = client.get("/api/dashboard")
        data = resp.get_json()
        form_data = data["forms"][0]
        assert form_data["response_rate"] == 25.0
