from flask import Blueprint, jsonify, render_template, request

from app.extensions import csrf, db
from app.models.competitor_product import CompetitorProduct
from app.models.search_config import SearchConfig
from app.services.product_search_service import complex_search


bp = Blueprint("search", __name__)


@bp.route("/", methods=["GET", "POST"])
def advanced():
    query_text = request.values.get("q", "").strip()
    cfg = SearchConfig.get()

    too_short = query_text and len(query_text) < cfg.min_query_length
    results = complex_search(query_text) if query_text and not too_short else []

    return render_template(
        "search/advanced.html",
        query_text=query_text,
        results=results,
        too_short=too_short,
        min_query_length=cfg.min_query_length,
    )


@bp.route("/asociaza", methods=["POST"])
@csrf.exempt
def asociaza():
    data = request.get_json()
    pid = data.get("product_id")
    aid = data.get("asociat_id")

    if not pid or not aid:
        return jsonify({"error": "ID-uri lipsa"}), 400

    p = CompetitorProduct.query.get(int(pid))
    a = CompetitorProduct.query.get(int(aid))

    if not p or not a:
        return jsonify({"error": "Produs negasit"}), 404

    if p.id == a.id:
        return jsonify({"error": "Nu poti asocia un produs cu el insusi"}), 400

    def _add(product, other_id):
        current = [x for x in (product.asociere or "").split(";") if x]
        if str(other_id) not in current:
            current.append(str(other_id))
            product.asociere = ";".join(current)

    _add(p, a.id)
    _add(a, p.id)
    db.session.commit()

    return jsonify({"ok": True, "asociere_p": p.asociere, "asociere_a": a.asociere})

