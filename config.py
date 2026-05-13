import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5055"))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'scan_pret.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    UPLOAD_FOLDER = BASE_DIR / "uploads" / "imports"
    EXPORT_FOLDER = BASE_DIR / "uploads" / "exports"
    LOG_FOLDER = BASE_DIR / "logs"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "1048576"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))
    APP_LOG_FILE = os.getenv("APP_LOG_FILE", str(BASE_DIR / "logs" / "app.log"))
    ACCESS_LOG_FILE = os.getenv("ACCESS_LOG_FILE", str(BASE_DIR / "logs" / "access.log"))
    ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", str(BASE_DIR / "logs" / "error.log"))
    AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", str(BASE_DIR / "logs" / "audit.log"))
