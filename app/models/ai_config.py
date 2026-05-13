from app.extensions import db


class AIConfig(db.Model):
    __tablename__ = "ai_config"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, default="openai")
    api_key = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(100), nullable=False, default="gpt-4o-mini")
    prompt_template = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    @staticmethod
    def get_active():
        return AIConfig.query.filter_by(is_active=True).first()
