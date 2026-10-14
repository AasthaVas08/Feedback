"""Email notification service using Microsoft 365 Graph API.

Responsibilities
----------------
* Send publish notifications to all employees when a form is published.
* Send reminder emails 24 hours before a form's closing date.
* Log every attempt in the ``notifications`` table.
* Run email sends in a background thread so the API returns immediately.

Configuration
-------------
Set ``MAIL_ENABLED=true`` and provide the MS Graph credentials in the
environment (see ``.env.example``).  When ``MAIL_ENABLED`` is false the
service logs the intent but does not call the Graph API — safe for
dev/test.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask

from app import db
from app.models import Form, Notification, User

logger = logging.getLogger(__name__)

# Microsoft Graph endpoints
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"


# ── Graph API helpers ──────────────────────────────────────────────


def _get_access_token(app: Flask) -> str:
    """Obtain an OAuth2 access token via the client-credentials flow.

    Raises
    ------
    RuntimeError
        If the token request fails.
    """
    tenant_id = app.config["MS_GRAPH_TENANT_ID"]
    url = _TOKEN_URL.format(tenant=tenant_id)

    payload = {
        "client_id": app.config["MS_GRAPH_CLIENT_ID"],
        "client_secret": app.config["MS_GRAPH_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    resp = requests.post(url, data=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to obtain Graph API token: {resp.status_code} {resp.text}"
        )

    return resp.json()["access_token"]


def _send_single_email(
    access_token: str,
    sender_email: str,
    recipient_email: str,
    subject: str,
    html_body: str,
) -> None:
    """Send one email via the Graph API ``sendMail`` endpoint.

    Raises
    ------
    requests.HTTPError
        If the Graph API returns a non-2xx status.
    """
    url = _SEND_MAIL_URL.format(sender=sender_email)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient_email}},
            ],
        },
        "saveToSentItems": "false",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()


# ── Email body builders ───────────────────────────────────────────


def _build_publish_email(form: Form, base_url: str) -> tuple[str, str]:
    """Return (subject, html_body) for a publish notification."""
    form_url = f"{base_url}/form/{form.id}"
    closes_text = (
        form.closes_at.strftime("%B %d, %Y at %H:%M UTC")
        if form.closes_at
        else "No deadline set"
    )

    subject = f"New Feedback Form: {form.title}"
    html_body = f"""\
<div style="font-family: 'Inter', -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #4f46e5;">📋 New Feedback Form Published</h2>
  <p>A new feedback form has been published and is ready for your response.</p>
  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <tr>
      <td style="padding: 8px 12px; font-weight: 600; color: #374151;">Title</td>
      <td style="padding: 8px 12px;">{form.title}</td>
    </tr>
    <tr>
      <td style="padding: 8px 12px; font-weight: 600; color: #374151;">Description</td>
      <td style="padding: 8px 12px;">{form.description or 'No description provided'}</td>
    </tr>
    <tr>
      <td style="padding: 8px 12px; font-weight: 600; color: #374151;">Closing Date</td>
      <td style="padding: 8px 12px;">{closes_text}</td>
    </tr>
  </table>
  <p>
    <a href="{form_url}"
       style="display: inline-block; padding: 12px 24px; background: #4f46e5;
              color: #ffffff; text-decoration: none; border-radius: 6px;
              font-weight: 600;">
      Fill Out Form →
    </a>
  </p>
  <p style="color: #6b7280; font-size: 13px; margin-top: 24px;">
    Submit early for maximum reward points! The earlier you respond, the
    more points you earn.
  </p>
</div>"""

    return subject, html_body


def _build_reminder_email(form: Form, base_url: str) -> tuple[str, str]:
    """Return (subject, html_body) for a 24-hour closing reminder."""
    form_url = f"{base_url}/form/{form.id}"
    closes_text = (
        form.closes_at.strftime("%B %d, %Y at %H:%M UTC")
        if form.closes_at
        else "soon"
    )

    subject = f"⏰ Reminder: \"{form.title}\" closes {closes_text}"
    html_body = f"""\
