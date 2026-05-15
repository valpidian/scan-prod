from datetime import datetime
from app.extensions import db


class ScrapingJob(db.Model):
    __tablename__ = "scraping_jobs"

    id              = db.Column(db.Integer, primary_key=True)
    job_id          = db.Column(db.String(32), unique=True, index=True, nullable=False)
    competitor_code = db.Column(db.String(32), index=True, nullable=False)
    status          = db.Column(db.String(20), nullable=False, default="running")
    # running / done / stopped / error
    stop_requested  = db.Column(db.Boolean, nullable=False, default=False)
    total           = db.Column(db.Integer, default=0)
    inserted        = db.Column(db.Integer, default=0)
    updated         = db.Column(db.Integer, default=0)
    errors          = db.Column(db.Integer, default=0)
    started_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at     = db.Column(db.DateTime, nullable=True)

    @classmethod
    def get_running(cls, competitor_code):
        return cls.query.filter_by(
            competitor_code=competitor_code, status="running"
        ).order_by(cls.started_at.desc()).first()

    @classmethod
    def get_by_job_id(cls, job_id):
        return cls.query.filter_by(job_id=job_id).first()

    def as_dict(self):
        return {
            "job_id":     self.job_id,
            "status":     self.status,
            "total":      self.total,
            "inserted":   self.inserted,
            "updated":    self.updated,
            "errors":     self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
