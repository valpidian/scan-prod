from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.search_config import SearchConfig

bp = Blueprint("search_config", __name__)


@bp.route("/", methods=["GET", "POST"])
def index():
    cfg = SearchConfig.get()

    if request.method == "POST":
        cfg.min_query_length        = int(request.form.get("min_query_length", 2))
        cfg.search_limit            = int(request.form.get("search_limit", 100))
        cfg.candidate_limit         = int(request.form.get("candidate_limit", 20))
        cfg.candidate_fetch_multiplier = int(request.form.get("candidate_fetch_multiplier", 3))
        cfg.min_score_filter        = float(request.form.get("min_score_filter", 0.0))
        cfg.sure_match_threshold    = float(request.form.get("sure_match_threshold", 0.85))
        cfg.sku_exact_score         = float(request.form.get("sku_exact_score", 1.0))
        cfg.sku_partial_score       = float(request.form.get("sku_partial_score", 0.85))
        cfg.model_match_score       = float(request.form.get("model_match_score", 0.80))
        cfg.brand_bonus             = float(request.form.get("brand_bonus", 0.10))
        cfg.category_bonus          = float(request.form.get("category_bonus", 0.05))
        cfg.title_word_min_length   = int(request.form.get("title_word_min_length", 3))
        cfg.title_word_count        = int(request.form.get("title_word_count", 4))
        cfg.ai_min_confidence       = float(request.form.get("ai_min_confidence", 0.6))
        db.session.commit()
        flash("Configurare salvata.", "success")
        return redirect(url_for("search_config.index"))

    return render_template("search_config/index.html", cfg=cfg)