<div style="font-family: 'Inter', -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #dc2626;">⏰ Form Closing Soon!</h2>
  <p>
    The feedback form <strong>{form.title}</strong> is closing in less than
    24 hours. Don't miss your chance to respond and earn reward points!
  </p>
  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <tr>
      <td style="padding: 8px 12px; font-weight: 600; color: #374151;">Title</td>
      <td style="padding: 8px 12px;">{form.title}</td>
    </tr>
    <tr>
      <td style="padding: 8px 12px; font-weight: 600; color: #374151;">Closes At</td>
      <td style="padding: 8px 12px; color: #dc2626; font-weight: 600;">{closes_text}</td>
    </tr>
  </table>
  <p>
    <a href="{form_url}"
       style="display: inline-block; padding: 12px 24px; background: #dc2626;
              color: #ffffff; text-decoration: none; border-radius: 6px;
              font-weight: 600;">
      Respond Now →
    </a>
  </p>
  <p style="color: #6b7280; font-size: 13px; margin-top: 24px;">
    This is an automated reminder. If you have already submitted your
    response, please disregard this email.
  </p>
</div>"""

    return subject, html_body


# ── Core send logic ───────────────────────────────────────────────


def _send_notifications_for_form(
    app: Flask,
    form_id: str,
    notification_type: str,
) -> None:
    """Send emails for all pending notifications of a form.

    Runs inside an application context (typically in a background thread).
    Each notification row is updated to ``sent`` or ``failed`` individually
    so partial failures are recorded.
    """
    with app.app_context():
        mail_enabled = app.config.get("MAIL_ENABLED", False)
        sender_email = app.config.get("MAIL_SENDER_EMAIL", "")
        base_url = app.config.get("APP_BASE_URL", "http://localhost:5000").rstrip("/")

        form = db.session.get(Form, form_id)
        if form is None:
            logger.error("Notification job: form %s not found", form_id)
            return

        # Build the email content once (same for all recipients)
        if notification_type == "reminder":
            subject, html_body = _build_reminder_email(form, base_url)
        else:
            subject, html_body = _build_publish_email(form, base_url)

        pending = Notification.query.filter_by(
            form_id=form_id,
            notification_type=notification_type,
            status="pending",
        ).all()

        if not pending:
            logger.info("No pending %s notifications for form %s", notification_type, form_id)
            return

        if not mail_enabled:
            # Dry-run mode: mark all notifications as "sent" so the flow
            # is fully testable without Graph API credentials.  The
            # error_message field records that this was a dry run, so
            # operators can distinguish real sends from simulated ones.
            logger.info(
                "MAIL_ENABLED is false — marking %d %s notifications as sent (dry run)",
                len(pending),
                notification_type,
            )
            now = datetime.now(timezone.utc)
            for notif in pending:
                notif.status = "sent"
                notif.sent_at = now
                notif.error_message = "dry_run: MAIL_ENABLED=false"
            db.session.commit()
            return

        # Obtain a single OAuth2 token for the entire batch.  If the
        # token request fails, ALL pending notifications are marked as
        # failed with the token error — this is deliberate: without a
        # valid token none of them can be sent, and recording the error
        # on each row makes it visible in the notification log and the
        # /api/notifications/stats endpoint.
        try:
            access_token = _get_access_token(app)
        except Exception as exc:
            logger.error("Failed to get Graph API token: %s", exc)
            for notif in pending:
                notif.status = "failed"
                notif.error_message = f"Token error: {exc}"
            db.session.commit()
            return

        # Send to each recipient individually
        for notif in pending:
            recipient = db.session.get(User, notif.recipient_id)
            if recipient is None:
                notif.status = "failed"
                notif.error_message = "Recipient user not found"
                db.session.commit()
                continue

            try:
                _send_single_email(
                    access_token=access_token,
                    sender_email=sender_email,
                    recipient_email=recipient.email,
                    subject=subject,
                    html_body=html_body,
                )
                notif.status = "sent"
                notif.sent_at = datetime.now(timezone.utc)
                logger.info(
                    "Sent %s email to %s for form %s",
                    notification_type,
                    recipient.email,
                    form_id,
                )
            except Exception as exc:
                notif.status = "failed"
                notif.error_message = str(exc)[:500]
                logger.error(
                    "Failed to send %s email to %s: %s",
                    notification_type,
                    recipient.email,
                    exc,
                )

            db.session.commit()


# ── Public API ────────────────────────────────────────────────────


def queue_publish_notifications(app: Flask, form_id: str) -> int:
    """Create notification rows for all employees and fire a background send.

    Parameters
    ----------
    app : Flask
        The Flask application (needed for config and app context in the
        background thread).
    form_id : str
        UUID of the form that was just published.

    Returns
    -------
    int
        Number of notification rows created.
    """
    with app.app_context():
        employees = User.query.filter_by(role="employee").all()
        if not employees:
            logger.info("No employees to notify for form %s", form_id)
            return 0

        # Avoid duplicate notifications (idempotency).  If the publish
        # endpoint is called twice, or if queue_publish_notifications is
        # retried via the CLI, we skip employees who already have a
        # notification row for this form+type combination.
        existing = {
            n.recipient_id
            for n in Notification.query.filter_by(
                form_id=form_id, notification_type="publish"
            ).all()
        }

        created = 0
        for emp in employees:
            if emp.id in existing:
                continue
            db.session.add(Notification(
                form_id=form_id,
                recipient_id=emp.id,
                notification_type="publish",
                status="pending",
            ))
            created += 1

        db.session.commit()

    # Fire the actual email sends in a background daemon thread so the
    # API endpoint returns immediately.  The thread gets its own app
    # context (via with app.app_context() in _send_notifications_for_form).
    # Using daemon=True means the thread is killed if the main process
    # exits — acceptable because each send is committed individually,
    # and unsent notifications remain "pending" for retry.
    if created > 0:
        thread = threading.Thread(
            target=_send_notifications_for_form,
            args=(app, form_id, "publish"),
            daemon=True,
        )
        thread.start()

    return created


def queue_reminder_notifications(app: Flask, form_id: str) -> int:
    """Create reminder notification rows for employees who have NOT yet
    responded, then fire a background send.

    Parameters
    ----------
    app : Flask
        The Flask application.
    form_id : str
        UUID of the form whose closing date is approaching.

    Returns
    -------
    int
        Number of reminder notifications created.
    """
    from app.models import Response as FormResponse

    with app.app_context():
        form = db.session.get(Form, form_id)
        if form is None or not form.is_published:
            logger.warning("Reminder skipped: form %s not found or not published", form_id)
            return 0

        # Only employees who have NOT already responded
        responded_ids = {
            r.respondent_id
            for r in FormResponse.query.filter_by(form_id=form_id).all()
        }
        employees = User.query.filter_by(role="employee").all()
        to_remind = [e for e in employees if e.id not in responded_ids]

        if not to_remind:
            logger.info("No employees to remind for form %s", form_id)
            return 0

        # Avoid duplicate reminders
        existing = {
            n.recipient_id
            for n in Notification.query.filter_by(
                form_id=form_id, notification_type="reminder"
            ).all()
        }

        created = 0
        for emp in to_remind:
            if emp.id in existing:
                continue
            db.session.add(Notification(
                form_id=form_id,
                recipient_id=emp.id,
                notification_type="reminder",
                status="pending",
            ))
            created += 1

        db.session.commit()

    if created > 0:
        thread = threading.Thread(
            target=_send_notifications_for_form,
            args=(app, form_id, "reminder"),
            daemon=True,
        )
        thread.start()

    return created


def send_closing_reminders(app: Flask) -> dict:
    """Find all published forms closing within the next 24 hours and send
    reminder emails to employees who haven't responded yet.

    Intended to be called from a CLI command or scheduled job.

    Returns
    -------
    dict
        Summary with form IDs and counts.
    """
    results = {}

    with app.app_context():
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        forms_closing = Form.query.filter(
            Form.is_published.is_(True),
            Form.closes_at.isnot(None),
            Form.closes_at > now,
            Form.closes_at <= cutoff,
        ).all()

        if not forms_closing:
            logger.info("No forms closing within 24 hours")
            return results

        for form in forms_closing:
            count = queue_reminder_notifications(app, form.id)
            results[form.id] = count
            logger.info(
                "Queued %d reminder(s) for form %s (%s)",
                count,
                form.id,
                form.title,
            )

    return results
