"""Tests for the SQLAlchemy models.

Covers creation, relationships, constraints, and the reward ranking logic.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Answer, Form, Question, Response, Reward, User


# ── helpers ────────────────────────────────────────────────────────

def _make_owner(db):
    u = User(name="Owner", email="owner@test.com", role="owner")
    db.session.add(u)
    db.session.flush()
    return u


def _make_employee(db, n=1):
    u = User(name=f"Emp{n}", email=f"emp{n}@test.com", role="employee")
    db.session.add(u)
    db.session.flush()
    return u


def _make_form(db, owner, **kw):
    defaults = dict(
        id=str(uuid.uuid4()),
        title="Test Form",
        owner_id=owner.id,
    )
    defaults.update(kw)
    f = Form(**defaults)
    db.session.add(f)
    db.session.flush()
    return f


# ── User ───────────────────────────────────────────────────────────

class TestUser:
    def test_create_user(self, db):
        u = User(name="Alice", email="alice@test.com", role="owner")
        db.session.add(u)
        db.session.commit()

        assert u.id is not None
        assert u.role == "owner"
        assert u.created_at is not None

    def test_email_unique(self, db):
        db.session.add(User(name="A", email="dup@test.com", role="employee"))
        db.session.commit()
        db.session.add(User(name="B", email="dup@test.com", role="employee"))
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()

    def test_default_role(self, db):
        u = User(name="Default", email="def@test.com")
        db.session.add(u)
        db.session.commit()
        assert u.role == "employee"


# ── Form ───────────────────────────────────────────────────────────

class TestForm:
    def test_create_form_with_uuid(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        db.session.commit()

        # id is a valid UUID-4 string
        parsed = uuid.UUID(f.id, version=4)
        assert str(parsed) == f.id

    def test_form_owner_relationship(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        db.session.commit()

        assert f.owner.id == owner.id
        assert f in owner.owned_forms.all()

    def test_is_published_default_false(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        db.session.commit()
        assert f.is_published is False


# ── Question ───────────────────────────────────────────────────────

class TestQuestion:
    def test_question_types(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        for qt in Question.ALLOWED_TYPES:
            q = Question(form_id=f.id, question_text=f"Q {qt}", question_type=qt, order=0)
            db.session.add(q)
        db.session.commit()
        assert f.questions.count() == 4

    def test_options_json_helpers(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        q = Question(form_id=f.id, question_text="Pick one", question_type="multiple_choice", order=1)
        q.set_options(["A", "B", "C"])
        db.session.add(q)
        db.session.commit()

        fetched = Question.query.get(q.id)
        assert fetched.get_options() == ["A", "B", "C"]

    def test_ordering(self, db):
        owner = _make_owner(db)
        f = _make_form(db, owner)
        for i in [3, 1, 2]:
            db.session.add(Question(form_id=f.id, question_text=f"Q{i}", question_type="text", order=i))
        db.session.commit()

        orders = [q.order for q in f.questions.all()]
        assert orders == [1, 2, 3]


# ── Response & Answer ──────────────────────────────────────────────

class TestResponseAnswer:
    def test_response_with_answers(self, db):
        owner = _make_owner(db)
        emp = _make_employee(db)
        f = _make_form(db, owner)
        q = Question(form_id=f.id, question_text="Rate us", question_type="rating", order=1)
        db.session.add(q)
        db.session.flush()

        r = Response(form_id=f.id, respondent_id=emp.id)
        db.session.add(r)
        db.session.flush()

        a = Answer(response_id=r.id, question_id=q.id, answer_value="5")
        db.session.add(a)
        db.session.commit()

        assert r.answers[0].answer_value == "5"
        assert r.respondent.email == "emp1@test.com"

    def test_one_response_per_user_per_form(self, db):
        owner = _make_owner(db)
        emp = _make_employee(db)
        f = _make_form(db, owner)

        db.session.add(Response(form_id=f.id, respondent_id=emp.id))
        db.session.commit()

        db.session.add(Response(form_id=f.id, respondent_id=emp.id))
        with pytest.raises(Exception):
            db.session.commit()

    def test_cascade_delete_form_removes_responses(self, db):
        owner = _make_owner(db)
        emp = _make_employee(db)
        f = _make_form(db, owner)
        q = Question(form_id=f.id, question_text="Q", question_type="text", order=1)
        db.session.add(q)
        db.session.flush()
        r = Response(form_id=f.id, respondent_id=emp.id)
        db.session.add(r)
        db.session.flush()
        db.session.add(Answer(response_id=r.id, question_id=q.id, answer_value="x"))
        db.session.commit()

        db.session.delete(f)
        db.session.commit()

        assert Response.query.count() == 0
        assert Answer.query.count() == 0
        assert Question.query.count() == 0


# ── Reward ─────────────────────────────────────────────────────────

class TestReward:
    def test_reward_linear_scaling(self, db):
        """First submitter gets max, last gets min, middle is interpolated."""
        owner = _make_owner(db)
        f = _make_form(db, owner)
        now = datetime.now(timezone.utc)

        max_pts, min_pts = 100.0, 10.0
        employees = [_make_employee(db, n=i) for i in range(1, 6)]

        # Create responses with staggered times
        responses = []
        for i, emp in enumerate(employees):
            r = Response(
                form_id=f.id,
                respondent_id=emp.id,
                submitted_at=now + timedelta(hours=i),
            )
            db.session.add(r)
            responses.append(r)
        db.session.flush()

        # Calculate rewards
        total = len(responses)
        for rank, resp in enumerate(responses, start=1):
            if total == 1:
                pts = max_pts
            else:
                pts = max_pts - (max_pts - min_pts) * (rank - 1) / (total - 1)
            db.session.add(Reward(
                form_id=f.id,
                user_id=resp.respondent_id,
                rank=rank,
                reward_points=round(pts, 2),
            ))
        db.session.commit()

        rewards = Reward.query.filter_by(form_id=f.id).order_by(Reward.rank).all()
        assert len(rewards) == 5
        assert rewards[0].reward_points == 100.0   # first
        assert rewards[-1].reward_points == 10.0    # last
        # Middle should be between min and max
        assert min_pts < rewards[2].reward_points < max_pts

    def test_one_reward_per_user_per_form(self, db):
        owner = _make_owner(db)
        emp = _make_employee(db)
        f = _make_form(db, owner)

        db.session.add(Reward(form_id=f.id, user_id=emp.id, rank=1, reward_points=100))
        db.session.commit()

        db.session.add(Reward(form_id=f.id, user_id=emp.id, rank=1, reward_points=100))
        with pytest.raises(Exception):
            db.session.commit()
