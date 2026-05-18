from sqlalchemy import exists, or_

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct


def build_query(filters):
    query = CompetitorProduct.query

    competitor = filters.get("competitor")
    search = filters.get("q")
    sort = filters.get("sort", "title")
    direction = filters.get("direction", "asc")
    ai_status = filters.get("ai_status", "").strip()

    if competitor:
        query = query.filter_by(cod_competitor=competitor)

    if ai_status:
        from app.models.ai_association_log import AIAssociationLog
        if ai_status == "neprocesate":
            query = query.filter(
                ~exists().where(AIAssociationLog.product_id == CompetitorProduct.id)
            )
        elif ai_status == "procesate":
            query = query.filter(
                exists().where(AIAssociationLog.product_id == CompetitorProduct.id)
            )
        elif ai_status == "confirmate":
            query = query.filter(
                exists().where(
                    (AIAssociationLog.product_id == CompetitorProduct.id)
                    & (AIAssociationLog.status == "confirmed")
                )
            )

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
    if sort == 'cod_competitor':
        sort_column = CompetitorProduct.cod_competitor
    elif sort == 'asociere':
        sort_column = CompetitorProduct.asociere
    if direction == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    return query.order_by(sort_column)


def complex_search(query_text, limit=None):
    from app.models.search_config import SearchConfig
    cfg = SearchConfig.get()

    if len(query_text) < cfg.min_query_length:
        return []

    actual_limit = limit or cfg.search_limit
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
        .limit(actual_limit)
        .all()
    )

    codes = list({p.cod_competitor for p in products})
    competitors_map = {
        c.internal_code: c
        for c in Competitor.query.filter(Competitor.internal_code.in_(codes)).all()
    }
    return [{"product": p, "competitor": competitors_map.get(p.cod_competitor)} for p in products]
