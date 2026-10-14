"""User model — owners and respondents."""

from datetime import datetime, timezone

from app import db


class User(db.Model):
    """A platform user who can own forms or submit responses.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    name : str
        Display name.
    email : str
        Unique email address (used for notifications).
    role : str
        ``owner`` — can create/manage forms.
        ``employee`` — can fill in forms.
    created_at : datetime
        UTC timestamp of account creation.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    role = db.Column(
        db.String(20),
        nullable=False,
        default="employee",
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    owned_forms = db.relationship("Form", back_populates="owner", lazy="dynamic")
    responses = db.relationship("Response", back_populates="respondent", lazy="dynamic")
    rewards = db.relationship("Reward", back_populates="user", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email!r} role={self.role}>"
