from datetime import datetime

from app.extensions import db


class Competitor(db.Model):
    __tablename__ = "competitors"

    id = db.Column(db.Integer, primary_key=True)
    internal_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    source_url = db.Column(db.Text, unique=True, nullable=False)
    source_host = db.Column(db.String(255), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def as_dict(self):
        return {
            "id": self.id,
            "internal_code": self.internal_code,
            "source_url": self.source_url,
            "source_host": self.source_host,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
