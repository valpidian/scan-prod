from app.extensions import db


class SearchConfig(db.Model):
    __tablename__ = "search_config"

    id = db.Column(db.Integer, primary_key=True)

    # Cautare generala
    min_query_length = db.Column(db.Integer, default=2)       # minim caractere pentru a declansa cautarea
    search_limit = db.Column(db.Integer, default=100)         # max rezultate returnate

    # Candidati pentru AI
    candidate_limit = db.Column(db.Integer, default=20)       # max candidati trimisi la AI
    candidate_fetch_multiplier = db.Column(db.Integer, default=3)  # factor fetch DB inainte de re-ranking

    # Scoring matching
    min_score_filter = db.Column(db.Float, default=0.0)       # scor minim pentru a aparea in candidati
    sure_match_threshold = db.Column(db.Float, default=0.85)  # prag potrivire sigura
    sku_exact_score = db.Column(db.Float, default=1.0)        # scor SKU exact
    sku_partial_score = db.Column(db.Float, default=0.85)     # scor SKU partial
    model_match_score = db.Column(db.Float, default=0.80)     # scor model tehnic comun
    brand_bonus = db.Column(db.Float, default=0.10)           # bonus brand identic
    category_bonus = db.Column(db.Float, default=0.05)        # bonus categorie identica

    # Titluri cuvinte semnificative
    title_word_min_length = db.Column(db.Integer, default=3)  # lungime minima cuvant din titlu
    title_word_count = db.Column(db.Integer, default=4)       # nr cuvinte din titlu folosite

    # AI confidence
    ai_min_confidence = db.Column(db.Float, default=0.6)      # sub acest prag AI returneaza gol

    @staticmethod
    def get():
        cfg = SearchConfig.query.first()
        if not cfg:
            cfg = SearchConfig()
            db.session.add(cfg)
            db.session.commit()
        return cfg
