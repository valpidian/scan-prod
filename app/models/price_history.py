from datetime import datetime

from app.extensions import db


class PriceHistory(db.Model):
    __tablename__ = "price_history"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False, index=True)
    pret = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    sursa = db.Column(db.String(20), nullable=False, default="import")  # "import" | "manual"
