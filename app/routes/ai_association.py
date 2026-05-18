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
    all_competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    target_competitors = [c for c in all_competitors if c.internal_code != source.cod_competitor]
    selected = request.args.getlist("competitors")
    candidates = find_candidates(source, target_competitors=selected or None)
    config = AIConfig.get_active()
    prompt = build_prompt(source, candidates, config.prompt_template if config else None)
    return render_template(
        "ai/workbench.html",
        source=source,
        source_competitor=source_competitor,
        candidates=candidates,
        prompt=prompt,
        config=config,
        target_competitors=target_competitors,
        selected_competitors=selected,
    )


@bp.route("/associate/<int:product_id>/candidates", methods=["GET"])
def associate_candidates(product_id):
    source = CompetitorProduct.query.get_or_404(product_id)
    selected = request.args.getlist("competitors")
    candidates = find_candidates(source, target_competitors=selected or None)
    config = AIConfig.get_active()
    template_body = None
    template_id = request.args.get("template_id", type=int)
    if template_id:
        from app.models.prompt_template import PromptTemplate
        tmpl = PromptTemplate.query.get(template_id)
        if tmpl:
            template_body = tmpl.body
    prompt = build_prompt(source, candidates, template_body or (config.prompt_template if config else None))
    return jsonify({
        "count": len(candidates),
        "prompt": prompt,
        "candidates": [{
            "id": row["product"].id,
            "title": row["product"].title or "",
            "sku": row["product"].sku or "",
            "brand": row["product"].brand or "",
            "pret": row["product"].pret,
            "competitor_name": row["competitor"].display_name if row["competitor"] else "",
            "match_score": row.get("match_score", 0) or 0,
        } for row in candidates],
    })


@bp.route("/associate/<int:product_id>/run", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute")
def associate_run(product_id):
    source = CompetitorProduct.query.get_or_404(product_id)
    config = AIConfig.get_active()

    if not config or not config.api_key:
        return jsonify({"error": "AI neconfigurat — adauga API key in Configurare AI"}), 400

    data_json = request.get_json(silent=True) or {}
    target_competitors = data_json.get("target_competitors") or None
    candidates = find_candidates(source, target_competitors=target_competitors)
    custom_prompt = data_json.get("prompt")
    prompt_id = data_json.get("prompt_id")
    prompt_name = None
    if prompt_id:
        from app.models.prompt_template import PromptTemplate
        tmpl = PromptTemplate.query.get(int(prompt_id))
        if tmpl:
            prompt_name = tmpl.name
            custom_prompt = custom_prompt or tmpl.body
    prompt = custom_prompt or build_prompt(source, candidates, config.prompt_template)

    try:
        ai_raw = call_ai(prompt, config)
        ai_result = parse_ai_response(ai_raw)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    matched = ai_result.get("matched_ids") or (
        [str(ai_result["matched_id"])] if ai_result.get("matched_id") else []
    )

    from app.models.ai_association_log import AIAssociationLog
    db.session.add(AIAssociationLog(
        product_id=source.id,
        competitor_target=",".join(target_competitors) if target_competitors else None,
        matched_product_id=int(matched[0]) if matched and str(matched[0]).isdigit() else None,
        status="found" if matched else "no_match",
        confidence=ai_result.get("confidence"),
        reason=ai_result.get("reason"),
        prompt_name=prompt_name,
    ))
    db.session.commit()

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

    from app.models.ai_association_log import AIAssociationLog
    from datetime import datetime
    log = (
        AIAssociationLog.query
        .filter_by(product_id=source.id, status="found")
        .order_by(AIAssociationLog.processed_at.desc())
        .first()
    )
    if log:
        log.status = "confirmed"
        log.confirmed_at = datetime.utcnow()

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


@bp.route("/prompts", methods=["GET"])
def prompts_list():
    from app.models.prompt_template import PromptTemplate
    templates = PromptTemplate.query.order_by(
        PromptTemplate.is_system.desc(), PromptTemplate.name.asc()
    ).all()
    return jsonify([t.as_dict() for t in templates])


@bp.route("/prompts/save", methods=["POST"])
@csrf.exempt
def prompts_save():
    from app.models.prompt_template import PromptTemplate
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    body = (data.get("body") or "").strip()
    template_id = data.get("id")

    if not name or not body:
        return jsonify({"error": "Numele si corpul sunt obligatorii"}), 400

    if template_id:
        t = PromptTemplate.query.get_or_404(int(template_id))
        if t.is_system:
            return jsonify({"error": "Templateurile sistem nu pot fi modificate"}), 403
        t.name = name
        t.description = description
        t.body = body
    else:
        t = PromptTemplate(name=name, description=description, body=body, is_system=False)
        db.session.add(t)

    db.session.commit()
    return jsonify(t.as_dict())


@bp.route("/prompts/<int:template_id>/delete", methods=["POST"])
@csrf.exempt
def prompts_delete(template_id):
    from app.models.prompt_template import PromptTemplate
    t = PromptTemplate.query.get_or_404(template_id)
    if t.is_system:
        return jsonify({"error": "Templateurile sistem nu pot fi sterse"}), 403
    db.session.delete(t)
    db.session.commit()
    return jsonify({"deleted": True})


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
