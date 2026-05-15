from datetime import datetime
from app.extensions import db


class ScrapingUrl(db.Model):
    __tablename__ = "scraping_urls"

    id = db.Column(db.Integer, primary_key=True)
    competitor_code = db.Column(db.String(32), nullable=False, index=True)
    url = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    # pending | scraped | error
    product_id = db.Column(db.Integer, db.ForeignKey("competitor_products.id"), nullable=True)
    error_msg = db.Column(db.Text, nullable=True)
    discovered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    scraped_at = db.Column(db.DateTime, nullable=True)

    product = db.relationship("CompetitorProduct", backref="scraping_url", foreign_keys=[product_id])
