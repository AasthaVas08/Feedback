"""Notification log endpoints.

Routes
------
GET /api/forms/<id>/notifications — list all notifications for a form
GET /api/notifications/stats      — aggregate notification statistics
"""

from flask import jsonify

from app import db
from app.api import api_bp
from app.models import Form, Notification


def _serialize_notification(n: Notification) -> dict:
    """Convert a Notification model to a JSON-safe dict."""
    return {
        "id": n.id,
        "form_id": n.form_id,
        "recipient_id": n.recipient_id,
        "recipient_name": n.recipient.name if n.recipient else None,
        "recipient_email": n.recipient.email if n.recipient else None,
        "notification_type": n.notification_type,
        "status": n.status,
        "error_message": n.error_message,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@api_bp.route("/forms/<form_id>/notifications", methods=["GET"])
def list_form_notifications(form_id: str):
    """List all notifications for a specific form."""
    form = db.session.get(Form, form_id)
    if form is None:
        return jsonify({"error": "Form not found"}), 404

    notifications = (
        Notification.query
        .filter_by(form_id=form_id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    return jsonify({
        "form_id": form_id,
        "total": len(notifications),
        "sent": sum(1 for n in notifications if n.status == "sent"),
        "failed": sum(1 for n in notifications if n.status == "failed"),
        "pending": sum(1 for n in notifications if n.status == "pending"),
        "notifications": [_serialize_notification(n) for n in notifications],
    })


@api_bp.route("/notifications/stats", methods=["GET"])
def notification_stats():
    """Aggregate notification statistics across all forms."""
    total = Notification.query.count()
    sent = Notification.query.filter_by(status="sent").count()
    failed = Notification.query.filter_by(status="failed").count()
    pending = Notification.query.filter_by(status="pending").count()

    publish_count = Notification.query.filter_by(notification_type="publish").count()
    reminder_count = Notification.query.filter_by(notification_type="reminder").count()

    return jsonify({
        "total": total,
        "sent": sent,
        "failed": failed,
        "pending": pending,
        "by_type": {
            "publish": publish_count,
            "reminder": reminder_count,
        },
    })
