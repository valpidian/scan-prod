import json
from datetime import datetime

from app.extensions import db

_DEFAULTS = [
    dict(name="SKU exact",                rule_type="sku_exact",        weight=1.00, is_active=True,  params=None,
         description="SKU normalizat identic => potrivire sigura"),
    dict(name="SKU normalizat (contine)",  rule_type="sku_partial",      weight=0.85, is_active=True,  params=None,
         description="SKU sursa continut in SKU candidat sau invers"),
    dict(name="SKU in titlu / descriere",  rule_type="sku_in_title",     weight=0.80, is_active=True,  params=None,
         description="SKU sursa apare in titlul sau descrierea candidatului (bidirectional)"),
    dict(name="Cod model tehnic",          rule_type="model_match",      weight=0.80, is_active=True,  params=None,
         description="Cod model extras din SKU/titlu exista in candidat"),
    dict(name="Similaritate titlu",        rule_type="title_similarity", weight=0.65, is_active=True,
         params=json.dumps({"threshold": 0.72}),
         description="Ratio de similaritate text intre titluri >= threshold"),
    dict(name="Brand identic (bonus)",     rule_type="brand_bonus",      weight=0.10, is_active=True,  params=None,
         description="Bonus aditiv cand brand-ul coincide (se aplica doar daca scor de baza > 0)"),
    dict(name="Interval pret (bonus)",     rule_type="price_range",      weight=0.05, is_active=False,
         params=json.dumps({"tolerance_pct": 15}),
         description="Bonus aditiv daca pretul candidatului este in intervalul +/- X% fata de sursa"),
]


class MatchingRule(db.Model):
    __tablename__ = "matching_rules"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    rule_type   = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    weight      = db.Column(db.Float, nullable=False, default=1.0)
    is_active   = db.Column(db.Boolean, nullable=False, default=True)
    is_system   = db.Column(db.Boolean, nullable=False, default=False)
    params      = db.Column(db.Text, nullable=True)   # JSON
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def get_params(self):
        try:
            return json.loads(self.params or "{}")
        except Exception:
            return {}

    def as_dict(self):
        return {
            "id":          self.id,
            "name":        self.name,
            "rule_type":   self.rule_type,
            "description": self.description or "",
            "weight":      self.weight,
            "is_active":   self.is_active,
            "is_system":   self.is_system,
            "params":      self.get_params(),
        }

    @classmethod
    def seed_defaults(cls):
        if cls.query.count() > 0:
            return
        db.session.add_all([
            cls(is_system=True, **d) for d in _DEFAULTS
        ])
        db.session.commit()

    @classmethod
    def get_active(cls):
        return cls.query.filter_by(is_active=True).order_by(cls.id.asc()).all()
