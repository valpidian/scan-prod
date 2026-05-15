import os
import secrets
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    _secret = os.getenv("SECRET_KEY", "")
    SECRET_KEY = _secret if _secret and _secret != "dev-secret-key-change-me" else secrets.token_hex(32)
    DEBUG = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5055"))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'scan_pret.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite: timeout la lock contention (scraping thread + web thread)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30},
        "pool_pre_ping": True,
    }
    # Cheie pentru criptare API keys (generata automat daca lipseste din .env)
    _fernet_key = os.getenv("FERNET_KEY", "")
    FERNET_KEY = _fernet_key.encode() if _fernet_key else None
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
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
    # Paginare
    PRODUCTS_PER_PAGE = int(os.getenv("PRODUCTS_PER_PAGE", "50"))
