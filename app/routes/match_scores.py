from flask import Blueprint, jsonify, redirect, render_template, request, url_for, flash

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.models.matching_rule import MatchingRule
from app.models.product_match_score import ProductMatchScore

bp = Blueprint("match_scores", __name__)


# ── Pagina de reguli ──────────────────────────────────────────────────────────

@bp.route("/rules")
def rules():
    all_rules = MatchingRule.query.order_by(MatchingRule.id.asc()).all()
    return render_template("match_scores/rules.html", rules=all_rules)


@bp.route("/rules/save", methods=["POST"])
@csrf.exempt
def rules_save():
    data = request.get_json(silent=True) or {}
    rule_id = data.get("id")
    name    = (data.get("name") or "").strip()
    weight  = data.get("weight")
    params  = data.get("params")
    is_active = data.get("is_active")

    if rule_id:
        rule = MatchingRule.query.get_or_404(int(rule_id))
        if name:
            rule.name = name
        if weight is not None:
            rule.weight = float(weight)
        if params is not None:
            import json
            rule.params = json.dumps(params) if isinstance(params, dict) else (params or None)
        if is_active is not None:
            rule.is_active = bool(is_active)
    else:
        rule_type = (data.get("rule_type") or "").strip()
        if not name or not rule_type:
            return jsonify({"error": "name si rule_type obligatorii"}), 400
        import json
        rule = MatchingRule(
            name=name,
            rule_type=rule_type,
            description=(data.get("description") or "").strip() or None,
            weight=float(weight or 0.5),
            is_active=bool(is_active if is_active is not None else True),
            params=json.dumps(params) if isinstance(params, dict) else (params or None),
            is_system=False,
        )
        db.session.add(rule)

    db.session.commit()
    return jsonify(rule.as_dict())


@bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
@csrf.exempt
def rules_toggle(rule_id):
    rule = MatchingRule.query.get_or_404(rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    return jsonify({"is_active": rule.is_active})


@bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
@csrf.exempt
def rules_delete(rule_id):
    rule = MatchingRule.query.get_or_404(rule_id)
    if rule.is_system:
        return jsonify({"error": "Regulile sistem nu pot fi sterse"}), 403
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Rulare scoring ────────────────────────────────────────────────────────────

@bp.route("/run", methods=["POST"])
@csrf.exempt
def run():
    """Ruleaza motorul de scoring pentru produsele selectate si salveaza in DB."""
    data = request.get_json(silent=True) or {}
    product_ids = [int(x) for x in (data.get("product_ids") or []) if str(x).isdigit()]
    target_competitors = data.get("target_competitors") or None
    min_score = float(data.get("min_score") or 0.40)

    if not product_ids:
        return jsonify({"error": "Niciun produs selectat"}), 400

    from app.services.scoring_engine import run_scoring_for_product
    rules = MatchingRule.get_active()

    saved_total = 0
    results_summary = []

    for pid in product_ids:
        source = CompetitorProduct.query.get(pid)
        if not source:
            continue

        scored = run_scoring_for_product(
            source, target_competitors=target_competitors, rules=rules, min_score=min_score
        )

        count = 0
        for cand, score, breakdown in scored:
            ProductMatchScore.upsert(pid, cand.id, score, breakdown)
            count += 1

        saved_total += count
        results_summary.append({"product_id": pid, "matches_found": count})

    db.session.commit()

    # Cel mai bun scor pending per produs (pentru actualizare celula in UI)
    best_scores = {}
    for pid in product_ids:
        best = (
            ProductMatchScore.query
            .filter_by(product_id=pid, status="pending")
            .order_by(ProductMatchScore.score.desc())
            .first()
        )
        if best:
            best_scores[str(pid)] = round(best.score * 100)

    return jsonify({"ok": True, "saved": saved_total, "results": results_summary, "best_scores": best_scores})


# ── Pagina de confirmare ──────────────────────────────────────────────────────

@bp.route("/review")
def review():
    status_filter = request.args.get("status", "pending")
    min_score_filter = request.args.get("min_score", 0.0, type=float)
    competitor_filter = request.args.get("competitor", "")
    page = request.args.get("page", 1, type=int)

    q = ProductMatchScore.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if min_score_filter > 0:
        q = q.filter(ProductMatchScore.score >= min_score_filter)
    q = q.order_by(ProductMatchScore.score.desc(), ProductMatchScore.created_at.desc())

    pagination = q.paginate(page=page, per_page=50, error_out=False)
    records = pagination.items

    # Preia produsele sursa + candidate
    all_ids = set()
    for r in records:
        all_ids.add(r.product_id)
        all_ids.add(r.matched_product_id)

    products_map = {}
    if all_ids:
        products_map = {p.id: p for p in CompetitorProduct.query.filter(CompetitorProduct.id.in_(all_ids)).all()}

    comp_codes = {p.cod_competitor for p in products_map.values()}
    comp_map = {
        c.internal_code: c.display_name
        for c in Competitor.query.filter(Competitor.internal_code.in_(comp_codes)).all()
    } if comp_codes else {}

    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()

    # Statistici
    stats = {
        "pending":   ProductMatchScore.query.filter_by(status="pending").count(),
        "confirmed": ProductMatchScore.query.filter_by(status="confirmed").count(),
        "rejected":  ProductMatchScore.query.filter_by(status="rejected").count(),
    }

    return render_template(
        "match_scores/review.html",
        records=records,
        pagination=pagination,
        products_map=products_map,
        comp_map=comp_map,
        competitors=competitors,
        status_filter=status_filter,
        min_score_filter=min_score_filter,
        competitor_filter=competitor_filter,
        stats=stats,
    )


@bp.route("/confirm", methods=["POST"])
@csrf.exempt
def confirm():
    data = request.get_json(silent=True) or {}
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not ids:
        return jsonify({"error": "Niciun ID"}), 400

    from app.models.product_association import ProductAssociation
    from datetime import datetime

    confirmed = 0
    for rid in ids:
        rec = ProductMatchScore.query.get(rid)
        if not rec or rec.status == "confirmed":
            continue
        ProductAssociation.add(rec.product_id, rec.matched_product_id)
        rec.status = "confirmed"
        rec.confirmed_at = datetime.utcnow()
        confirmed += 1

    db.session.commit()
    return jsonify({"ok": True, "confirmed": confirmed})


@bp.route("/reject", methods=["POST"])
@csrf.exempt
def reject():
    data = request.get_json(silent=True) or {}
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not ids:
        return jsonify({"error": "Niciun ID"}), 400

    rejected = 0
    for rid in ids:
        rec = ProductMatchScore.query.get(rid)
        if not rec or rec.status == "rejected":
            continue
        rec.status = "rejected"
        rejected += 1

    db.session.commit()
    return jsonify({"ok": True, "rejected": rejected})


@bp.route("/delete", methods=["POST"])
@csrf.exempt
def delete():
    data = request.get_json(silent=True) or {}
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not ids:
        return jsonify({"error": "Niciun ID"}), 400
    ProductMatchScore.query.filter(ProductMatchScore.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True})
