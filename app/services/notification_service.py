from app.extensions import db
from app.models.notification import Notification
from app.utils.logging_helpers import audit


def create_notification(title, message, level="info"):
    notification = Notification(title=title, message=message, level=level)
    db.session.add(notification)
    db.session.commit()
    audit("Notificare creata | level=%s | title=%s", level, title)
    return notification


def unread_notifications():
    return Notification.query.filter_by(is_read=False).count()


def recent_notifications(limit=10):
    return Notification.query.order_by(Notification.created_at.desc()).limit(limit).all()


def mark_notification_read(notification_id):
    notification = Notification.query.get(notification_id)
    if notification:
        notification.is_read = True
        db.session.commit()
    return notification
