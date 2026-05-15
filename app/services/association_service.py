from sqlalchemy import or_

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.services.matching_service import rank_candidates


def sync_pret_preluat(product):
    """Preia pretul minim din produsele asociate si il scrie in pret_preluat."""
    ids = [x for x in (product.asociere or "").split(";") if x]
    if not ids:
        return
    associated = CompetitorProduct.query.filter(
        CompetitorProduct.id.in_([int(i) for i in ids if i.isdigit()]),
        CompetitorProduct.pret.isnot(None),
    ).all()
    if associated:
        min_product = min(associated, key=lambda p: p.pret)
        product.pret_preluat = min_product.pret
        product.pret_preluat_sursa = min_product.cod_competitor
        product.pret_preluat_asociat_id = min_product.id


def find_candidates(source_product, limit=None, target_competitors=None):
    from app.models.search_config import SearchConfig
    cfg = SearchConfig.get()

    actual_limit = limit or cfg.candidate_limit
    fetch_limit = actual_limit * cfg.candidate_fetch_multiplier

    terms = []
    if source_product.title:
        words = [w for w in source_product.title.split() if len(w) > cfg.title_word_min_length]
        terms.extend(words[:cfg.title_word_count])
    if source_product.brand:
        terms.append(source_product.brand)
    if source_product.sku:
        terms.append(source_product.sku)

    if not terms:
        return []

    query = CompetitorProduct.query.filter(
        CompetitorProduct.cod_competitor != source_product.cod_competitor
    )

    # Filtru optional pe competitori tinta
    if target_competitors:
        query = query.filter(CompetitorProduct.cod_competitor.in_(target_competitors))

    db_candidates = (
        query.filter(or_(
            *[CompetitorProduct.title.ilike(f"%{t}%") for t in terms],
            *[CompetitorProduct.sku.ilike(f"%{t}%") for t in terms],
            *([CompetitorProduct.brand.ilike(f"%{source_product.brand}%")] if source_product.brand else []),
        ))
        .limit(fetch_limit)
        .all()
    )

    codes = list({c.cod_competitor for c in db_candidates})
    comp_map = {
        c.internal_code: c
        for c in Competitor.query.filter(Competitor.internal_code.in_(codes)).all()
    }

    rows = [{"product": c, "competitor": comp_map.get(c.cod_competitor)} for c in db_candidates]
    scored = rank_candidates(source_product, rows, min_score=cfg.min_score_filter)
    scored_ids = {ms.product_id: ms.score for ms in scored}
    rows_sorted = sorted(rows, key=lambda r: scored_ids.get(r["product"].id, 0), reverse=True)
    for row in rows_sorted:
        row["match_score"] = scored_ids.get(row["product"].id, 0)

    return rows_sorted[:actual_limit]
