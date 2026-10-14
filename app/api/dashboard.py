"""Dashboard endpoint — aggregate statistics.

Routes
------
GET /api/dashboard — form count, response rates, reward distributions
"""

from flask import jsonify

from app import db
from app.api import api_bp
from app.models import Form, Response, Reward, User


@api_bp.route("/dashboard", methods=["GET"])
def dashboard():
    """Return aggregate statistics across all forms.

    Response shape::

        {
            "total_forms": 5,
            "published_forms": 3,
            "draft_forms": 2,
            "total_responses": 42,
            "total_employees": 10,
            "forms": [
                {
                    "id": "uuid",
                    "title": "Q3 Survey",
                    "is_published": true,
                    "response_count": 8,
                    "employee_count": 10,
                    "response_rate": 80.0,
                    "rewards_calculated": true,
                    "reward_distribution": {
                        "max_points": 100.0,
                        "min_points": 10.0,
                        "avg_points": 55.0,
                        "total_points": 440.0
                    }
                }
            ]
        }
    """
    total_employees = User.query.filter_by(role="employee").count()
    forms = Form.query.order_by(Form.created_at.desc()).all()

    total_responses = 0
    published_count = 0
    draft_count = 0
    form_stats = []

    for form in forms:
        response_count = form.responses.count()
        total_responses += response_count

        if form.is_published:
            published_count += 1
        else:
            draft_count += 1

        # Response rate: percentage of employees who responded.
        # Guard against division by zero when no employees exist.
        # The rate is calculated against ALL employees, not just those
        # who were notified — this gives a consistent denominator across
        # forms even if new employees joined after a form was published.
        response_rate = (
            round(response_count / total_employees * 100, 1)
            if total_employees > 0
            else 0.0
        )

        # Reward distribution for this form.
        rewards = Reward.query.filter_by(form_id=form.id).all()
        reward_distribution = None
        if rewards:
            points = [r.reward_points for r in rewards]
            reward_distribution = {
                "max_points": max(points),
                "min_points": min(points),
                "avg_points": round(sum(points) / len(points), 2),
                "total_points": round(sum(points), 2),
            }

        form_stats.append({
            "id": form.id,
            "title": form.title,
            "is_published": form.is_published,
            "created_at": form.created_at.isoformat() if form.created_at else None,
            "closes_at": form.closes_at.isoformat() if form.closes_at else None,
            "response_count": response_count,
            "employee_count": total_employees,
            "response_rate": response_rate,
            "rewards_calculated": len(rewards) > 0,
            "reward_distribution": reward_distribution,
        })

    return jsonify({
        "total_forms": len(forms),
        "published_forms": published_count,
        "draft_forms": draft_count,
        "total_responses": total_responses,
        "total_employees": total_employees,
        "forms": form_stats,
    })
