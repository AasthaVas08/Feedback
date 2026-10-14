"""Answer model — one answer to one question within a response."""

from app import db


class Answer(db.Model):
    """A single answer to a :class:`Question` inside a :class:`Response`.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    response_id : int
        FK → ``responses.id``.
    question_id : int
        FK → ``questions.id``.
    answer_value : str
        Free-text value.  For ``multiple_choice`` / ``checkbox`` types this
        stores the selected option(s) as a JSON string; for ``rating`` it
        stores the numeric rating as a string; for ``text`` it is plain text.
    """

    __tablename__ = "answers"

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(
        db.Integer,
        db.ForeignKey("responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = db.Column(
        db.Integer,
        db.ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_value = db.Column(db.Text, nullable=False)

    # Unique constraint: one answer per question per response
    __table_args__ = (
        db.UniqueConstraint(
            "response_id", "question_id", name="uq_one_answer_per_question"
        ),
    )

    # Relationships
    response = db.relationship("Response", back_populates="answers")
    question = db.relationship("Question", back_populates="answers")

    def __repr__(self) -> str:
        return (
            f"<Answer {self.id} response={self.response_id} "
            f"question={self.question_id}>"
        )
