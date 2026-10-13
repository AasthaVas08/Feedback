"""Reward calculation and leaderboard endpoints.

Routes
------
POST /api/forms/<id>/rewards/calculate — compute time-based rewards
GET  /api/forms/<id>/rewards           — leaderboard data

Reward formula (from S-1 spec):
    points = max_reward − (max_reward − min_reward) × (rank − 1) / (total − 1)

    - Rank 1 (first submitter) → max_reward points
    - Rank N (last submitter)  → min_reward points
    - Single submitter         → max_reward points
"""

from datetime import datetime, timezone

from flask import current_app, jsonify, request

from app import db
from app.api import api_bp
from app.models import Form, Response, Reward


def _calculate_reward_points(
    rank: int,
    total: int,
    max_pts: float,
    min_pts: float,
) -> float:
    """Compute reward points for a given rank using linear interpolation.

    The formula distributes points evenly between max_pts (rank 1) and
    min_pts (rank N).  The fraction ``(rank - 1) / (total - 1)`` maps
    rank 1 → 0.0 and rank N → 1.0, so subtracting it from max_pts
    produces a straight-line decay.

    Edge case: when there is only one respondent (total <= 1), the
    denominator would be zero, so we short-circuit and return max_pts.
    A sole respondent deserves the full reward.

    The result is rounded to 2 decimal places to avoid floating-point
    artefacts in JSON output and database storage.
    """
    if total <= 1:
        # Single respondent — avoid division by zero, award full points.
        return max_pts
    # Linear interpolation: rank 1 → max_pts, rank N → min_pts.
    return round(max_pts - (max_pts - min_pts) * (rank - 1) / (total - 1), 2)


# ── POST /api/forms/<id>/rewards/calculate ─────────────────────────

@api_bp.route("/forms/<form_id>/rewards/calculate", methods=["POST"])
def calculate_rewards(form_id: str):
    """Compute time-based rewards for all respondents of a form.

    Optional JSON body::

        {
            "max_reward": 100,   // default from config
            "min_reward": 10     // default from config
        }

    Rewards are recalculated from scratch each time (old rewards for this
    form are deleted first).
    """
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    # Get responses ordered by submission time (earliest first).
    responses = (
        Response.query
        .filter_by(form_id=form_id)
        .order_by(Response.submitted_at.asc())
        .all()
    )

    if not responses:
        return jsonify({"error": "No responses to calculate rewards for"}), 400

    # Read reward bounds from request body or config defaults.
    data = request.get_json(silent=True) or {}
    max_pts = float(data.get("max_reward", current_app.config["DEFAULT_MAX_REWARD"]))
    min_pts = float(data.get("min_reward", current_app.config["DEFAULT_MIN_REWARD"]))

    if max_pts <= min_pts:
        return jsonify({"error": "max_reward must be greater than min_reward"}), 400

    # Delete existing rewards for this form so the operation is idempotent.
    # This means calling calculate twice produces the same result — safe to
    # retry after new responses arrive or after changing reward bounds.
    Reward.query.filter_by(form_id=form_id).delete()

    total = len(responses)
    now = datetime.now(timezone.utc)
    created_rewards = []

    for rank, resp in enumerate(responses, start=1):
        pts = _calculate_reward_points(rank, total, max_pts, min_pts)
        reward = Reward(
            form_id=form_id,
            user_id=resp.respondent_id,
            rank=rank,
            reward_points=pts,
            calculated_at=now,
        )
        db.session.add(reward)
        created_rewards.append({
            "rank": rank,
            "user_id": resp.respondent_id,
            "user_name": resp.respondent.name if resp.respondent else None,
            "user_email": resp.respondent.email if resp.respondent else None,
            "reward_points": pts,
            "submitted_at": resp.submitted_at.isoformat() if resp.submitted_at else None,
        })

    db.session.commit()

    return jsonify({
        "form_id": form_id,
        "total_respondents": total,
        "max_reward": max_pts,
        "min_reward": min_pts,
        "rewards": created_rewards,
    }), 201


# ── GET /api/forms/<id>/rewards ────────────────────────────────────

@api_bp.route("/forms/<form_id>/rewards", methods=["GET"])
def get_leaderboard(form_id: str):
    """Return the reward leaderboard for a form, ranked by submission order."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    rewards = (
        Reward.query
        .filter_by(form_id=form_id)
        .order_by(Reward.rank.asc())
        .all()
    )

    if not rewards:
        return jsonify({
            "form_id": form_id,
            "form_title": form.title,
            "message": "No rewards calculated yet",
            "leaderboard": [],
        })

    leaderboard = []
    for r in rewards:
        leaderboard.append({
            "rank": r.rank,
            "user_id": r.user_id,
            "user_name": r.user.name if r.user else None,
            "user_email": r.user.email if r.user else None,
            "reward_points": r.reward_points,
            "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
        })

    return jsonify({
        "form_id": form_id,
        "form_title": form.title,
        "total_respondents": len(leaderboard),
        "leaderboard": leaderboard,
    })
