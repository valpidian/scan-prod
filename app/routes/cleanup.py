import re

from flask import Blueprint, jsonify, render_template, request

from app.extensions import csrf, db
from app.models.competitor_product import CompetitorProduct
from app.services.cleanup_service import clean_product

bp = Blueprint("cleanup", __name__)


def _strip_sku_prefix(sku, prefix):
    """Sterge prefix-ul din SKU (case-insensitive), plus orice separatori ramasi (., :, -, |, _)."""
    if not sku or not prefix:
        return sku
    pattern = re.compile(r'^\s*' + re.escape(prefix.strip()) + r'[\s.:\-|_]*', re.IGNORECASE)
    return pattern.sub('', sku).strip()


@bp.route("/", methods=["GET"])
def index():
    """Analizeaza DB si returneaza statistici."""
    from app.models.competitor import Competitor
    products = CompetitorProduct.query.all()
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()

    dirty = []
    stats = {'html': 0, 'url': 0, 'filepath': 0, 'entity': 0, 'pret_format': 0, 'total_dirty': 0}

    for p in products:
        changes, issues = clean_product(p)
        if changes:
            stats['total_dirty'] += 1
            for issue in issues:
                if issue in stats:
                    stats[issue] += 1
            dirty.append({
                'id': p.id,
                'sku': p.sku,
                'title': p.title[:60] + ('...' if p.title and len(p.title) > 60 else ''),
                'cod_competitor': p.cod_competitor,
                'issues': issues,
                'fields': list(changes.keys()),
            })

    return render_template(
        "cleanup/index.html",
        dirty=dirty,
        stats=stats,
        total=len(products),
        competitors=competitors,
    )


@bp.route("/preview/<int:product_id>", methods=["GET"])
def preview(product_id):
    """Returneaza preview curatare pentru un produs."""
    p = CompetitorProduct.query.get_or_404(product_id)
    changes, issues = clean_product(p)
    return jsonify({'id': p.id, 'changes': changes, 'issues': issues})


@bp.route("/apply/<int:product_id>", methods=["POST"])
@csrf.exempt
def apply_one(product_id):
    """Aplica curatarea pe un singur produs."""
    p = CompetitorProduct.query.get_or_404(product_id)
    changes, _ = clean_product(p)
    for field, vals in changes.items():
        setattr(p, field, vals['after'])
    db.session.commit()
    return jsonify({'ok': True, 'changes': len(changes)})


@bp.route("/apply-all", methods=["POST"])
@csrf.exempt
def apply_all():
    """Aplica curatarea pe toate produsele murdare."""
    ids = request.get_json().get('ids', [])
    count = 0
    for pid in ids:
        p = CompetitorProduct.query.get(pid)
        if not p:
            continue
        changes, _ = clean_product(p)
        for field, vals in changes.items():
            setattr(p, field, vals['after'])
        if changes:
            count += 1
    db.session.commit()
    return jsonify({'ok': True, 'cleaned': count})


@bp.route("/sku-strip/preview", methods=["POST"])
@csrf.exempt
def sku_strip_preview():
    """Preview: cate SKU-uri contin prefix-ul si cum ar arata dupa stergere."""
    data = request.get_json() or {}
    prefix = (data.get("prefix") or "").strip()
    competitor = (data.get("competitor") or "").strip()
    if not prefix:
        return jsonify({"error": "Prefix lipsa"}), 400

    q = CompetitorProduct.query
    if competitor:
        q = q.filter_by(cod_competitor=competitor)
    products = q.all()

    matches = []
    for p in products:
        new_sku = _strip_sku_prefix(p.sku, prefix)
        if new_sku != p.sku:
            matches.append({
                "id": p.id,
                "cod_competitor": p.cod_competitor,
                "sku_before": p.sku,
                "sku_after": new_sku,
                "title": (p.title or "")[:80],
            })

    return jsonify({
        "count": len(matches),
        "items": matches,
    })


@bp.route("/sku-strip/apply-one/<int:product_id>", methods=["POST"])
@csrf.exempt
def sku_strip_apply_one(product_id):
    """Aplica stergerea prefix-ului pe un singur produs."""
    data = request.get_json() or {}
    prefix = (data.get("prefix") or "").strip()
    if not prefix:
        return jsonify({"error": "Prefix lipsa"}), 400

    p = CompetitorProduct.query.get_or_404(product_id)
    new_sku = _strip_sku_prefix(p.sku, prefix)
    changed = new_sku != p.sku
    if changed:
        p.sku = new_sku
        db.session.commit()
    return jsonify({"ok": True, "changed": changed, "sku": new_sku})


@bp.route("/sku-strip/apply-selection", methods=["POST"])
@csrf.exempt
def sku_strip_apply_selection():
    """Aplica stergerea prefix-ului pe o selectie de produse (dupa ID)."""
    data = request.get_json() or {}
    prefix = (data.get("prefix") or "").strip()
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not prefix:
        return jsonify({"error": "Prefix lipsa"}), 400
    if not ids:
        return jsonify({"error": "Niciun ID selectat"}), 400

    products = CompetitorProduct.query.filter(CompetitorProduct.id.in_(ids)).all()
    updated = 0
    for p in products:
        new_sku = _strip_sku_prefix(p.sku, prefix)
        if new_sku != p.sku:
            p.sku = new_sku
            updated += 1
    db.session.commit()
    return jsonify({"ok": True, "updated": updated})


@bp.route("/sku-strip/apply", methods=["POST"])
@csrf.exempt
def sku_strip_apply():
    """Aplica stergerea prefix-ului din toate SKU-urile care il contin."""
    data = request.get_json() or {}
    prefix = (data.get("prefix") or "").strip()
    competitor = (data.get("competitor") or "").strip()
    if not prefix:
        return jsonify({"error": "Prefix lipsa"}), 400

    q = CompetitorProduct.query
    if competitor:
        q = q.filter_by(cod_competitor=competitor)
    products = q.all()

    updated = 0
    for p in products:
        new_sku = _strip_sku_prefix(p.sku, prefix)
        if new_sku != p.sku:
            p.sku = new_sku
            updated += 1
    db.session.commit()
    return jsonify({"ok": True, "updated": updated})
