from __future__ import annotations

import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import g, has_request_context, request
from flask.signals import got_request_exception


def _build_rotating_handler(path, level, formatter, max_bytes, backup_count):
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _prepare_logger(name, level):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    return logger


def configure_logging(app):
    log_dir = Path(app.config["LOG_FOLDER"])
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, app.config["LOG_LEVEL"], logging.INFO)
    max_bytes = app.config["LOG_MAX_BYTES"]
    backup_count = app.config["LOG_BACKUP_COUNT"]

    app_logger = _prepare_logger(app.import_name, log_level)
    access_logger = _prepare_logger("scanpret.access", logging.INFO)
    error_logger = _prepare_logger("scanpret.error", logging.ERROR)
    audit_logger = _prepare_logger("scanpret.audit", logging.INFO)

    app_logger.addHandler(
        _build_rotating_handler(
            app.config["APP_LOG_FILE"],
            log_level,
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"),
            max_bytes,
            backup_count,
        )
    )
    access_logger.addHandler(
        _build_rotating_handler(
            app.config["ACCESS_LOG_FILE"],
            logging.INFO,
            logging.Formatter("%(asctime)s | %(message)s"),
            max_bytes,
            backup_count,
        )
    )
    error_logger.addHandler(
        _build_rotating_handler(
            app.config["ERROR_LOG_FILE"],
            logging.ERROR,
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(module)s:%(lineno)d | %(message)s"
            ),
            max_bytes,
            backup_count,
        )
    )
    audit_logger.addHandler(
        _build_rotating_handler(
            app.config["AUDIT_LOG_FILE"],
            logging.INFO,
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"),
            max_bytes,
            backup_count,
        )
    )

    app.extensions["scanpret_loggers"] = {
        "app": app_logger,
        "access": access_logger,
        "error": error_logger,
        "audit": audit_logger,
    }

    logging.captureWarnings(True)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.before_request
    def capture_request_start():
        g.request_started_at = time.perf_counter()
        g.request_id = uuid.uuid4().hex[:12]

    @app.after_request
    def log_request(response):
        request_id = getattr(g, "request_id", uuid.uuid4().hex[:12])
        response.headers["X-Request-ID"] = request_id

        duration_ms = 0.0
        started_at = getattr(g, "request_started_at", None)
        if started_at is not None:
            duration_ms = (time.perf_counter() - started_at) * 1000

        client_ip = (
            request.headers.get("X-Forwarded-For", request.remote_addr) or "-"
        ).split(",")[0].strip()
        user_agent = (request.headers.get("User-Agent") or "-")[:160]
        path = request.full_path if request.query_string else request.path
        access_logger.info(
            "request_id=%s | %s %s | status=%s | duration_ms=%.2f | bytes=%s | ip=%s | ua=%s",
            request_id,
            request.method,
            path.rstrip("?"),
            response.status_code,
            duration_ms,
            response.calculate_content_length() or response.content_length or 0,
            client_ip,
            user_agent,
        )
        return response

    @got_request_exception.connect_via(app)
    def log_exception(sender, exception, **extra):
        request_id = getattr(g, "request_id", uuid.uuid4().hex[:12]) if has_request_context() else uuid.uuid4().hex[:12]
        if has_request_context():
            error_logger.exception(
                "request_id=%s | %s %s | unhandled exception",
                request_id,
                request.method,
                request.path,
            )
        else:
            error_logger.exception("request_id=%s | unhandled exception", request_id)

    app_logger.info(
        "Application started | host=%s | port=%s | debug=%s",
        app.config["HOST"],
        app.config["PORT"],
        app.config["DEBUG"],
    )
