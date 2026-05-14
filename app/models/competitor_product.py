from datetime import datetime

from app.extensions import db


class CompetitorProduct(db.Model):
    __tablename__ = "competitor_products"

    id = db.Column(db.Integer, primary_key=True)
    cod_competitor = db.Column(db.String(50), nullable=False, index=True)
    sku = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    pret = db.Column(db.Float, nullable=True)
    brand = db.Column(db.String(120), nullable=True, index=True)
    descriere = db.Column(db.Text, nullable=True)
    asociere = db.Column(db.Text, nullable=True, default="")
    pret_preluat = db.Column(db.Float, nullable=True)  # pret preluat manual de la produsul asociat
    categorie = db.Column(db.String(120), nullable=True, index=True)
    imported_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def as_dict(self):
        return {
            "id": self.id,
            "cod_competitor": self.cod_competitor,
            "sku": self.sku,
            "title": self.title,
            "pret": self.pret,
            "brand": self.brand,
            "descriere": self.descriere,
            "asociere": self.asociere or "",
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
        }

