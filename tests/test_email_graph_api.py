"""Tests for email notification logic with mocked Graph API calls.

Covers:
- Graph API token acquisition (success and failure)
- Email sending via Graph API (success and failure)
- Publish email body content
- Reminder email body content
- Dry-run mode (MAIL_ENABLED=false)
- Partial send failures (some emails succeed, some fail)
- Background thread spawning
- Notification status transitions (pending → sent / failed)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

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
    form = Form(title=title, owner_id=owner.id, closes_at=closes_at)
    db_session.add(form)
    db_session.flush()
    db_session.add(Question(
        form_id=form.id, question_text="Q1",
        question_type="text", order=1,
    ))
    db_session.commit()
    return form


# ── Graph API Token Tests ─────────────────────────────────────────


class TestGraphAPIToken:
    """Tests for _get_access_token function."""

    @patch("app.services.email_service.requests.post")
    def test_get_access_token_success(self, mock_post, app, db):
        from app.services.email_service import _get_access_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test-token-123"}
        mock_post.return_value = mock_response

        with app.app_context():
            token = _get_access_token(app)

        assert token == "test-token-123"
        mock_post.assert_called_once()
        # Verify the token URL contains the tenant ID
        call_args = mock_post.call_args
        assert "oauth2/v2.0/token" in call_args[0][0]

    @patch("app.services.email_service.requests.post")
    def test_get_access_token_failure_raises(self, mock_post, app, db):
        from app.services.email_service import _get_access_token

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid client credentials"
        mock_post.return_value = mock_response

        with app.app_context():
            with pytest.raises(RuntimeError, match="Failed to obtain Graph API token"):
                _get_access_token(app)


# ── Graph API Send Email Tests ────────────────────────────────────


class TestGraphAPISendEmail:
    """Tests for _send_single_email function."""

    @patch("app.services.email_service.requests.post")
    def test_send_single_email_success(self, mock_post, app, db):
        from app.services.email_service import _send_single_email

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        _send_single_email(
            access_token="test-token",
            sender_email="sender@company.com",
            recipient_email="recipient@company.com",
            subject="Test Subject",
            html_body="<p>Test body</p>",
        )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        # Verify the sendMail URL
        assert "sendMail" in call_args[0][0]
        # Verify authorization header
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token"
        # Verify payload structure
        payload = call_args[1]["json"]
        assert payload["message"]["subject"] == "Test Subject"
        assert payload["message"]["body"]["content"] == "<p>Test body</p>"
        assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "recipient@company.com"

    @patch("app.services.email_service.requests.post")
    def test_send_single_email_failure_raises(self, mock_post, app, db):
        import requests as req
        from app.services.email_service import _send_single_email

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = req.HTTPError("403 Forbidden")
        mock_post.return_value = mock_response

        with pytest.raises(req.HTTPError):
            _send_single_email(
                access_token="bad-token",
                sender_email="sender@company.com",
                recipient_email="recipient@company.com",
                subject="Test",
                html_body="<p>Test</p>",
            )


# ── Email Body Content Tests ──────────────────────────────────────


class TestEmailBodyContent:
    """Tests for email body builder functions."""

    def test_publish_email_contains_form_title(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(db.session, owner, title="Q4 Survey")

            subject, html_body = _build_publish_email(form, "http://localhost:5000")

        assert "Q4 Survey" in subject
        assert "Q4 Survey" in html_body
        assert f"http://localhost:5000/form/{form.id}" in html_body

    def test_publish_email_contains_form_link(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(db.session, owner)

            subject, html_body = _build_publish_email(form, "https://feedback.example.com")

        assert f"https://feedback.example.com/form/{form.id}" in html_body

    def test_publish_email_with_deadline(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            closes = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            form = _make_publishable_form(db.session, owner, closes_at=closes)

            _, html_body = _build_publish_email(form, "http://localhost:5000")

        assert "December 31, 2026" in html_body

    def test_publish_email_without_deadline(self, app, db):
        from app.services.email_service import _build_publish_email

        with app.app_context():
            owner = _make_owner(db.session)
            form = _make_publishable_form(db.session, owner, closes_at=None)

            _, html_body = _build_publish_email(form, "http://localhost:5000")

        assert "No deadline set" in html_body

    def test_reminder_email_contains_urgency(self, app, db):
        from app.services.email_service import _build_reminder_email

        with app.app_context():
            owner = _make_owner(db.session)
            closes = datetime.now(timezone.utc) + timedelta(hours=12)
            form = _make_publishable_form(db.session, owner, closes_at=closes)

            subject, html_body = _build_reminder_email(form, "http://localhost:5000")

        assert "Reminder" in subject or "⏰" in subject
        assert "Closing Soon" in html_body or "closing" in html_body.lower()


# ── Notification Send Logic Tests ─────────────────────────────────


class TestNotificationSendLogic:
    """Tests for _send_notifications_for_form with mocked Graph API.

    The _send_notifications_for_form function opens its own app context,
    so we must use the client fixture (which provides an active context)
    and pass form_id as a string so the function re-fetches the form
    inside its own context.
    """

    @patch("app.services.email_service.requests.post")
    def test_dry_run_marks_sent_without_api_call(self, mock_post, client, db, app):
        """When MAIL_ENABLED=false, notifications are marked sent (dry run)."""
        from app.services.email_service import _send_notifications_for_form

        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)
        form_id = form.id

        db.session.add(Notification(
            form_id=form_id,
            recipient_id=emp.id,
            notification_type="publish",
            status="pending",
        ))
        db.session.commit()

        # MAIL_ENABLED is false in testing config
        _send_notifications_for_form(app, form_id, "publish")

        notif = Notification.query.filter_by(form_id=form_id).first()
        assert notif.status == "sent"
        assert notif.sent_at is not None
        assert "dry_run" in notif.error_message

        # No actual HTTP calls were made
        mock_post.assert_not_called()

    @patch("app.services.email_service._get_access_token")
    @patch("app.services.email_service._send_single_email")
    def test_send_with_mail_enabled(self, mock_send, mock_token, client, db, app):
        """When MAIL_ENABLED=true, actual Graph API calls are made."""
        from app.services.email_service import _send_notifications_for_form

        mock_token.return_value = "test-token"

        owner = _make_owner(db.session)
        emp = _make_employee(db.session, "emp@company.com", "Emp")
        form = _make_publishable_form(db.session, owner)
        form_id = form.id

        db.session.add(Notification(
            form_id=form_id,
            recipient_id=emp.id,
            notification_type="publish",
            status="pending",
        ))
        db.session.commit()

        # Temporarily enable mail, then restore
        original = app.config["MAIL_ENABLED"]
        app.config["MAIL_ENABLED"] = True
        app.config["MAIL_SENDER_EMAIL"] = "noreply@company.com"
        try:
            _send_notifications_for_form(app, form_id, "publish")
        finally:
            app.config["MAIL_ENABLED"] = original

        notif = Notification.query.filter_by(form_id=form_id).first()
        assert notif.status == "sent"
        assert notif.sent_at is not None

        mock_token.assert_called_once()
        mock_send.assert_called_once()

    @patch("app.services.email_service._get_access_token")
    def test_token_failure_marks_all_failed(self, mock_token, client, db, app):
        """If token acquisition fails, all notifications are marked failed."""
        from app.services.email_service import _send_notifications_for_form

        mock_token.side_effect = RuntimeError("Token error: bad credentials")

        owner = _make_owner(db.session)
        emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
        emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
        form = _make_publishable_form(db.session, owner)
        form_id = form.id

        for emp in [emp1, emp2]:
            db.session.add(Notification(
                form_id=form_id,
                recipient_id=emp.id,
                notification_type="publish",
                status="pending",
            ))
        db.session.commit()

        original = app.config["MAIL_ENABLED"]
        app.config["MAIL_ENABLED"] = True
        try:
            _send_notifications_for_form(app, form_id, "publish")
        finally:
            app.config["MAIL_ENABLED"] = original

        notifs = Notification.query.filter_by(form_id=form_id).all()
        assert len(notifs) == 2
        assert all(n.status == "failed" for n in notifs)
        assert all("Token error" in n.error_message for n in notifs)

    @patch("app.services.email_service._get_access_token")
    @patch("app.services.email_service._send_single_email")
    def test_partial_send_failure(self, mock_send, mock_token, client, db, app):
        """If one email fails, others still succeed; each status is independent."""
        from app.services.email_service import _send_notifications_for_form

        mock_token.return_value = "test-token"
        # First call succeeds, second raises
        mock_send.side_effect = [None, Exception("SMTP timeout")]

        owner = _make_owner(db.session)
        emp1 = _make_employee(db.session, "emp1@test.com", "Emp1")
        emp2 = _make_employee(db.session, "emp2@test.com", "Emp2")
        form = _make_publishable_form(db.session, owner)
        form_id = form.id

        for emp in [emp1, emp2]:
            db.session.add(Notification(
                form_id=form_id,
                recipient_id=emp.id,
                notification_type="publish",
                status="pending",
            ))
        db.session.commit()

        original = app.config["MAIL_ENABLED"]
        app.config["MAIL_ENABLED"] = True
        app.config["MAIL_SENDER_EMAIL"] = "noreply@company.com"
        try:
            _send_notifications_for_form(app, form_id, "publish")
        finally:
            app.config["MAIL_ENABLED"] = original

        notifs = Notification.query.filter_by(form_id=form_id).order_by(
            Notification.id
        ).all()
        assert len(notifs) == 2
        # First succeeded
        assert notifs[0].status == "sent"
        assert notifs[0].sent_at is not None
        # Second failed
        assert notifs[1].status == "failed"
        assert "SMTP timeout" in notifs[1].error_message

    def test_send_for_nonexistent_form(self, client, db, app):
        """Sending notifications for a missing form logs error and returns."""
        from app.services.email_service import _send_notifications_for_form

        # Should not raise — just log and return
        _send_notifications_for_form(app, "nonexistent-uuid", "publish")

    def test_send_with_no_pending_notifications(self, client, db, app):
        """No pending notifications → no-op."""
        from app.services.email_service import _send_notifications_for_form

        owner = _make_owner(db.session)
        form = _make_publishable_form(db.session, owner)
        form_id = form.id

        _send_notifications_for_form(app, form_id, "publish")
        # No error, no crash


# ── Background Thread Tests ───────────────────────────────────────


class TestBackgroundThreadSpawning:
    """Verify that email sending spawns a daemon background thread."""

    @patch("app.services.email_service.threading.Thread")
    def test_publish_spawns_daemon_thread(self, mock_thread_cls, client, db):
        owner = _make_owner(db.session)
        emp = _make_employee(db.session)
        form = _make_publishable_form(db.session, owner)

        client.post(f"/api/forms/{form.id}/publish")

        mock_thread_cls.assert_called_once()
        thread_instance = mock_thread_cls.return_value
        # Thread should be set as daemon
        assert thread_instance.daemon is True or \
               mock_thread_cls.call_args[1].get("daemon") is True
        thread_instance.start.assert_called_once()

    @patch("app.services.email_service.threading.Thread")
    def test_no_thread_when_no_employees(self, mock_thread_cls, client, db):
        """No background thread is spawned when there are no employees."""
        owner = _make_owner(db.session)
        form = _make_publishable_form(db.session, owner)

        client.post(f"/api/forms/{form.id}/publish")

        mock_thread_cls.assert_not_called()
