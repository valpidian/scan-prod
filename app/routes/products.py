from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.services.product_search_service import build_query

bp = Blueprint("products", __name__)


@bp.route("/")
def list_view():
    filters = {
        "competitor": request.args.get("competitor", "").strip(),
        "q": request.args.get("q", "").strip(),
        "sort": request.args.get("sort", "title").strip(),
        "direction": request.args.get("direction", "asc").strip(),
    }
    products = build_query(filters).all()
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    competitor_lookup = {c.internal_code: c.display_name for c in competitors}
    return render_template(
        "products/list.html",
        products=products,
        competitors=competitors,
        competitor_lookup=competitor_lookup,
        filters=filters,
    )


@bp.route("/<int:product_id>/edit", methods=["POST"])
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
