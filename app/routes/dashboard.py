from flask import Blueprint, render_template

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct


bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    total_products = CompetitorProduct.query.count()
    competitors = Competitor.query.count()
    return render_template("dashboard/index.html", total_products=total_products, competitors=competitors)
