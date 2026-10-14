"""Reward model — time-based reward calculated after a form closes."""

from datetime import datetime, timezone

from app import db


class Reward(db.Model):
    """Reward record for a user on a specific form.

    Rewards are calculated once a form's collection period ends (or on
    demand).  The first respondent gets ``max_reward`` points and the last
    gets ``min_reward``; intermediate respondents are scaled linearly by
    submission order.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    form_id : str
        FK → ``forms.id`` (UUID).
    user_id : int
        FK → ``users.id`` — the respondent who earned the reward.
    rank : int
        1-based submission rank (1 = first to submit).
    reward_points : float
        Points awarded (higher for earlier submissions).
    calculated_at : datetime
        UTC timestamp of when the reward was computed.
    """

    __tablename__ = "rewards"

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(
        db.String(36),
        db.ForeignKey("forms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank = db.Column(db.Integer, nullable=False)
    reward_points = db.Column(db.Float, nullable=False)
    calculated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Unique constraint: one reward per user per form
    __table_args__ = (
        db.UniqueConstraint("form_id", "user_id", name="uq_one_reward_per_user_per_form"),
    )

    # Relationships
    form = db.relationship("Form", back_populates="rewards")
    user = db.relationship("User", back_populates="rewards")

    def __repr__(self) -> str:
        return (
            f"<Reward {self.id} form={self.form_id!r} "
            f"user={self.user_id} rank={self.rank} pts={self.reward_points}>"
        )
