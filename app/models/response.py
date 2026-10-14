"""Response model — one submission of a form by a respondent."""

from datetime import datetime, timezone

from app import db


class Response(db.Model):
    """A single submission of a :class:`Form` by a :class:`User`.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    form_id : str
        FK → ``forms.id`` (UUID).
    respondent_id : int
        FK → ``users.id`` — the employee who filled in the form.
    submitted_at : datetime
        UTC timestamp of submission — used for time-based reward ranking.
    """

    __tablename__ = "responses"

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(
        db.String(36),
        db.ForeignKey("forms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    respondent_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,  # indexed for reward-ranking ORDER BY
    )

    # Unique constraint: one response per user per form.
    # This is the database-level enforcement of the "no duplicate
    # submissions" rule.  The API also checks for duplicates before
    # INSERT (returning 409), but the constraint is the safety net
    # against race conditions in concurrent requests.
    __table_args__ = (
        db.UniqueConstraint("form_id", "respondent_id", name="uq_one_response_per_user_per_form"),
    )

    # Relationships
    form = db.relationship("Form", back_populates="responses")
    respondent = db.relationship("User", back_populates="responses")
    answers = db.relationship(
        "Answer",
        back_populates="response",
        lazy="joined",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Response {self.id} form={self.form_id!r} "
            f"user={self.respondent_id}>"
        )
