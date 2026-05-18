from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.models.product_association import ProductAssociation
from app.services.association_service import sync_pret_preluat
from app.services.product_search_service import build_query

bp = Blueprint("products", __name__)

ALLOWED_PER_PAGE = [50, 100, 200, 400]


def _build_score_map(page_ids):
    """Returneaza cel mai bun scor pending per produs: {product_id: {"score": float, "count": int}}."""
    from app.models.product_match_score import ProductMatchScore
    if not page_ids:
        return {}
    rows = (
        db.session.query(
            ProductMatchScore.product_id,
            func.max(ProductMatchScore.score).label("best_score"),
            func.count(ProductMatchScore.id).label("cnt"),
        )
        .filter(
            ProductMatchScore.product_id.in_(page_ids),
            ProductMatchScore.status == "pending",
        )
        .group_by(ProductMatchScore.product_id)
        .all()
    )
    return {r.product_id: {"score": r.best_score, "count": r.cnt} for r in rows}


def _build_asociere_counts(page_ids):
    from sqlalchemy import or_ as _or
    counts: dict = {}
    if not page_ids:
        return counts
    rows = (
        db.session.query(
            ProductAssociation.product_id,
            ProductAssociation.associated_id,
        )
        .filter(
            _or(
                ProductAssociation.product_id.in_(page_ids),
                ProductAssociation.associated_id.in_(page_ids),
            )
        )
        .all()
    )
    ids_set = set(page_ids)
    for r in rows:
        if r.product_id in ids_set:
            counts[r.product_id] = counts.get(r.product_id, 0) + 1
        if r.associated_id in ids_set:
            counts[r.associated_id] = counts.get(r.associated_id, 0) + 1
    return counts


@bp.route("/")
def list_view():
    filters = {
        "competitor": request.args.get("competitor", "").strip(),
        "q": request.args.get("q", "").strip(),
        "sort": request.args.get("sort", "title").strip(),
        "direction": request.args.get("direction", "asc").strip(),
        "ai_status": request.args.get("ai_status", "").strip(),
    }
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", current_app.config.get("PRODUCTS_PER_PAGE", 50), type=int)

    load_all = per_page == 0  # "Toate" — JS va incarca toate paginile automat
    if per_page == 0 or per_page not in ALLOWED_PER_PAGE:
        if per_page != 0:
            per_page = 50  # normalizeaza valoarea invalida
        effective_per_page = 50  # pagineaza cu 50, JS incarca restul
    else:
        effective_per_page = per_page

    pagination = build_query(filters).paginate(page=page, per_page=effective_per_page, error_out=False)

    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    competitor_lookup = {c.internal_code: c.display_name for c in competitors}

    page_ids = [p.id for p in pagination.items]
    asociere_counts = _build_asociere_counts(page_ids)
    score_map = _build_score_map(page_ids)

    # Raspuns JSON pentru infinite scroll AJAX
    if request.args.get("format") == "json":
        return jsonify({
            "products": [{
                "id": p.id,
                "cod_competitor": p.cod_competitor,
                "sku": p.sku,
                "title": p.title,
                "pret": p.pret,
                "pret_preluat": p.pret_preluat,
                "pret_preluat_sursa": p.pret_preluat_sursa,
                "brand": p.brand,
                "url": p.url,
                "descriere": p.descriere or "",
                "pret_alerta": p.pret_alerta,
                "asociere_count": asociere_counts.get(p.id, 0),
                "best_score": score_map.get(p.id, {}).get("score"),
                "score_count": score_map.get(p.id, {}).get("count", 0),
            } for p in pagination.items],
            "has_next": pagination.has_next,
            "next_page": pagination.next_num,
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        })

    return render_template(
        "products/list.html",
        products=pagination.items,
        pagination=pagination,
        per_page=per_page,
        load_all=load_all,
        allowed_per_page=ALLOWED_PER_PAGE,
        competitors=competitors,
        competitor_lookup=competitor_lookup,
        filters=filters,
        asociere_counts=asociere_counts,
        score_map=score_map,
    )


