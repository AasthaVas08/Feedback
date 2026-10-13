"""Tests for the email notification system.

Covers:
- Notification model creation and relationships
- Publish endpoint creating notification rows
- Notification API endpoints (list, stats)
- Email service logic (with mocked Graph API)
- Reminder CLI command
- Idempotency (no duplicate notifications)
- Error handling for failed sends
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import Form, Notification, Question, User


# ── Helpers ────────────────────────────────────────────────────────


def _make_owner(db_session, email="owner@test.com"):
    owner = User(name="Owner", email=email, role="owner")
    db_session.add(owner)
    db_session.flush()
    return owner


def _make_employee(db_session, email="emp@test.com", name="Employee"):
    emp = User(name=name, email=email, role="employee")
    db_session.add(emp)
    db_session.flush()
    return emp


def _make_publishable_form(db_session, owner, title="Test Form", closes_at=None):
    """Create a form with one question so it can be published."""
    form = Form(title=title, owner_id=owner.id, closes_at=closes_at)
    db_session.add(form)
    db_session.flush()
    db_session.add(Question(
        form_id=form.id, question_text="Q1",
        question_type="text", order=1,
    ))
    db_session.commit()
    return form


# ── Notification Model Tests ──────────────────────────────────────


class TestNotificationModel:
    """Notification model CRUD and relationships."""

    def test_create_notification(self, client, db):
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        notif = Notification(
            form_id=form.id,
            recipient_id=emp.id,
            notification_type="publish",
            status="pending",
        )
        db.session.add(notif)
        db.session.commit()

        assert notif.id is not None
        assert notif.form_id == form.id
        assert notif.recipient_id == emp.id
        assert notif.notification_type == "publish"
        assert notif.status == "pending"
        assert notif.created_at is not None
        assert notif.sent_at is None
        assert notif.error_message is None

    def test_notification_relationships(self, client, db):
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        notif = Notification(
            form_id=form.id,
            recipient_id=emp.id,
            notification_type="publish",
        )
        db.session.add(notif)
        db.session.commit()

        # Relationship to form
        assert notif.form.title == "Test Form"
        # Relationship to recipient
        assert notif.recipient.email == "emp@test.com"
        # Reverse relationship from form
        assert form.notifications.count() == 1
        # Reverse relationship from user
        assert emp.notifications.count() == 1

    def test_notification_repr(self, client, db):
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        notif = Notification(
            form_id=form.id,
            recipient_id=emp.id,
            notification_type="publish",
            status="pending",
        )
        db.session.add(notif)
        db.session.commit()

        r = repr(notif)
        assert "Notification" in r
        assert "publish" in r
        assert "pending" in r

    def test_notification_cascade_delete_form(self, client, db):
        """Deleting a form cascades to its notifications."""
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        notif = Notification(
            form_id=form.id,
            recipient_id=emp.id,
            notification_type="publish",
        )
        db.session.add(notif)
        db.session.commit()
        notif_id = notif.id

        db.session.delete(form)
        db.session.commit()

        assert db.session.get(Notification, notif_id) is None


# ── Publish Endpoint + Notifications ──────────────────────────────


class TestPublishWithNotifications:
    """POST /api/forms/<id>/publish creates notification rows."""

    @patch("app.services.email_service.threading.Thread")
    def test_publish_creates_notifications(self, mock_thread, client, db):
        owner = _make_owner(db.session)
        emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
        emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
        form = _make_publishable_form(db.session, owner)

        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["notifications_queued"] == 2

        # Verify notification rows were created
        notifs = Notification.query.filter_by(form_id=form.id).all()
        assert len(notifs) == 2
        assert all(n.notification_type == "publish" for n in notifs)
        assert all(n.status == "pending" for n in notifs)

        # Background thread was started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("app.services.email_service.threading.Thread")
    def test_publish_idempotent_notifications(self, mock_thread, client, db):
        """Publishing twice doesn't create duplicate notifications."""
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        # First publish
        client.post(f"/api/forms/{form.id}/publish")
        assert Notification.query.filter_by(form_id=form.id).count() == 1

        # Try to publish again — should fail (already published)
        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 409

        # Still only 1 notification
        assert Notification.query.filter_by(form_id=form.id).count() == 1

    @patch("app.services.email_service.threading.Thread")
    def test_publish_no_employees(self, mock_thread, client, db):
        """Publishing with no employees creates zero notifications."""
        owner = _make_owner(db.session)
        form = _make_publishable_form(db.session, owner)

        resp = client.post(f"/api/forms/{form.id}/publish")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["notifications_queued"] == 0
        assert Notification.query.filter_by(form_id=form.id).count() == 0

        # No thread started when there's nothing to send
        mock_thread.assert_not_called()


