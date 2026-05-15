from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.services.competitor_service import create_or_get_competitor
from app.services.notification_service import create_notification


bp = Blueprint("competitors", __name__)


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        source_url = request.form.get("source_url", "").strip()
        if not source_url:
            flash("Completeaza URL-ul competitorului.", "warning")
            return redirect(url_for("competitors.index"))

        try:
            competitor, created = create_or_get_competitor(source_url)
            if created:
                create_notification(
                    "Competitor adaugat",
                    f"{competitor.internal_code} a fost generat pentru {competitor.display_name}.",
                    "success",
                )
                flash(f"Competitor creat: {competitor.internal_code} pentru {competitor.display_name}.", "success")
            else:
                flash(f"Competitor existent: {competitor.internal_code} pentru {competitor.display_name}.", "info")
        except Exception as exc:
            current_app.logger.exception("Create competitor failed")
            flash(str(exc), "danger")
        return redirect(url_for("competitors.index"))

    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    return render_template("competitors/index.html", competitors=competitors)


@bp.route("/<code>", methods=["GET"])
def detail(code):
    from app.models.competitor_product import CompetitorProduct
    competitor = Competitor.query.filter_by(internal_code=code).first_or_404()
    stats = {
        "total":     CompetitorProduct.query.filter_by(cod_competitor=code).count(),
        "cu_url":    CompetitorProduct.query.filter_by(cod_competitor=code).filter(
                         CompetitorProduct.url.isnot(None), CompetitorProduct.url != "").count(),
        "cu_pret":   CompetitorProduct.query.filter_by(cod_competitor=code).filter(
                         CompetitorProduct.pret.isnot(None)).count(),
        "cu_alerta": CompetitorProduct.query.filter_by(cod_competitor=code).filter(
                         CompetitorProduct.pret_alerta.isnot(None)).count(),
    }
    return render_template("competitors/detail.html", competitor=competitor, stats=stats)


@bp.route("/<code>/save", methods=["POST"])
def save(code):
    competitor = Competitor.query.filter_by(internal_code=code).first_or_404()
    competitor.display_name   = request.form.get("display_name", competitor.display_name).strip()
    competitor.price_selector = request.form.get("price_selector", "").strip() or None
    competitor.is_active      = request.form.get("is_active") == "1"
    db.session.commit()
    flash("Setari salvate.", "success")
    return redirect(url_for("competitors.detail", code=code))


@bp.route("/<code>/test-selector", methods=["POST"])
@csrf.exempt
def test_selector(code):
    from app.services.scraper_service import scrape_price
    data = request.get_json()
    url      = (data.get("url") or "").strip()
    selector = (data.get("selector") or "").strip()
    if not url or not selector:
        return jsonify({"error": "URL si selector sunt necesare"}), 400
    price = scrape_price(url, selector)
    if price is None:
        return jsonify({"error": "Nu s-a putut extrage pretul. Verifica URL-ul si selectorul."}), 422
    return jsonify({"ok": True, "price": price})


@bp.route("/<code>/selector", methods=["POST"])
@csrf.exempt
def update_selector(code):
    competitor = Competitor.query.filter_by(internal_code=code).first_or_404()
    data = request.get_json()
    competitor.price_selector = (data.get("selector") or "").strip() or None
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<code>/scrape", methods=["POST"])
@csrf.exempt
def scrape(code):
    from app.models.competitor_product import CompetitorProduct
    from app.models.price_history import PriceHistory
    from app.services.scraper_service import scrape_competitor_products

    competitor = Competitor.query.filter_by(internal_code=code).first_or_404()
    if not competitor.price_selector:
        return jsonify({"error": "Selectorul CSS nu este configurat pentru acest competitor."}), 400

    updated = 0
    errors = 0
    alerte = 0

    for result in scrape_competitor_products(code, competitor.price_selector, delay=0.5):
        product = CompetitorProduct.query.get(result["product_id"])
        if not product:
            continue
        if result["new_pret"] is None:
            errors += 1
            continue
        if result["changed"]:
            db.session.add(PriceHistory(
                product_id=product.id,
                pret=result["new_pret"],
                sursa="scraper",
            ))
            if product.pret_alerta and result["new_pret"] <= product.pret_alerta:
                create_notification(
                    "Alerta pret",
                    f"#{product.id} {product.title[:50]} → {result['new_pret']:.2f} lei"
                    f" (prag: {product.pret_alerta:.2f} lei)",
                    "warning",
                )
                alerte += 1
            product.pret = result["new_pret"]
            updated += 1

    db.session.commit()
    return jsonify({"ok": True, "updated": updated, "errors": errors, "alerte": alerte})
