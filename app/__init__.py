from pathlib import Path

from flask import Flask, url_for

from config import Config
from app.extensions import db
from app.logging_setup import configure_logging


def create_app(config_object=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["EXPORT_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["LOG_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path("instance").mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from app.extensions import csrf, limiter, migrate
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

    register_blueprints(app)
    configure_logging(app)
    register_context_processors(app)
    register_error_handlers(app)
    register_template_filters(app)

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()

    return app


def register_template_filters(app):
    import re
    from markupsafe import Markup, escape

    @app.template_filter('highlight')
    def highlight_filter(text, query):
        if not text or not query:
            return escape(text or '')
        escaped_text = str(escape(text))
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        result = pattern.sub(
            lambda m: f'<mark class="bg-warning px-0">{m.group()}</mark>',
            escaped_text
        )
        return Markup(result)


def register_blueprints(app):
    from app.routes.ai_association import bp as ai_bp
    from app.routes.cleanup import bp as cleanup_bp
    from app.routes.competitors import bp as competitors_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.import_export import bp as import_export_bp
    from app.routes.notifications import bp as notifications_bp
    from app.routes.products import bp as products_bp
    from app.routes.search import bp as search_bp

    app.register_blueprint(competitors_bp, url_prefix="/competitors")
    app.register_blueprint(cleanup_bp, url_prefix="/cleanup")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(import_export_bp, url_prefix="/io")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(search_bp, url_prefix="/search")
    app.register_blueprint(ai_bp, url_prefix="/ai")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")


def register_error_handlers(app):
    from app.utils.logging_helpers import get_named_logger

    @app.errorhandler(404)
    def not_found(error):
        return (
            "<h1>404</h1><p>Pagina nu a fost gasita.</p>",
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        get_named_logger("error").exception("Internal server error: %s", error)
        return (
            "<h1>500</h1><p>A aparut o eroare interna.</p>",
            500,
        )


def register_context_processors(app):
    from app.models.competitor import Competitor
    from app.services.notification_service import recent_notifications, unread_notifications

    @app.context_processor
    def inject_navigation():
        workflow_steps = [
            {
                "number": 1,
                "title": "Competitori",
                "subtitle": "Adauga URL → cod intern",
                "url": url_for("competitors.index"),
                "endpoints": {"competitors.index"},
            },
            {
                "number": 2,
                "title": "Import CSV",
                "subtitle": "Incarcare fisier competitor",
                "url": url_for("import_export.import_view"),
                "endpoints": {"import_export.import_view"},
            },
            {
                "number": 3,
                "title": "Curatare date",
                "subtitle": "Elimina HTML, URL-uri, fisiere",
                "url": url_for("cleanup.index"),
                "endpoints": {"cleanup.index"},
            },
            {
                "number": 4,
                "title": "Vizualizare produse",
                "subtitle": "Filtrare, sortare, editare",
                "url": url_for("products.list_view"),
                "endpoints": {"products.list_view"},
            },
            {
                "number": 5,
                "title": "Cautare produs",
                "subtitle": "SKU, titlu, descriere, brand",
                "url": url_for("search.advanced"),
                "endpoints": {"search.advanced"},
            },
            {
                "number": 6,
                "title": "Asociere AI",
                "subtitle": "Potrivire automata produse",
                "url": url_for("products.list_view"),
                "endpoints": {"ai_association.associate", "ai_association.config"},
            },
            {
                "number": 7,
                "title": "Export CSV",
                "subtitle": "Download per competitor",
                "url": url_for("import_export.export_view"),
                "endpoints": {"import_export.export_view"},
            },
        ]

        sidebar_competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()

        return {
            "recent_notifications": recent_notifications(),
            "unread_notifications": unread_notifications(),
            "workflow_steps": workflow_steps,
            "sidebar_competitors": sidebar_competitors,
        }
