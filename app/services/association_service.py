from sqlalchemy import or_

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.services.matching_service import rank_candidates


def sync_pret_preluat(product):
    """Preia pretul minim din produsele asociate si il scrie in pret_preluat."""
    from app.models.product_association import ProductAssociation
    ids = ProductAssociation.get_associated_ids(product.id)
    if not ids:
        return
    associated = CompetitorProduct.query.filter(
        CompetitorProduct.id.in_(ids),
        CompetitorProduct.pret.isnot(None),
    ).all()
    if associated:
        min_product = min(associated, key=lambda p: p.pret)
        product.pret_preluat = min_product.pret
        product.pret_preluat_sursa = min_product.cod_competitor
        product.pret_preluat_asociat_id = min_product.id


def _fts_candidates(source_product, fetch_limit, target_competitors):
    """Cauta candidati folosind FTS5. Returneaza lista de CompetitorProduct sau None daca FTS5 nu e disponibil."""
    from app.extensions import db
    from sqlalchemy import text

    terms = []
    if source_product.title:
        from app.models.search_config import SearchConfig
        cfg = SearchConfig.get()
        words = [w for w in source_product.title.split() if len(w) > cfg.title_word_min_length]
        terms.extend(words[:cfg.title_word_count])
    if source_product.brand:
        terms.append(source_product.brand)
    if source_product.sku:
        terms.append(source_product.sku)

    if not terms:
        return None

    # Construieste query FTS5: fiecare termen cu prefix match (termen*)
    fts_query = " OR ".join(f'"{t}"*' for t in terms)

    competitor_filter = ""
    params = {"fts_q": fts_query, "src_code": source_product.cod_competitor, "lim": fetch_limit}

    if target_competitors:
        placeholders = ", ".join(f":tc{i}" for i in range(len(target_competitors)))
        for i, code in enumerate(target_competitors):
            params[f"tc{i}"] = code
        competitor_filter = f"AND cp.cod_competitor IN ({placeholders})"

    sql = text(f"""
        SELECT cp.id
        FROM competitor_products_fts fts
        JOIN competitor_products cp ON cp.id = fts.rowid
        WHERE fts.competitor_products_fts MATCH :fts_q
          AND cp.cod_competitor != :src_code
          {competitor_filter}
        LIMIT :lim
    """)

    try:
        rows = db.session.execute(sql, params).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return []
        return CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    except Exception:
        return None  # FTS5 indisponibil — fallback la ILIKE


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

    # Incearca FTS5 mai intai, fallback la ILIKE
    db_candidates = _fts_candidates(source_product, fetch_limit, target_competitors)

    if db_candidates is None:
        # FTS5 indisponibil — ILIKE fallback
        query = CompetitorProduct.query.filter(
            CompetitorProduct.cod_competitor != source_product.cod_competitor
        )
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
