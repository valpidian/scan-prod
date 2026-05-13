import logging

from flask import current_app, has_app_context


def get_named_logger(name):
    if has_app_context():
        loggers = current_app.extensions.get("scanpret_loggers", {})
        logger = loggers.get(name)
        if logger is not None:
            return logger
    return logging.getLogger(f"scanpret.{name}")


def audit(message, *args, **kwargs):
    get_named_logger("audit").info(message, *args, **kwargs)


def app_log(message, *args, **kwargs):
    get_named_logger("app").info(message, *args, **kwargs)

