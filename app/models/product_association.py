from datetime import datetime
from app.extensions import db


class ProductAssociation(db.Model):
    """Asocieri bidirectionale intre produse.
    Stocat canonical: product_id < associated_id pentru a evita duplicatele.
    Query-urile folosesc OR pe ambele coloane.
    """
    __tablename__ = "product_associations"

    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, db.ForeignKey("competitor_products.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    associated_id  = db.Column(db.Integer, db.ForeignKey("competitor_products.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("product_id", "associated_id", name="uq_product_association"),
    )

    # ── Helpers statice ────────────────────────────────────────────────────

    @staticmethod
    def _canonical(p1_id, p2_id):
        return (min(p1_id, p2_id), max(p1_id, p2_id))

    @classmethod
    def add(cls, p1_id, p2_id):
        """Adauga asociere (idempotent)."""
        low, high = cls._canonical(p1_id, p2_id)
        if low == high:
            return
        exists = cls.query.filter_by(product_id=low, associated_id=high).first()
        if not exists:
            db.session.add(cls(product_id=low, associated_id=high))

    @classmethod
    def remove(cls, p1_id, p2_id):
        """Sterge asociere daca exista."""
        low, high = cls._canonical(p1_id, p2_id)
        cls.query.filter_by(product_id=low, associated_id=high).delete()

    @classmethod
    def get_associated_ids(cls, product_id):
        """Returneaza lista de ID-uri ale produselor asociate."""
        rows = cls.query.filter(
            (cls.product_id == product_id) | (cls.associated_id == product_id)
        ).all()
        return [
            r.associated_id if r.product_id == product_id else r.product_id
            for r in rows
        ]

    @classmethod
    def are_associated(cls, p1_id, p2_id):
        low, high = cls._canonical(p1_id, p2_id)
        return cls.query.filter_by(product_id=low, associated_id=high).first() is not None
