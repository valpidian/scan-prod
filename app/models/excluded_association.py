from datetime import datetime

from app.extensions import db


class ExcludedAssociation(db.Model):
    __tablename__ = "excluded_associations"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False, index=True)
    excluded_product_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("product_id", "excluded_product_id", name="uq_excluded_pair"),
    )
