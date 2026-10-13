"""Form model — a questionnaire/feedback form identified by UUID."""

import uuid
from datetime import datetime, timezone

from app import db


def _new_uuid() -> str:
    """Generate a new UUID-4 string for use as a form identifier.

    Using a callable default (rather than ``default=uuid.uuid4``) ensures
    each form gets its own unique ID at INSERT time.  The UUID is stored
    as a 36-character string (``xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx``)
    which works identically on SQLite and PostgreSQL.
    """
    return str(uuid.uuid4())


class Form(db.Model):
    """A feedback/questionnaire form.

    Each form is identified by a UUID so it can be shared via URL without
    exposing sequential IDs.

    Attributes
    ----------
    id : str
        UUID-4 primary key.
    title : str
        Human-readable title shown to respondents.
    description : str | None
        Optional longer description / instructions.
    owner_id : int
        FK → ``users.id`` — the user who created the form.
    created_at : datetime
        UTC creation timestamp.
    closes_at : datetime | None
        Optional deadline; after this the form stops accepting responses
        and rewards can be calculated.
    is_published : bool
        ``True`` once the owner publishes the form (triggers email
        notifications to employees).
    """

    __tablename__ = "forms"

    id = db.Column(db.String(36), primary_key=True, default=_new_uuid)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    closes_at = db.Column(db.DateTime(timezone=True), nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    owner = db.relationship("User", back_populates="owned_forms")
    questions = db.relationship(
        "Question",
        back_populates="form",
        lazy="dynamic",
        order_by="Question.order",
        cascade="all, delete-orphan",
    )
    responses = db.relationship(
        "Response",
        back_populates="form",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    rewards = db.relationship(
        "Reward",
        back_populates="form",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Form {self.id!r} title={self.title!r}>"