@bp.route("/<int:product_id>")
def detail(product_id):
    product = CompetitorProduct.query.get_or_404(product_id)
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    competitor_lookup = {c.internal_code: c.display_name for c in competitors}

    from app.models.product_association import ProductAssociation
    assoc_ids = ProductAssociation.get_associated_ids(product_id)
    associated = []
    if assoc_ids:
        associated = CompetitorProduct.query.filter(CompetitorProduct.id.in_(assoc_ids)).all()
    assoc_comp_map = {}
    if associated:
        codes = {p.cod_competitor for p in associated}
        assoc_comp_map = {
            c.internal_code: c.display_name
            for c in Competitor.query.filter(Competitor.internal_code.in_(codes)).all()
        }

    return render_template(
        "products/detail.html",
        product=product,
        competitors=competitors,
        competitor_lookup=competitor_lookup,
        associated=associated,
        assoc_comp_map=assoc_comp_map,
    )


@bp.route("/bulk-delete", methods=["POST"])
@csrf.exempt
def bulk_delete():
    data = request.get_json()
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not ids:
        return jsonify({"error": "Niciun ID primit"}), 400
    deleted = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True, "deleted": deleted})


@bp.route("/<int:product_id>/edit", methods=["POST"])
@csrf.exempt
def edit(product_id):
    product = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json() if request.is_json else request.form
    product.sku = (data.get("sku") or "").strip()
    product.title = (data.get("title") or "").strip()
    product.brand = (data.get("brand") or "").strip()
    product.pret = data.get("pret") or None
    product.descriere = (data.get("descriere") or "").strip()
    product.asociere = (data.get("asociere") or "").strip()
    product.pret_alerta = data.get("pret_alerta") or None
    product.url = (data.get("url") or "").strip() or None
    db.session.commit()
    if request.is_json:
        return {"ok": True}
    flash("Produs actualizat.", "success")
    return redirect(url_for("products.list_view"))


@bp.route("/<int:product_id>/delete", methods=["POST"])
def delete(product_id):
    product = CompetitorProduct.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Produs sters.", "success")
    return redirect(url_for("products.list_view"))


@bp.route("/<int:product_id>/asociate", methods=["GET"])
def asociate(product_id):
    from app.models.product_association import ProductAssociation
    product = CompetitorProduct.query.get_or_404(product_id)
    ids = ProductAssociation.get_associated_ids(product_id)
    if not ids:
        return jsonify({"items": [], "meta": {}})
    items = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    comp_codes = {p.cod_competitor for p in items}
    comp_map = {
        c.internal_code: c.display_name
        for c in Competitor.query.filter(Competitor.internal_code.in_(comp_codes)).all()
    }
    return jsonify({
        "items": [{
            "id": p.id, "sku": p.sku, "title": p.title,
            "brand": p.brand or "", "pret": p.pret,
            "cod_competitor": p.cod_competitor,
            "display_name": comp_map.get(p.cod_competitor, p.cod_competitor),
            "url": p.url or "",
        } for p in items],
        "meta": {
            "pret_preluat_asociat_id": product.pret_preluat_asociat_id,
        },
    })


@bp.route("/<int:product_id>/price-history")
def price_history(product_id):
    from app.models.price_history import PriceHistory
    history = (
        PriceHistory.query
        .filter_by(product_id=product_id)
        .order_by(PriceHistory.recorded_at.asc())
        .all()
    )
    return jsonify([{
        "pret": h.pret,
        "recorded_at": h.recorded_at.strftime("%d.%m.%Y %H:%M"),
        "sursa": h.sursa,
    } for h in history])


@bp.route("/<int:product_id>/ai-history")
def ai_history(product_id):
    from app.models.ai_association_log import AIAssociationLog
    logs = (
        AIAssociationLog.query
        .filter_by(product_id=product_id)
        .order_by(AIAssociationLog.processed_at.desc())
        .all()
    )
    return jsonify([{
        "id": log.id,
        "competitor_target": log.competitor_target or "toti",
        "matched_product_id": log.matched_product_id,
        "status": log.status,
        "confidence": log.confidence,
        "reason": log.reason or "",
        "prompt_name": log.prompt_name or "",
        "processed_at": log.processed_at.strftime("%d.%m.%Y %H:%M"),
        "confirmed_at": log.confirmed_at.strftime("%d.%m.%Y %H:%M") if log.confirmed_at else None,
    } for log in logs])


