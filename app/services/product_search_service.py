from sqlalchemy import or_

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct


def build_query(filters):
    query = CompetitorProduct.query

    competitor = filters.get("competitor")
    search = filters.get("q")
    sort = filters.get("sort", "title")
    direction = filters.get("direction", "asc")

    if competitor:
        query = query.filter_by(cod_competitor=competitor)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                CompetitorProduct.cod_competitor.ilike(pattern),
                CompetitorProduct.sku.ilike(pattern),
                CompetitorProduct.title.ilike(pattern),
                CompetitorProduct.brand.ilike(pattern),
                CompetitorProduct.descriere.ilike(pattern),
            )
        )

    sort_column = getattr(CompetitorProduct, sort, CompetitorProduct.title)
    if direction == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    return query.order_by(sort_column)


def complex_search(query_text, limit=100):
    pattern = f"%{query_text}%"
    products = (
        CompetitorProduct.query.filter(
            or_(
                CompetitorProduct.sku.ilike(pattern),
                CompetitorProduct.title.ilike(pattern),
                CompetitorProduct.descriere.ilike(pattern),
                CompetitorProduct.brand.ilike(pattern),
                CompetitorProduct.cod_competitor.ilike(pattern),
            )
        )
        .order_by(CompetitorProduct.title.asc())
        .limit(limit)
        .all()
    )

    # Aduce toti competitorii intr-un singur query si face map dupa internal_code
    codes = list({p.cod_competitor for p in products})
    competitors_map = {
        c.internal_code: c
        for c in Competitor.query.filter(Competitor.internal_code.in_(codes)).all()
    }

    results = []
    for p in products:
        results.append({
            "product": p,
            "competitor": competitors_map.get(p.cod_competitor),
        })
    return results
