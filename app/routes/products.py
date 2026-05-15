from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.services.association_service import sync_pret_preluat
from app.services.product_search_service import build_query

bp = Blueprint("products", __name__)

ALLOWED_PER_PAGE = [50, 100, 200, 400]


@bp.route("/")
def list_view():
    filters = {
        "competitor": request.args.get("competitor", "").strip(),
        "q": request.args.get("q", "").strip(),
        "sort": request.args.get("sort", "title").strip(),
        "direction": request.args.get("direction", "asc").strip(),
    }
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", current_app.config.get("PRODUCTS_PER_PAGE", 50), type=int)
    if per_page not in ALLOWED_PER_PAGE:
        per_page = 50
    pagination = build_query(filters).paginate(page=page, per_page=per_page, error_out=False)
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    competitor_lookup = {c.internal_code: c.display_name for c in competitors}
    return render_template(
        "products/list.html",
        products=pagination.items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=ALLOWED_PER_PAGE,
        competitors=competitors,
        competitor_lookup=competitor_lookup,
        filters=filters,
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
    product = CompetitorProduct.query.get_or_404(product_id)
    ids = [int(x) for x in (product.asociere or "").split(";") if x.isdigit()]
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
    product = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json()
    asociat_id = str(data.get("asociat_id", ""))
    asocieri = [x for x in (product.asociere or "").split(";") if x]
    if asociat_id not in asocieri:
        return jsonify({"error": "Produsul nu este asociat"}), 400
    asociat = CompetitorProduct.query.get_or_404(int(asociat_id))
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
    # Exclude competitorii din care fac parte produsele selectate
    source_codes = {p.cod_competitor for p in products}
    target_competitors = [c for c in competitors if c.internal_code not in source_codes]
    return render_template(
        "products/ai_batch.html",
        products=products,
        ids=ids,
        target_competitors=target_competitors,
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
    target_competitors = data.get("target_competitors")  # lista de cod_competitor sau None = toti

    product = CompetitorProduct.query.get(product_id)
    if not product:
        return jsonify({"error": "Produs negasit", "product_id": product_id}), 404

    config = AIConfig.get_active()
    if not config or not config.api_key:
        return jsonify({"error": "AI neconfigurat", "product_id": product_id}), 400

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
    data = request.get_json()
    results = data.get("results", [])  # [{product_id, matched_ids}, ...]
    saved = 0
    for item in results:
        product = CompetitorProduct.query.get(item.get("product_id"))
        if not product:
            continue
        ids_to_save = [str(x) for x in item.get("matched_ids", []) if x]
        if not ids_to_save:
            continue
        current = [x for x in (product.asociere or "").split(";") if x]
        for mid in ids_to_save:
            if mid not in current:
                current.append(mid)
        product.asociere = ";".join(current)
        saved += 1
    db.session.commit()
    return jsonify({"ok": True, "saved": saved})


@bp.route("/<int:product_id>/exclude", methods=["POST"])
@csrf.exempt
def exclude_asociere(product_id):
    from app.models.excluded_association import ExcludedAssociation
    product = CompetitorProduct.query.get_or_404(product_id)
    data = request.get_json()
    excluded_id = int(data.get("excluded_id", 0))
    if not excluded_id:
        return jsonify({"error": "excluded_id lipsa"}), 400

    current = [x for x in (product.asociere or "").split(";") if x]
    if str(excluded_id) in current:
        current.remove(str(excluded_id))
        product.asociere = ";".join(current)

    # Golim pretul preluat si recalculam din asocierile ramase.
    # Facem asta indiferent de sursa originala, ca sa evitam situatia
    # in care pret_preluat_asociat_id e None (date vechi) si verificarea
    # conditionala ar rata cazul cand produsul exclus era sursa pretului.
    product.pret_preluat = None
    product.pret_preluat_sursa = None
    product.pret_preluat_asociat_id = None
    sync_pret_preluat(product)  # re-populeaza din ce a ramas, sau lasa None

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