@bp.route("/<int:product_id>/scrape", methods=["POST"])
@csrf.exempt
def scrape_product(product_id):
    from app.models.competitor import Competitor
    from app.models.price_history import PriceHistory
    from app.services.scraper_service import scrape_price
    from app.services.notification_service import create_notification

    product = CompetitorProduct.query.get_or_404(product_id)
    if not product.url:
        return jsonify({"error": "Produsul nu are URL setat"}), 400

    competitor = Competitor.query.filter_by(internal_code=product.cod_competitor).first()
    if not competitor or not competitor.price_selector:
        return jsonify({"error": "Competitorul nu are selector CSS configurat"}), 400

    new_pret = scrape_price(product.url, competitor.price_selector)
    if new_pret is None:
        return jsonify({"error": "Nu s-a putut extrage pretul. Verifica URL-ul si selectorul CSS."}), 422

    changed = new_pret != product.pret
    if changed:
        db.session.add(PriceHistory(product_id=product.id, pret=new_pret, sursa="scraper"))
        if product.pret_alerta and new_pret <= product.pret_alerta:
            create_notification(
                "Alerta pret",
                f"#{product.id} {product.title[:50]} → {new_pret:.2f} lei"
                f" (prag: {product.pret_alerta:.2f} lei)",
                "warning",
            )
        product.pret = new_pret
        db.session.commit()

    return jsonify({"ok": True, "pret": new_pret, "changed": changed})


@bp.route("/<int:product_id>/pret-preluat", methods=["POST"])
@csrf.exempt
def set_pret_preluat(product_id):
    from app.models.product_association import ProductAssociation
    product = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json()
    asociat_id = int(data.get("asociat_id", 0))
    if not asociat_id or not ProductAssociation.are_associated(product_id, asociat_id):
        return jsonify({"error": "Produsul nu este asociat"}), 400
    asociat = CompetitorProduct.query.get_or_404(asociat_id)
    product.pret_preluat = asociat.pret
    product.pret_preluat_sursa = asociat.cod_competitor
    product.pret_preluat_asociat_id = asociat.id
    db.session.commit()
    return jsonify({"ok": True, "pret_preluat": asociat.pret})


@bp.route("/ai-batch", methods=["GET"])
def ai_batch():
    ids = request.args.getlist("ids", type=int)
    if not ids:
        flash("Niciun produs selectat.", "warning")
        return redirect(url_for("products.list_view"))
    products = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    source_codes = {p.cod_competitor for p in products}
    target_competitors = [c for c in competitors if c.internal_code not in source_codes]
    from app.models.prompt_template import PromptTemplate
    prompts = PromptTemplate.query.order_by(
        PromptTemplate.is_system.desc(), PromptTemplate.name.asc()
    ).all()
    return render_template(
        "products/ai_batch.html",
        products=products,
        ids=ids,
        target_competitors=target_competitors,
        prompts=prompts,
    )


@bp.route("/ai-batch/run", methods=["POST"])
@csrf.exempt
def ai_batch_run():
    from app.models.ai_config import AIConfig
    from app.services.association_service import find_candidates
    from app.services.ai_service import build_prompt, call_ai, parse_ai_response

    data = request.get_json()
    product_id = data.get("product_id")
    custom_prompt = data.get("prompt")
    target_competitors = data.get("target_competitors")
    prompt_id = data.get("prompt_id")

    product = CompetitorProduct.query.get(product_id)
    if not product:
        return jsonify({"error": "Produs negasit", "product_id": product_id}), 404

    config = AIConfig.get_active()
    if not config or not config.api_key:
        return jsonify({"error": "AI neconfigurat", "product_id": product_id}), 400

    prompt_name = None
    if prompt_id:
        from app.models.prompt_template import PromptTemplate
        tmpl = PromptTemplate.query.get(int(prompt_id))
        if tmpl:
            prompt_name = tmpl.name
            custom_prompt = custom_prompt or tmpl.body

    try:
        candidates = find_candidates(product, target_competitors=target_competitors or None)
        prompt = custom_prompt or build_prompt(product, candidates, config.prompt_template)
        ai_raw = call_ai(prompt, config)
        ai_result = parse_ai_response(ai_raw)
    except Exception as e:
        return jsonify({"error": str(e), "product_id": product_id}), 500

    matched = ai_result.get("matched_ids") or (
        [str(ai_result["matched_id"])] if ai_result.get("matched_id") else []
    )

    from app.models.ai_association_log import AIAssociationLog
    db.session.add(AIAssociationLog(
        product_id=product_id,
        competitor_target=",".join(target_competitors) if target_competitors else None,
        matched_product_id=int(matched[0]) if matched and str(matched[0]).isdigit() else None,
        status="found" if matched else "no_match",
        confidence=ai_result.get("confidence"),
        reason=ai_result.get("reason"),
        prompt_name=prompt_name,
    ))
    db.session.commit()

    # Aduce detalii despre produsele gasite
    matched_details = []
    if matched:
        matched_products = CompetitorProduct.query.filter(
            CompetitorProduct.id.in_([int(x) for x in matched if x.isdigit()])
        ).all()
        comp_codes = {p.cod_competitor for p in matched_products}
        from app.models.competitor import Competitor as Comp
        comp_map = {c.internal_code: c.display_name for c in Comp.query.filter(
            Comp.internal_code.in_(comp_codes)).all()}
        matched_details = [{
            "id": p.id, "sku": p.sku, "title": p.title,
            "brand": p.brand or "", "pret": p.pret,
            "display_name": comp_map.get(p.cod_competitor, p.cod_competitor),
        } for p in matched_products]

    return jsonify({
        "product_id": product_id,
        "sku": product.sku,
        "title": product.title[:60],
        "matched_ids": matched,
        "matched_details": matched_details,
        "confidence": ai_result.get("confidence", 0),
        "reason": ai_result.get("reason", ""),
        "raw": ai_result.get("raw", ""),
    })


