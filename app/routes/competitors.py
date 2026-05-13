from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app.models.competitor import Competitor
from app.services.competitor_service import create_or_get_competitor
from app.services.notification_service import create_notification, recent_notifications, unread_notifications


bp = Blueprint("competitors", __name__)


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        source_url = request.form.get("source_url", "").strip()
        if not source_url:
            flash("Completeaza URL-ul competitorului.", "warning")
            return redirect(url_for("competitors.index"))

        try:
            competitor, created = create_or_get_competitor(source_url)
            if created:
                create_notification(
                    "Competitor adaugat",
                    f"{competitor.internal_code} a fost generat pentru {competitor.display_name}.",
                    "success",
                )
                flash(
                    f"Competitor creat: {competitor.internal_code} pentru {competitor.display_name}.",
                    "success",
                )
            else:
                flash(
                    f"Competitor existent: {competitor.internal_code} pentru {competitor.display_name}.",
                    "info",
                )
        except Exception as exc:
            current_app.logger.exception("Create competitor failed")
            flash(str(exc), "danger")
        return redirect(url_for("competitors.index"))

    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    return render_template(
        "competitors/index.html",
        competitors=competitors,
        unread_notifications=unread_notifications(),
        recent_notifications=recent_notifications(),
    )
