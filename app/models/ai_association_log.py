from datetime import datetime

from app.extensions import db


class AIAssociationLog(db.Model):
    __tablename__ = "ai_association_log"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False, index=True)
    competitor_target = db.Column(db.String(200), nullable=True)  # comma-separated codes or None = all
    matched_product_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, index=True)  # no_match | found | confirmed | rejected
    confidence = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    prompt_name = db.Column(db.String(100), nullable=True)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
