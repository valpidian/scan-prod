from flask import Blueprint, redirect, render_template, url_for

from app.services.notification_service import mark_notification_read, recent_notifications


bp = Blueprint("notifications", __name__)


@bp.route("/")
def list_view():
    return render_template("notifications/list.html", notifications=recent_notifications(100))


@bp.route("/read/<int:notification_id>", methods=["POST"])
def read(notification_id):
    mark_notification_read(notification_id)
    return redirect(url_for("notifications.list_view"))
