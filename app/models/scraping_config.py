from datetime import datetime
from app.extensions import db


class ScrapingConfig(db.Model):
    __tablename__ = "scraping_configs"

    id              = db.Column(db.Integer, primary_key=True)
    competitor_code = db.Column(db.String(32), nullable=False, unique=True, index=True)

    # Surse
    sources    = db.Column(db.Text, nullable=True)
    url_filter = db.Column(db.String(512), nullable=True)

    # Selectori CSS
    sel_sku       = db.Column(db.String(512), nullable=True)
    sel_title     = db.Column(db.String(512), nullable=True)
    sel_pret      = db.Column(db.String(512), nullable=True)
    sel_brand     = db.Column(db.String(512), nullable=True)
    sel_descriere = db.Column(db.String(512), nullable=True)
    sel_categorie = db.Column(db.String(512), nullable=True)

    # Parametri scraping
    delay            = db.Column(db.Float,   nullable=False, default=1.0)
    randomize_delay  = db.Column(db.Boolean, nullable=False, default=True)   # delay ± 50%
    timeout          = db.Column(db.Integer, nullable=False, default=15)
    max_retries      = db.Column(db.Integer, nullable=False, default=2)
    retry_delay      = db.Column(db.Float,   nullable=False, default=5.0)
    user_agent       = db.Column(db.String(512), nullable=True)               # None = rotatie automata
    respect_robots   = db.Column(db.Boolean, nullable=False, default=False)
    block_resources  = db.Column(db.Boolean, nullable=False, default=True)   # nu incarca imagini/CSS/JS

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def selectors(self):
        return {
            "sku":       self.sel_sku,
            "title":     self.sel_title,
            "pret":      self.sel_pret,
            "brand":     self.sel_brand,
            "descriere": self.sel_descriere,
            "categorie": self.sel_categorie,
        }
