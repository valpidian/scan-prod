"""
Motor de matching bazat pe regex + reguli semantice.
Folosit pentru pre-filtrarea candidatilor inainte de AI.
"""
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Extragere model tehnic ────────────────────────────────────────────────────

# Pattern-uri pentru modele tehnice comune (ordonate dupa specificitate)
_MODEL_PATTERNS = [
    # HVAC: FTXP25, KFR-35GW, MSZ-AP25VGK, AR09TXHQ, CP-W18FK
    re.compile(r'\b([A-Z]{2,6}[-/]?[A-Z0-9]{2,10}(?:[-/][A-Z0-9]{1,8})*)\b'),
    # Modele cu cifre+litere: 35GW, 25VGK, 18000BTU
    re.compile(r'\b(\d{2,5}[A-Z]{1,4})\b'),
    # Capacitate kW/BTU
    re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(?:kw|btu|w)\b', re.IGNORECASE),
]

# Separatori de ignorat la normalizare SKU
_SEP_RE = re.compile(r'[-/\s_.]+')

# Prefixe/sufixe de distribuitor de eliminat
_DISTRIBUTOR_AFFIXES = re.compile(
    r'^(?:RO|EU|INT|LOC|WH|B2B|PRO|OEM)[-/]|[-/](?:RO|EU|INT|A|B|C|D|NEW|OLD|V\d)$',
    re.IGNORECASE
)


def extract_model(text: str) -> list[str]:
    """Extrage modelele tehnice dintr-un text (SKU sau titlu)."""
    if not text:
        return []
    models = []
    for pattern in _MODEL_PATTERNS:
        for m in pattern.finditer(text.upper()):
            val = m.group(1) if m.lastindex else m.group(0)
            if len(val) >= 3 and val not in models:
                models.append(val)
    return models


def normalize_sku(sku: str) -> str:
    """Normalizeaza SKU pentru comparare: strip afixe, separatori, uppercase."""
    if not sku:
        return ""
    s = sku.upper().strip()
    s = _DISTRIBUTOR_AFFIXES.sub('', s)
    s = _SEP_RE.sub('', s)
    return s


# ── Scoring ───────────────────────────────────────────────────────────────────

@dataclass
class MatchScore:
    product_id: int
    sku: str
    title: str
    score: float          # 0.0 - 1.0
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 0.9:
            return "sigur"
        if self.score >= 0.7:
            return "probabil"
        if self.score >= 0.5:
            return "posibil"
        return "slab"


def score_pair(source, candidate, cfg=None) -> MatchScore:
    score = 0.0
    reasons = []

    # Scoruri din config sau valori default
    sku_exact    = cfg.sku_exact_score    if cfg else 1.0
    sku_partial  = cfg.sku_partial_score  if cfg else 0.85
    model_base   = cfg.model_match_score  if cfg else 0.80
    brand_bonus  = cfg.brand_bonus        if cfg else 0.10
    cat_bonus    = cfg.category_bonus     if cfg else 0.05

    src_sku_norm = normalize_sku(source.sku or "")
    cnd_sku_norm = normalize_sku(candidate.sku or "")

    # 1. Potrivire exacta SKU normalizat
    if src_sku_norm and src_sku_norm == cnd_sku_norm:
        score = max(score, sku_exact)
        reasons.append(f"SKU exact: {src_sku_norm}")
    elif src_sku_norm and cnd_sku_norm:
        if src_sku_norm in cnd_sku_norm or cnd_sku_norm in src_sku_norm:
            score = max(score, sku_partial)
            reasons.append(f"SKU partial: {src_sku_norm} ↔ {cnd_sku_norm}")

    # 2. Model tehnic comun
    src_models = set(extract_model(source.sku or "") + extract_model(source.title or ""))
    cnd_models = set(extract_model(candidate.sku or "") + extract_model(candidate.title or ""))
    common_models = src_models & cnd_models
    if common_models:
        model_score = min(model_base + 0.05 * (len(common_models) - 1), 0.95)
        if model_score > score:
            score = model_score
            reasons.append(f"Model comun: {', '.join(common_models)}")

    # 3. Brand identic
    src_brand = (source.brand or "").upper().strip()
    cnd_brand = (candidate.brand or "").upper().strip()
    if src_brand and cnd_brand and src_brand == cnd_brand:
        if score > 0:
            score = min(score + brand_bonus, 1.0)
            reasons.append(f"Brand identic: {src_brand}")
        else:
            score = max(score, 0.30)
            reasons.append(f"Doar brand: {src_brand}")

    # 4. Categorie identica
    src_cat = (source.categorie or "").lower().strip()
    cnd_cat = (candidate.categorie or "").lower().strip()
    if src_cat and cnd_cat and src_cat == cnd_cat:
        score = min(score + cat_bonus, 1.0)
        reasons.append(f"Categorie: {src_cat}")

    return MatchScore(
        product_id=candidate.id,
        sku=candidate.sku,
        title=candidate.title,
        score=round(score, 3),
        reasons=reasons,
    )


def rank_candidates(source, candidates: list, min_score: float = 0.3, cfg=None) -> list[MatchScore]:
    from app.models.search_config import SearchConfig
    if cfg is None:
        try:
            cfg = SearchConfig.get()
        except Exception:
            cfg = None
    scores = []
    for row in candidates:
        candidate = row["product"] if isinstance(row, dict) else row
        ms = score_pair(source, candidate, cfg=cfg)
        if ms.score >= min_score:
            scores.append(ms)
    return sorted(scores, key=lambda x: x.score, reverse=True)


def get_sure_matches(source, candidates: list, threshold: float = 0.85) -> list[MatchScore]:
    """Returneaza doar potrivirile sigure (scor >= threshold)."""
    return [ms for ms in rank_candidates(source, candidates) if ms.score >= threshold]
