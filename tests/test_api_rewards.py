"""Tests for the rewards API endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Form, Question, Response, Reward, User


def _setup_form_with_responses(db, num_respondents=3):
    """Helper: create a form with staggered responses for reward testing."""
    owner = User(name="Owner", email="owner@test.com", role="owner")
    db.session.add(owner)
    db.session.flush()

    form = Form(title="Reward Test", owner_id=owner.id, is_published=True)
    db.session.add(form)
    db.session.flush()

    q = Question(
        form_id=form.id, question_text="Rate",
        question_type="rating", order=1,
    )
    db.session.add(q)
    db.session.flush()

    now = datetime.now(timezone.utc)
    employees = []
    for i in range(1, num_respondents + 1):
        emp = User(name=f"Emp{i}", email=f"emp{i}@test.com", role="employee")
        db.session.add(emp)
        db.session.flush()
        employees.append(emp)

        r = Response(
            form_id=form.id,
            respondent_id=emp.id,
            submitted_at=now + timedelta(hours=i),
        )
        db.session.add(r)

    db.session.commit()
    return owner, form, employees


class TestCalculateRewards:
    """POST /api/forms/<id>/rewards/calculate"""

    def test_calculate_rewards_default_bounds(self, client, db):
        _, form, employees = _setup_form_with_responses(db, 3)

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["total_respondents"] == 3
        assert data["max_reward"] == 100.0
        assert data["min_reward"] == 10.0

        rewards = data["rewards"]
        assert rewards[0]["rank"] == 1
        assert rewards[0]["reward_points"] == 100.0
        assert rewards[2]["rank"] == 3
        assert rewards[2]["reward_points"] == 10.0
        # Middle should be interpolated
        assert 10.0 < rewards[1]["reward_points"] < 100.0

    def test_calculate_rewards_custom_bounds(self, client, db):
        _, form, _ = _setup_form_with_responses(db, 2)

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate", json={
            "max_reward": 200,
            "min_reward": 50,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["rewards"][0]["reward_points"] == 200.0
        assert data["rewards"][1]["reward_points"] == 50.0

    def test_calculate_rewards_single_respondent(self, client, db):
        _, form, _ = _setup_form_with_responses(db, 1)

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["total_respondents"] == 1
        assert data["rewards"][0]["reward_points"] == 100.0

    def test_calculate_rewards_idempotent(self, client, db):
        """Recalculating replaces old rewards."""
        _, form, _ = _setup_form_with_responses(db, 3)

        client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert Reward.query.filter_by(form_id=form.id).count() == 3

        # Recalculate
        resp = client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert resp.status_code == 201
        assert Reward.query.filter_by(form_id=form.id).count() == 3

    def test_calculate_rewards_no_responses(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="Empty", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert resp.status_code == 400

    def test_calculate_rewards_invalid_bounds(self, client, db):
        _, form, _ = _setup_form_with_responses(db, 2)

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate", json={
            "max_reward": 10,
            "min_reward": 100,
        })
        assert resp.status_code == 400

    def test_calculate_rewards_form_not_found(self, client, db):
        resp = client.post(f"/api/forms/{uuid.uuid4()}/rewards/calculate")
        assert resp.status_code == 404

    def test_calculate_rewards_five_respondents(self, client, db):
        """Verify linear scaling with 5 respondents."""
        _, form, _ = _setup_form_with_responses(db, 5)

        resp = client.post(f"/api/forms/{form.id}/rewards/calculate")
        assert resp.status_code == 201
        rewards = resp.get_json()["rewards"]

        # Points should be strictly decreasing
        points = [r["reward_points"] for r in rewards]
        for i in range(len(points) - 1):
            assert points[i] > points[i + 1]

        # First = 100, last = 10
        assert points[0] == 100.0
        assert points[-1] == 10.0


class TestGetLeaderboard:
    """GET /api/forms/<id>/rewards"""

    def test_leaderboard_after_calculation(self, client, db):
        _, form, _ = _setup_form_with_responses(db, 3)
        client.post(f"/api/forms/{form.id}/rewards/calculate")

        resp = client.get(f"/api/forms/{form.id}/rewards")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_respondents"] == 3
        assert len(data["leaderboard"]) == 3
        assert data["leaderboard"][0]["rank"] == 1

    def test_leaderboard_no_rewards(self, client, db):
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.flush()
        form = Form(title="No Rewards", owner_id=owner.id)
        db.session.add(form)
        db.session.commit()

        resp = client.get(f"/api/forms/{form.id}/rewards")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["leaderboard"] == []

    def test_leaderboard_form_not_found(self, client, db):
        resp = client.get(f"/api/forms/{uuid.uuid4()}/rewards")
        assert resp.status_code == 404
