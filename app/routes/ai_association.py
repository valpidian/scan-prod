from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import csrf, limiter
from app.extensions import db
from app.models.ai_config import AIConfig
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.services.association_service import find_candidates
from app.services.ai_service import build_prompt, call_ai, parse_ai_response
from app.services.notification_service import create_notification
from app.utils.logging_helpers import audit

bp = Blueprint("ai_association", __name__)


@bp.route("/associate/<int:product_id>", methods=["GET"])
def associate(product_id):
    source = CompetitorProduct.query.get_or_404(product_id)
    source_competitor = Competitor.query.filter_by(internal_code=source.cod_competitor).first()
    candidates = find_candidates(source)
    config = AIConfig.get_active()
    prompt = build_prompt(source, candidates, config.prompt_template if config else None)
    return render_template(
        "ai/workbench.html",
        source=source,
        source_competitor=source_competitor,
        candidates=candidates,
        prompt=prompt,
        config=config,
    )


@bp.route("/associate/<int:product_id>/run", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute")
def associate_run(product_id):
    source = CompetitorProduct.query.get_or_404(product_id)
    config = AIConfig.get_active()

    if not config or not config.api_key:
        return jsonify({"error": "AI neconfigurat — adauga API key in Configurare AI"}), 400

    candidates = find_candidates(source)
    custom_prompt = request.json.get("prompt") if request.is_json else None
    prompt = custom_prompt or build_prompt(source, candidates, config.prompt_template)

    try:
        ai_raw = call_ai(prompt, config)
        ai_result = parse_ai_response(ai_raw)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    matched = ai_result.get("matched_ids") or (
        [str(ai_result["matched_id"])] if ai_result.get("matched_id") else []
    )

    return jsonify({
        "raw": ai_result.get("raw", ""),
        "matched_ids": matched,
        "confidence": ai_result.get("confidence", 0),
        "reason": ai_result.get("reason", ""),
    })


@bp.route("/associate/<int:product_id>/confirm", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute")
def associate_confirm(product_id):
    from app.models.product_association import ProductAssociation
    source = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json()
    ids_to_save = [int(x) for x in (data.get("matched_ids") or []) if str(x).isdigit()]

    if not ids_to_save:
        return jsonify({"error": "Niciun ID de salvat"}), 400

    for mid in ids_to_save:
        ProductAssociation.add(source.id, mid)
    db.session.commit()

    create_notification(
        "Asociere confirmata",
        f"Produsul #{source.id} asociat cu: {', '.join(['#' + str(x) for x in ids_to_save])}",
        "success",
    )
    audit("Asociere confirmata | product_id=%s | ids=%s", source.id, ids_to_save)

    return jsonify({"saved": True})


@bp.route("/associate/<int:product_id>/pret/<int:asociat_id>", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute")
def associate_pret(product_id, asociat_id):
    from app.models.product_association import ProductAssociation
    source = CompetitorProduct.query.get_or_404(product_id)
    asociat = CompetitorProduct.query.get_or_404(asociat_id)

    if not ProductAssociation.are_associated(source.id, asociat_id):
        return jsonify({"error": "Produsul nu este asociat"}), 400

    source.pret_preluat = asociat.pret
    db.session.commit()
    audit("Pret preluat | product_id=%s | de la=%s | pret=%s", source.id, asociat_id, asociat.pret)
    return jsonify({"ok": True, "pret_preluat": asociat.pret})


@bp.route("/config", methods=["GET", "POST"])
def config():
    cfg = AIConfig.get_active()
    if not cfg:
        cfg = AIConfig()
        db.session.add(cfg)
        db.session.commit()

    if request.method == "POST":
        cfg.provider = request.form.get("provider", "openai")
        cfg.model = request.form.get("model", "gpt-4o-mini")
        api_key = request.form.get("api_key", "").strip()
        if api_key:
            cfg.api_key = api_key
        cfg.prompt_template = request.form.get("prompt_template", "").strip() or None
        db.session.commit()
        flash("Configurare AI salvata.", "success")
        return redirect(url_for("ai_association.config"))

    return render_template("ai/config.html", cfg=cfg)
