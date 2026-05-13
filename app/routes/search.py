from flask import Blueprint, render_template, request

from app.services.notification_service import recent_notifications, unread_notifications
from app.services.product_search_service import complex_search


bp = Blueprint("search", __name__)


@bp.route("/", methods=["GET", "POST"])
def advanced():
    query_text = request.values.get("q", "").strip()
    results = complex_search(query_text) if query_text else []
    return render_template(
        "search/advanced.html",
        query_text=query_text,
        results=results,
        unread_notifications=unread_notifications(),
        recent_notifications=recent_notifications(),
    )

