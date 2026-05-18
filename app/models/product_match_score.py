import json
from datetime import datetime

from app.extensions import db


class ProductMatchScore(db.Model):
    __tablename__ = "product_match_scores"

    id                 = db.Column(db.Integer, primary_key=True)
    product_id         = db.Column(db.Integer, nullable=False, index=True)
    matched_product_id = db.Column(db.Integer, nullable=False, index=True)
    score              = db.Column(db.Float, nullable=False)
    rule_breakdown     = db.Column(db.Text, nullable=True)   # JSON {rule_label: score}
    status             = db.Column(db.String(20), nullable=False, default="pending", index=True)
    # pending | confirmed | rejected
    created_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at       = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("product_id", "matched_product_id", name="uq_match_pair"),
    )

    def get_breakdown(self):
        try:
            return json.loads(self.rule_breakdown or "{}")
        except Exception:
            return {}

    def as_dict(self):
        return {
            "id":                 self.id,
            "product_id":         self.product_id,
            "matched_product_id": self.matched_product_id,
            "score":              self.score,
            "rule_breakdown":     self.get_breakdown(),
            "status":             self.status,
            "created_at":         self.created_at.strftime("%d.%m.%Y %H:%M"),
            "confirmed_at":       self.confirmed_at.strftime("%d.%m.%Y %H:%M") if self.confirmed_at else None,
        }

    @classmethod
    def upsert(cls, product_id, matched_product_id, score, breakdown_dict):
        """Insert or update (pe baza product_id + matched_product_id)."""
        existing = cls.query.filter_by(
            product_id=product_id, matched_product_id=matched_product_id
        ).first()
        if existing:
            existing.score = score
            existing.rule_breakdown = json.dumps(breakdown_dict, ensure_ascii=False)
            existing.status = "pending"
            existing.created_at = datetime.utcnow()
            existing.confirmed_at = None
            return existing
        obj = cls(
            product_id=product_id,
            matched_product_id=matched_product_id,
            score=score,
            rule_breakdown=json.dumps(breakdown_dict, ensure_ascii=False),
            status="pending",
        )
        db.session.add(obj)
        return obj
