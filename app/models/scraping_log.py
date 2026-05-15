from datetime import datetime
from app.extensions import db


class ScrapingLog(db.Model):
    __tablename__ = "scraping_logs"

    id            = db.Column(db.Integer, primary_key=True)
    competitor_code = db.Column(db.String(32), nullable=False, index=True)
    job_id        = db.Column(db.String(40), nullable=False, index=True)  # timestamp-based
    url           = db.Column(db.Text, nullable=True)
    status        = db.Column(db.String(20), nullable=False)  # ok | error | skip | start | done
    message       = db.Column(db.Text, nullable=True)
    duration_ms   = db.Column(db.Integer, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
