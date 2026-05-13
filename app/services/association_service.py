from sqlalchemy import or_

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct


def find_candidates(source_product, limit=20):
    terms = []
    if source_product.title:
        words = [w for w in source_product.title.split() if len(w) > 3]
        terms.extend(words[:4])
    if source_product.brand:
        terms.append(source_product.brand)
    if source_product.sku:
        terms.append(source_product.sku)

    if not terms:
        return []

    candidates = (
        CompetitorProduct.query
        .filter(CompetitorProduct.cod_competitor != source_product.cod_competitor)
        .filter(or_(
            *[CompetitorProduct.title.ilike(f"%{t}%") for t in terms],
            *[CompetitorProduct.sku.ilike(f"%{t}%") for t in terms],
            *([CompetitorProduct.brand.ilike(f"%{source_product.brand}%")] if source_product.brand else []),
        ))
        .limit(limit)
        .all()
    )

    codes = list({c.cod_competitor for c in candidates})
    comp_map = {
        c.internal_code: c
        for c in Competitor.query.filter(Competitor.internal_code.in_(codes)).all()
    }

    return [{"product": c, "competitor": comp_map.get(c.cod_competitor)} for c in candidates]