@bp.route("/ai-batch/confirm", methods=["POST"])
@csrf.exempt
def ai_batch_confirm():
    """Salveaza asocierile confirmate din procesarea in masa."""
    from app.models.product_association import ProductAssociation
    from app.models.ai_association_log import AIAssociationLog
    from datetime import datetime
    data = request.get_json()
    results = data.get("results", [])
    saved = 0
    for item in results:
        product_id = item.get("product_id")
        if not product_id:
            continue
        ids_to_save = [int(x) for x in item.get("matched_ids", []) if str(x).isdigit()]
        if not ids_to_save:
            continue
        for mid in ids_to_save:
            ProductAssociation.add(product_id, mid)
        log = (
            AIAssociationLog.query
            .filter_by(product_id=product_id, status="found")
            .order_by(AIAssociationLog.processed_at.desc())
            .first()
        )
        if log:
            log.status = "confirmed"
            log.confirmed_at = datetime.utcnow()
        saved += 1
    db.session.commit()
    return jsonify({"ok": True, "saved": saved})


@bp.route("/<int:product_id>/exclude", methods=["POST"])
@csrf.exempt
def exclude_asociere(product_id):
    from app.models.excluded_association import ExcludedAssociation
    from app.models.product_association import ProductAssociation
    product = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json()
    excluded_id = int(data.get("excluded_id", 0))
    if not excluded_id:
        return jsonify({"error": "excluded_id lipsa"}), 400

    ProductAssociation.remove(product_id, excluded_id)

    # Golim pretul preluat si recalculam din asocierile ramase.
    product.pret_preluat = None
    product.pret_preluat_sursa = None
    product.pret_preluat_asociat_id = None
    sync_pret_preluat(product)

    existing = ExcludedAssociation.query.filter_by(
        product_id=product_id, excluded_product_id=excluded_id
    ).first()
    if not existing:
        db.session.add(ExcludedAssociation(product_id=product_id, excluded_product_id=excluded_id))
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/excluded")
def excluded_list():
    from app.models.excluded_association import ExcludedAssociation
    exclusions = ExcludedAssociation.query.order_by(ExcludedAssociation.created_at.desc()).all()
    all_ids = set()
    for e in exclusions:
        all_ids.add(e.product_id)
        all_ids.add(e.excluded_product_id)
    products_map = {}
    if all_ids:
        products_map = {p.id: p for p in CompetitorProduct.query.filter(CompetitorProduct.id.in_(all_ids)).all()}
    comp_codes = {p.cod_competitor for p in products_map.values()}
    competitors_map = {
        c.internal_code: c.display_name
        for c in Competitor.query.filter(Competitor.internal_code.in_(comp_codes)).all()
    } if comp_codes else {}
    return render_template(
        "products/excluded.html",
        exclusions=exclusions,
        products_map=products_map,
        competitors_map=competitors_map,
    )


@bp.route("/excluded/<int:exclusion_id>/undo", methods=["POST"])
def undo_exclusion(exclusion_id):
    from app.models.excluded_association import ExcludedAssociation
    excl = ExcludedAssociation.query.get_or_404(exclusion_id)
    db.session.delete(excl)
    db.session.commit()
    flash("Excludere anulata.", "success")
    return redirect(url_for("products.excluded_list"))
