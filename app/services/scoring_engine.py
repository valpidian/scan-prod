"""
Motor de scoring bazat pe reguli configurabile din DB.
Extinde matching_service.py cu suport pentru MatchingRule.
"""
from difflib import SequenceMatcher

from app.services.matching_service import extract_model, normalize_sku


def score_pair_with_rules(source, candidate, rules: list) -> tuple[float, dict]:
    """
    Calculeaza scorul de potrivire intre doua produse folosind regulile din lista.
    Returneaza (scor_final 0-1, breakdown {eticheta: scor_partial}).
    """
    rule_map = {r.rule_type: r for r in rules if r.is_active}
    breakdown = {}
    score = 0.0

    src_sku_norm = normalize_sku(source.sku or "")
    cnd_sku_norm = normalize_sku(candidate.sku or "")

    # ── 1. SKU exact ─────────────────────────────────────────────────────────
    if "sku_exact" in rule_map and src_sku_norm and src_sku_norm == cnd_sku_norm:
        w = rule_map["sku_exact"].weight
        score = max(score, w)
        breakdown["SKU exact"] = w

    # ── 2. SKU normalizat (contine) ───────────────────────────────────────────
    if "sku_partial" in rule_map and src_sku_norm and cnd_sku_norm and "SKU exact" not in breakdown:
        if src_sku_norm in cnd_sku_norm or cnd_sku_norm in src_sku_norm:
            w = rule_map["sku_partial"].weight
            score = max(score, w)
            breakdown["SKU normalizat"] = w

    # ── 3. SKU in titlu / descriere (bidirectional) ────────────────────────────
    if "sku_in_title" in rule_map:
        r = rule_map["sku_in_title"]
        src_sku_up = (source.sku or "").upper()
        cnd_sku_up = (candidate.sku or "").upper()
        cnd_title  = (candidate.title or "").upper()
        cnd_desc   = (candidate.descriere or "").upper()
        src_title  = (source.title or "").upper()
        src_desc   = (source.descriere or "").upper()
        if src_sku_up and (src_sku_up in cnd_title or src_sku_up in cnd_desc):
            score = max(score, r.weight)
            breakdown["SKU sursa in text candidat"] = r.weight
        if cnd_sku_up and (cnd_sku_up in src_title or cnd_sku_up in src_desc):
            score = max(score, r.weight)
            breakdown["SKU candidat in text sursa"] = r.weight

    # ── 4. Cod model tehnic ────────────────────────────────────────────────────
    if "model_match" in rule_map:
        r = rule_map["model_match"]
        src_models = set(extract_model(source.sku or "") + extract_model(source.title or ""))
        cnd_models = set(extract_model(candidate.sku or "") + extract_model(candidate.title or ""))
        common = src_models & cnd_models
        if common:
            model_score = min(r.weight + 0.05 * (len(common) - 1), 0.95)
            score = max(score, model_score)
            breakdown[f"Model ({', '.join(sorted(common)[:3])})"] = round(model_score, 3)

    # ── 5. Similaritate titlu ──────────────────────────────────────────────────
    if "title_similarity" in rule_map and score < 0.90:
        r = rule_map["title_similarity"]
        params = r.get_params()
        threshold = params.get("threshold", 0.72)
        ratio = SequenceMatcher(
            None,
            (source.title or "").lower(),
            (candidate.title or "").lower(),
        ).ratio()
        if ratio >= threshold:
            sim_score = round(r.weight * ratio, 3)
            score = max(score, sim_score)
            breakdown[f"Titlu similar ({int(ratio * 100)}%)"] = sim_score

    # ── 6. Brand identic (bonus aditiv) ───────────────────────────────────────
    if "brand_bonus" in rule_map and score > 0:
        r = rule_map["brand_bonus"]
        src_brand = (source.brand or "").upper().strip()
        cnd_brand = (candidate.brand or "").upper().strip()
        if src_brand and cnd_brand and src_brand == cnd_brand:
            bonus = r.weight
            score = min(score + bonus, 1.0)
            breakdown["Brand identic (+bonus)"] = bonus

    # ── 7. Interval pret (bonus aditiv) ────────────────────────────────────────
    if "price_range" in rule_map and score > 0:
        r = rule_map["price_range"]
        if source.pret and candidate.pret and float(source.pret) > 0:
            params = r.get_params()
            tol_pct = params.get("tolerance_pct", 15)
            diff_pct = abs(float(source.pret) - float(candidate.pret)) / float(source.pret) * 100
            if diff_pct <= tol_pct:
                bonus = r.weight
                score = min(score + bonus, 1.0)
                breakdown[f"Pret ±{diff_pct:.1f}% (+bonus)"] = bonus

    return round(score, 3), breakdown


def run_scoring_for_product(source_product, target_competitors=None, rules=None, min_score=0.40):
    """
    Ruleaza motorul de scoring pentru un produs sursa fata de toti candidatii.
    Returneaza lista de (candidate_product, score, breakdown) sortata descrescator.
    """
    from app.services.association_service import find_candidates
    from app.models.matching_rule import MatchingRule

    if rules is None:
        rules = MatchingRule.get_active()

    candidates = find_candidates(source_product, target_competitors=target_competitors, limit=200)

    results = []
    for row in candidates:
        cand = row["product"]
        score, breakdown = score_pair_with_rules(source_product, cand, rules)
        if score >= min_score:
            results.append((cand, score, breakdown))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