# ── Notification API Endpoints ────────────────────────────────────


class TestNotificationEndpoints:
    """GET /api/forms/<id>/notifications and GET /api/notifications/stats."""

    def test_list_form_notifications(self, client, db):
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        db.session.add(Notification(
            form_id=form.id, recipient_id=emp.id,
            notification_type="publish", status="sent",
            sent_at=datetime.now(timezone.utc),
        ))
        db.session.commit()

        resp = client.get(f"/api/forms/{form.id}/notifications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["sent"] == 1
        assert data["failed"] == 0
        assert data["pending"] == 0
        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["recipient_email"] == "emp@test.com"

    def test_list_form_notifications_not_found(self, client, db):
        resp = client.get(f"/api/forms/{uuid.uuid4()}/notifications")
        assert resp.status_code == 404

    def test_notification_stats_empty(self, client, db):
        resp = client.get("/api/notifications/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["sent"] == 0
        assert data["failed"] == 0

    def test_notification_stats_with_data(self, client, db):
        owner = _make_owner(db.session)
        emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
        emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
        form = _make_publishable_form(db.session, owner)

        db.session.add(Notification(
            form_id=form.id, recipient_id=emp1.id,
            notification_type="publish", status="sent",
        ))
        db.session.add(Notification(
            form_id=form.id, recipient_id=emp2.id,
            notification_type="publish", status="failed",
            error_message="Connection timeout",
        ))
        db.session.commit()

        resp = client.get("/api/notifications/stats")
        data = resp.get_json()
        assert data["total"] == 2
        assert data["sent"] == 1
        assert data["failed"] == 1
        assert data["by_type"]["publish"] == 2
        assert data["by_type"]["reminder"] == 0


# ── Email Service Unit Tests ──────────────────────────────────────


class TestEmailService:
    """Unit tests for the email service functions."""

    @patch("app.services.email_service.threading.Thread")
    def test_queue_publish_notifications(self, mock_thread, app, db):
        from app.services.email_service import queue_publish_notifications

        with app.app_context():
            owner = _make_owner(db.session)
            emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
            emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
            form = _make_publishable_form(db.session, owner)

            count = queue_publish_notifications(app, form.id)
            assert count == 2

            notifs = Notification.query.filter_by(form_id=form.id).all()
            assert len(notifs) == 2
            assert all(n.status == "pending" for n in notifs)

    @patch("app.services.email_service.threading.Thread")
    def test_queue_publish_idempotent(self, mock_thread, app, db):
        from app.services.email_service import queue_publish_notifications

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(db.session, owner)

            count1 = queue_publish_notifications(app, form.id)
            assert count1 == 1

            # Second call should not create duplicates
            count2 = queue_publish_notifications(app, form.id)
            assert count2 == 0

    @patch("app.services.email_service.threading.Thread")
    def test_queue_reminder_notifications(self, mock_thread, app, db):
        from app.services.email_service import queue_reminder_notifications

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(
                db.session, owner,
                closes_at=datetime.now(timezone.utc) + timedelta(hours=12),
            )
            form.is_published = True
            db.session.commit()

            count = queue_reminder_notifications(app, form.id)
            assert count == 1

            notifs = Notification.query.filter_by(
                form_id=form.id, notification_type="reminder"
            ).all()
            assert len(notifs) == 1

    @patch("app.services.email_service.threading.Thread")
    def test_queue_reminder_skips_respondents(self, mock_thread, app, db):
        """Employees who already responded don't get reminders."""
        from app.models import Response as FormResponse
        from app.services.email_service import queue_reminder_notifications

        with app.app_context():
            owner = _make_owner(db.session)
            emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
            emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
            form = _make_publishable_form(
                db.session, owner,
                closes_at=datetime.now(timezone.utc) + timedelta(hours=12),
            )
            form.is_published = True
            db.session.flush()

            # emp1 has already responded
            db.session.add(FormResponse(
                form_id=form.id, respondent_id=emp1.id,
            ))
            db.session.commit()

            count = queue_reminder_notifications(app, form.id)
            assert count == 1

            notif = Notification.query.filter_by(
                form_id=form.id, notification_type="reminder"
            ).first()
            assert notif.recipient_id == emp2.id

    def test_send_notifications_dry_run(self, app, db):
        """When MAIL_ENABLED is false, notifications are marked sent (dry run)."""
        from app.services.email_service import _send_notifications_for_form

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(db.session, owner)

            db.session.add(Notification(
                form_id=form.id, recipient_id=emp.id,
                notification_type="publish", status="pending",
            ))
            db.session.commit()

            # MAIL_ENABLED is False in testing config
            _send_notifications_for_form(app, form.id, "publish")

            notif = Notification.query.filter_by(form_id=form.id).first()
            assert notif.status == "sent"
            assert notif.error_message == "dry_run: MAIL_ENABLED=false"
            assert notif.sent_at is not None

    @patch("app.services.email_service._send_single_email")
    @patch("app.services.email_service._get_access_token", return_value="fake-token")
    def test_send_notifications_real_send(self, mock_token, mock_send, app, db):
        """When MAIL_ENABLED is true, the Graph API is called."""
        from app.services.email_service import _send_notifications_for_form

        with app.app_context():
            app.config["MAIL_ENABLED"] = True
            app.config["MAIL_SENDER_EMAIL"] = "sender@company.com"

            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(db.session, owner)

            db.session.add(Notification(
                form_id=form.id, recipient_id=emp.id,
                notification_type="publish", status="pending",
            ))
            db.session.commit()

            _send_notifications_for_form(app, form.id, "publish")

            notif = Notification.query.filter_by(form_id=form.id).first()
            assert notif.status == "sent"
            assert notif.sent_at is not None

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args.kwargs["recipient_email"] == "emp@test.com"
            assert call_args.kwargs["access_token"] == "fake-token"

            # Reset config
            app.config["MAIL_ENABLED"] = False

    @patch("app.services.email_service._send_single_email", side_effect=Exception("SMTP error"))
    @patch("app.services.email_service._get_access_token", return_value="fake-token")
    def test_send_notifications_handles_failure(self, mock_token, mock_send, app, db):
        """Failed sends are recorded with error messages."""
        from app.services.email_service import _send_notifications_for_form

        with app.app_context():
            app.config["MAIL_ENABLED"] = True
            app.config["MAIL_SENDER_EMAIL"] = "sender@company.com"

            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(db.session, owner)

            db.session.add(Notification(
                form_id=form.id, recipient_id=emp.id,
                notification_type="publish", status="pending",
            ))
            db.session.commit()

            _send_notifications_for_form(app, form.id, "publish")

            notif = Notification.query.filter_by(form_id=form.id).first()
            assert notif.status == "failed"
            assert "SMTP error" in notif.error_message

            app.config["MAIL_ENABLED"] = False

    @patch("app.services.email_service._get_access_token", side_effect=RuntimeError("Token failed"))
    def test_send_notifications_token_failure(self, mock_token, app, db):
        """Token acquisition failure marks all notifications as failed."""
        from app.services.email_service import _send_notifications_for_form

        with app.app_context():
            app.config["MAIL_ENABLED"] = True

            owner = _make_owner(db.session)
            emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
            emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
            form = _make_publishable_form(db.session, owner)

            db.session.add(Notification(
                form_id=form.id, recipient_id=emp1.id,
                notification_type="publish", status="pending",
            ))
            db.session.add(Notification(
                form_id=form.id, recipient_id=emp2.id,
                notification_type="publish", status="pending",
            ))
            db.session.commit()

            _send_notifications_for_form(app, form.id, "publish")

            notifs = Notification.query.filter_by(form_id=form.id).all()
            assert all(n.status == "failed" for n in notifs)
            assert all("Token failed" in n.error_message for n in notifs)

            app.config["MAIL_ENABLED"] = False


# ── Email Body Builder Tests ──────────────────────────────────────


class TestEmailBodyBuilders:
    """Test that email bodies contain the right content."""

    def test_publish_email_content(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(
                db.session, owner, title="Q3 Survey",
                closes_at=datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            )
            form.description = "Please fill out this survey"
            db.session.commit()

            subject, body = _build_publish_email(form, "http://localhost:5000")

            assert "Q3 Survey" in subject
            assert "Q3 Survey" in body
            assert "Please fill out this survey" in body
            assert f"/form/{form.id}" in body
            assert "December 31, 2026" in body

    def test_publish_email_no_deadline(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(db.session, owner, title="Open Survey")

            subject, body = _build_publish_email(form, "http://localhost:5000")

            assert "No deadline set" in body

    def test_reminder_email_content(self, app, db):
        from app.services.email_service import _build_reminder_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(
                db.session, owner, title="Urgent Survey",
                closes_at=datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
            )

            subject, body = _build_reminder_email(form, "http://localhost:5000")

            assert "Urgent Survey" in subject
            assert "Reminder" in subject or "⏰" in subject
            assert "Urgent Survey" in body
            assert f"/form/{form.id}" in body
            assert "Closing Soon" in body


# ── Send Closing Reminders Tests ──────────────────────────────────


class TestSendClosingReminders:
    """Test the send_closing_reminders function."""

    @patch("app.services.email_service.threading.Thread")
    def test_finds_forms_closing_soon(self, mock_thread, app, db):
        from app.services.email_service import send_closing_reminders

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)

            # Form closing in 12 hours — should get reminders
            form1 = _make_publishable_form(
                db.session, owner, title="Closing Soon",
                closes_at=datetime.now(timezone.utc) + timedelta(hours=12),
            )
            form1.is_published = True

            # Form closing in 48 hours — should NOT get reminders
            form2 = _make_publishable_form(
                db.session, owner, title="Not Yet",
                closes_at=datetime.now(timezone.utc) + timedelta(hours=48),
            )
            form2.is_published = True

            # Form already closed — should NOT get reminders
            form3 = _make_publishable_form(
                db.session, owner, title="Already Closed",
                closes_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            form3.is_published = True

            db.session.commit()

            results = send_closing_reminders(app)

            assert form1.id in results
            assert form2.id not in results
            assert form3.id not in results
            assert results[form1.id] == 1

    @patch("app.services.email_service.threading.Thread")
    def test_no_forms_closing(self, mock_thread, app, db):
        from app.services.email_service import send_closing_reminders

        with app.app_context():
            results = send_closing_reminders(app)
            assert results == {}


# ── CLI Command Tests ─────────────────────────────────────────────


class TestCLICommands:
    """Test the Flask CLI commands for notifications."""

    @patch("app.services.email_service.threading.Thread")
    def test_send_reminders_command(self, mock_thread, app, db):
        from click.testing import CliRunner
        from app.cli import notify_cli

        runner = CliRunner()

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(
                db.session, owner, title="CLI Test",
                closes_at=datetime.now(timezone.utc) + timedelta(hours=12),
            )
            form.is_published = True
            db.session.commit()

            result = runner.invoke(notify_cli, ["send-reminders"], obj=app)
            assert result.exit_code == 0
            assert "reminder" in result.output.lower() or "queued" in result.output.lower()

    def test_status_command(self, app, db):
        from click.testing import CliRunner
        from app.cli import notify_cli

        runner = CliRunner()

        with app.app_context():
            result = runner.invoke(notify_cli, ["status"], obj=app)
            assert result.exit_code == 0
            assert "Total" in result.output

    @patch("app.services.email_service.threading.Thread")
    def test_send_publish_command(self, mock_thread, app, db):
        from click.testing import CliRunner
        from app.cli import notify_cli

        runner = CliRunner()

        with app.app_context():
            owner = _make_owner(db.session)
            emp = _make_employee(db.session)
            form = _make_publishable_form(db.session, owner)
            form.is_published = True
            db.session.commit()

            result = runner.invoke(notify_cli, ["send-publish", form.id], obj=app)
            assert result.exit_code == 0
            assert "queued" in result.output.lower() or "Queued" in result.output

    def test_send_publish_not_found(self, app, db):
        from click.testing import CliRunner
        from app.cli import notify_cli

        runner = CliRunner()

        with app.app_context():
            result = runner.invoke(notify_cli, ["send-publish", str(uuid.uuid4())], obj=app)
            assert result.exit_code != 0

    def test_send_publish_not_published(self, app, db):
        from click.testing import CliRunner
        from app.cli import notify_cli

        runner = CliRunner()

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(db.session, owner)
            db.session.commit()

            result = runner.invoke(notify_cli, ["send-publish", form.id], obj=app)
            assert result.exit_code != 0
