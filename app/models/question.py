"""Question model — individual questions within a form."""

import json

from app import db


class Question(db.Model):
    """A single question belonging to a :class:`Form`.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    form_id : str
        FK → ``forms.id`` (UUID).
    question_text : str
        The question shown to the respondent.
    question_type : str
        One of ``text``, ``multiple_choice``, ``rating``, ``checkbox``.
    options : str | None
        JSON-encoded list of options for ``multiple_choice`` / ``checkbox``
        types.  ``None`` for ``text`` and ``rating``.
    order : int
        Display order within the form (ascending).
    """

    __tablename__ = "questions"

    ALLOWED_TYPES = ("text", "multiple_choice", "rating", "checkbox")

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(
        db.String(36),
        db.ForeignKey("forms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False, default="text")
    # Options are stored as a JSON-encoded string rather than a native
    # JSON column for SQLite compatibility.  The get_options() and
    # set_options() helpers handle serialisation/deserialisation.
    options = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    form = db.relationship("Form", back_populates="questions")
    answers = db.relationship(
        "Answer",
        back_populates="question",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # --- helpers for the JSON options column ---

    def get_options(self) -> list[str]:
        """Deserialise the options JSON into a Python list."""
        if self.options is None:
            return []
        return json.loads(self.options)

    def set_options(self, values: list[str]) -> None:
        """Serialise a Python list into the options JSON column."""
        self.options = json.dumps(values)

    def __repr__(self) -> str:
        return (
            f"<Question {self.id} type={self.question_type!r} "
            f"form={self.form_id!r}>"
        )
