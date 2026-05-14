from flask import Blueprint, jsonify, render_template, request

from app.extensions import csrf, db
from app.models.competitor_product import CompetitorProduct
from app.services.cleanup_service import clean_product

bp = Blueprint("cleanup", __name__)


@bp.route("/", methods=["GET"])
def index():
    """Analizeaza DB si returneaza statistici."""
    products = CompetitorProduct.query.all()

    dirty = []
    stats = {'html': 0, 'url': 0, 'filepath': 0, 'entity': 0, 'total_dirty': 0}

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
