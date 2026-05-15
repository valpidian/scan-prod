from flask import current_app
from app.extensions import db


def _fernet():
    """Returneaza instanta Fernet sau None daca cheia nu e configurata."""
    try:
        from cryptography.fernet import Fernet
        key = current_app.config.get("FERNET_KEY")
        if key:
            return Fernet(key)
    except Exception:
        pass
    return None


class AIConfig(db.Model):
    __tablename__ = "ai_config"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, default="openai")
    _api_key = db.Column("api_key", db.Text, nullable=True)
    model = db.Column(db.String(100), nullable=False, default="gpt-4o-mini")
    prompt_template = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def api_key(self):
        raw = self._api_key
        if not raw:
            return None
        f = _fernet()
        if f and raw.startswith("gAA"):  # prefix tipic Fernet
            try:
                return f.decrypt(raw.encode()).decode()
            except Exception:
                pass
        return raw

    @api_key.setter
    def api_key(self, value):
        if not value:
            self._api_key = None
            return
        f = _fernet()
        if f:
            self._api_key = f.encrypt(value.encode()).decode()
        else:
            self._api_key = value

    @staticmethod
    def get_active():
        return AIConfig.query.filter_by(is_active=True).first()
