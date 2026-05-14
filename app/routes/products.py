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
        return jsonify([])
    items = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    comp_codes = {p.cod_competitor for p in items}
    comp_map = {
        c.internal_code: c.display_name
        for c in Competitor.query.filter(Competitor.internal_code.in_(comp_codes)).all()
    }
    return jsonify([{
        "id": p.id, "sku": p.sku, "title": p.title,
        "brand": p.brand or "", "pret": p.pret,
        "cod_competitor": p.cod_competitor,
        "display_name": comp_map.get(p.cod_competitor, p.cod_competitor),
        "url": url_for("ai_association.associate", product_id=p.id),
    } for p in items])


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
    db.session.commit()
    return jsonify({"ok": True, "pret_preluat": asociat.pret})


@bp.route("/ai-batch", methods=["GET"])
def ai_batch():
    """Pagina de procesare AI in masa."""
    ids = request.args.getlist("ids", type=int)
    if not ids:
        flash("Niciun produs selectat.", "warning")
        return redirect(url_for("products.list_view"))
    products = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    return render_template("products/ai_batch.html", products=products, ids=ids)


@bp.route("/ai-batch/run", methods=["POST"])
@csrf.exempt
def ai_batch_run():
    """Proceseaza un singur produs din coada — apelat repetat din JS."""
    from app.models.ai_config import AIConfig
    from app.services.association_service import find_candidates
    from app.services.ai_service import build_prompt, call_ai, parse_ai_response

    data = request.get_json()
    product_id = data.get("product_id")
    custom_prompt = data.get("prompt")

    product = CompetitorProduct.query.get(product_id)
    if not product:
        return jsonify({"error": "Produs negasit", "product_id": product_id}), 404

    config = AIConfig.get_active()
    if not config or not config.api_key:
        return jsonify({"error": "AI neconfigurat", "product_id": product_id}), 400

    try:
        candidates = find_candidates(product)
        prompt = custom_prompt or build_prompt(product, candidates, config.prompt_template)
        ai_raw = call_ai(prompt, config)
        ai_result = parse_ai_response(ai_raw)
    except Exception as e:
        return jsonify({"error": str(e), "product_id": product_id}), 500

    matched = ai_result.get("matched_ids") or (
        [str(ai_result["matched_id"])] if ai_result.get("matched_id") else []
    )

    return jsonify({
        "product_id": product_id,
        "sku": product.sku,
        "title": product.title[:60],
        "matched_ids": matched,
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
        sync_pret_preluat(product)
        saved += 1
    db.session.commit()
    return jsonify({"ok": True, "saved": saved})
