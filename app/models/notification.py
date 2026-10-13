"""Notification model — tracks email notifications sent to users."""

from datetime import datetime, timezone

from app import db


class Notification(db.Model):
    """Log of every email notification sent (or attempted) by the platform.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    form_id : str
        FK → ``forms.id`` — the form this notification is about.
    recipient_id : int
        FK → ``users.id`` — the user who received (or should have received)
        the email.
    notification_type : str
        ``publish`` — form was just published.
        ``reminder`` — 24-hour closing reminder.
    status : str
        ``pending`` — queued but not yet sent.
        ``sent`` — successfully delivered via Graph API.
        ``failed`` — delivery attempt failed (see ``error_message``).
    error_message : str | None
        Error details when ``status == 'failed'``.
    sent_at : datetime | None
        UTC timestamp of successful delivery.
    created_at : datetime
        UTC timestamp when the notification was created/queued.
    """

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(
        db.String(36),
        db.ForeignKey("forms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = db.Column(
        db.String(20),
        nullable=False,
        default="publish",
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    form = db.relationship(
        "Form",
        backref=db.backref(
            "notifications", lazy="dynamic", cascade="all, delete-orphan",
        ),
    )
    recipient = db.relationship(
        "User",
        backref=db.backref("notifications", lazy="dynamic"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification {self.id} type={self.notification_type!r} "
            f"status={self.status!r} to=user:{self.recipient_id}>"
        )
