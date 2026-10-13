"""Seed the database with sample data for development.

Usage
-----
    cd Feedback
    python -m seeds.seed

Idempotent: skips seeding if users already exist.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import Answer, Form, Question, Response, Reward, User


def seed() -> None:
    app = create_app("development")

    with app.app_context():
        # Skip if data already present
        if User.query.first() is not None:
            print("Database already seeded — skipping.")
            return

        now = datetime.now(timezone.utc)

        # ── Users ──────────────────────────────────────────────
        owner = User(name="Alice Owner", email="alice@example.com", role="owner")
        emp1 = User(name="Bob Employee", email="bob@example.com", role="employee")
        emp2 = User(name="Carol Employee", email="carol@example.com", role="employee")
        emp3 = User(name="Dave Employee", email="dave@example.com", role="employee")
        db.session.add_all([owner, emp1, emp2, emp3])
        db.session.flush()  # populate ids

        # ── Form ───────────────────────────────────────────────
        form = Form(
            id=str(uuid.uuid4()),
            title="Q3 Employee Satisfaction Survey",
            description="Please share your feedback on the last quarter.",
            owner_id=owner.id,
            created_at=now - timedelta(days=7),
            closes_at=now + timedelta(days=7),
            is_published=True,
        )
        db.session.add(form)
        db.session.flush()

        # ── Questions ──────────────────────────────────────────
        q1 = Question(
            form_id=form.id,
            question_text="How satisfied are you with your role?",
            question_type="rating",
            order=1,
        )
        q2 = Question(
            form_id=form.id,
            question_text="Which benefits do you value most?",
            question_type="multiple_choice",
            options=json.dumps(["Health insurance", "Remote work", "Gym membership", "Stock options"]),
            order=2,
        )
        q3 = Question(
            form_id=form.id,
            question_text="Any additional comments?",
            question_type="text",
            order=3,
        )
        q4 = Question(
            form_id=form.id,
            question_text="Select areas for improvement",
            question_type="checkbox",
            options=json.dumps(["Communication", "Work-life balance", "Career growth", "Compensation"]),
            order=4,
        )
        db.session.add_all([q1, q2, q3, q4])
        db.session.flush()

        # ── Responses (staggered times for reward ranking) ─────
        r1 = Response(
            form_id=form.id,
            respondent_id=emp1.id,
            submitted_at=now - timedelta(days=5),
        )
        r2 = Response(
            form_id=form.id,
            respondent_id=emp2.id,
            submitted_at=now - timedelta(days=3),
        )
        r3 = Response(
            form_id=form.id,
            respondent_id=emp3.id,
            submitted_at=now - timedelta(days=1),
        )
        db.session.add_all([r1, r2, r3])
        db.session.flush()

        # ── Answers ────────────────────────────────────────────
        answers = [
            Answer(response_id=r1.id, question_id=q1.id, answer_value="5"),
            Answer(response_id=r1.id, question_id=q2.id, answer_value="Remote work"),
            Answer(response_id=r1.id, question_id=q3.id, answer_value="Great workplace!"),
            Answer(response_id=r1.id, question_id=q4.id, answer_value=json.dumps(["Communication"])),
            Answer(response_id=r2.id, question_id=q1.id, answer_value="4"),
            Answer(response_id=r2.id, question_id=q2.id, answer_value="Health insurance"),
            Answer(response_id=r2.id, question_id=q3.id, answer_value="Could improve communication."),
            Answer(response_id=r2.id, question_id=q4.id, answer_value=json.dumps(["Communication", "Career growth"])),
            Answer(response_id=r3.id, question_id=q1.id, answer_value="3"),
            Answer(response_id=r3.id, question_id=q2.id, answer_value="Stock options"),
            Answer(response_id=r3.id, question_id=q3.id, answer_value="Need more growth opportunities."),
            Answer(response_id=r3.id, question_id=q4.id, answer_value=json.dumps(["Career growth", "Compensation"])),
        ]
        db.session.add_all(answers)

        # ── Rewards (first = max, last = min, linear scale) ────
        max_pts, min_pts = 100.0, 10.0
        total = 3
        for rank, resp in enumerate([r1, r2, r3], start=1):
            if total == 1:
                pts = max_pts
            else:
                pts = max_pts - (max_pts - min_pts) * (rank - 1) / (total - 1)
            reward = Reward(
                form_id=form.id,
                user_id=resp.respondent_id,
                rank=rank,
                reward_points=round(pts, 2),
                calculated_at=now,
            )
            db.session.add(reward)

        db.session.commit()
        print("Seed data inserted successfully.")
        print(f"  Users:     {User.query.count()}")
        print(f"  Forms:     {Form.query.count()}")
        print(f"  Questions: {Question.query.count()}")
        print(f"  Responses: {Response.query.count()}")
        print(f"  Answers:   {Answer.query.count()}")
        print(f"  Rewards:   {Reward.query.count()}")


if __name__ == "__main__":
    seed()
