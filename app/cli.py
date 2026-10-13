"""Flask CLI commands for scheduled tasks.

Usage
-----
    flask notify send-reminders     — send 24-hour closing reminders
    flask notify send-publish <id>  — (re)send publish notifications for a form
    flask notify status             — show notification statistics
"""

import click
from flask import current_app
from flask.cli import AppGroup

from app import db
from app.models import Form, Notification

notify_cli = AppGroup("notify", help="Email notification commands.")


@notify_cli.command("send-reminders")
def send_reminders():
    """Find forms closing within 24 hours and send reminder emails.

    Intended to be run as a cron job or scheduled task, e.g.::

        0 * * * * cd /path/to/app && flask notify send-reminders
    """
    from app.services.email_service import send_closing_reminders

    click.echo("Checking for forms closing within 24 hours...")
    results = send_closing_reminders(current_app._get_current_object())

    if not results:
        click.echo("No forms closing within 24 hours.")
        return

    for form_id, count in results.items():
        click.echo(f"  Form {form_id}: {count} reminder(s) queued")

    click.echo(f"Done. {sum(results.values())} total reminder(s) queued.")


@notify_cli.command("send-publish")
@click.argument("form_id")
def send_publish(form_id):
    """(Re)send publish notifications for a specific form.

    Useful for retrying failed sends or notifying new employees.
    """
    from app.services.email_service import queue_publish_notifications

    form = db.session.get(Form, form_id)
    if form is None:
        click.echo(f"Error: Form {form_id} not found.", err=True)
        raise SystemExit(1)

    if not form.is_published:
        click.echo(f"Error: Form {form_id} is not published.", err=True)
        raise SystemExit(1)

    count = queue_publish_notifications(current_app._get_current_object(), form_id)
    click.echo(f"Queued {count} publish notification(s) for form {form_id}.")


@notify_cli.command("status")
def status():
    """Show notification statistics."""
    total = Notification.query.count()
    sent = Notification.query.filter_by(status="sent").count()
    failed = Notification.query.filter_by(status="failed").count()
    pending = Notification.query.filter_by(status="pending").count()

    click.echo("Notification Statistics")
    click.echo("=" * 40)
    click.echo(f"  Total:   {total}")
    click.echo(f"  Sent:    {sent}")
    click.echo(f"  Failed:  {failed}")
    click.echo(f"  Pending: {pending}")

    if failed > 0:
        click.echo("")
        click.echo("Recent failures:")
        failures = (
            Notification.query
            .filter_by(status="failed")
            .order_by(Notification.created_at.desc())
            .limit(5)
            .all()
        )
        for n in failures:
            click.echo(
                f"  [{n.notification_type}] form={n.form_id[:8]}... "
                f"to=user:{n.recipient_id} — {n.error_message or 'unknown error'}"
            )
