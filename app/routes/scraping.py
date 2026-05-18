import json
import threading
from datetime import datetime

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, stream_with_context, url_for

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.models.scraping_config import ScrapingConfig
from app.models.scraping_url import ScrapingUrl
from app.models.scraping_log import ScrapingLog
from app.models.scraping_job import ScrapingJob
from app.services.notification_service import create_notification

bp = Blueprint("scraping", __name__)

# Cache in-memory pentru viteza (progress entries, stop flag)
# Persista in ScrapingJob pentru supravietuire la restart
_jobs = {}  # code -> {status, progress, stats, job_id, stop_requested}


# ── Index ──────────────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def index():
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    configs = {c.competitor_code: c for c in ScrapingConfig.query.all()}
    url_counts = {}
    for c in competitors:
        url_counts[c.internal_code] = ScrapingUrl.query.filter_by(competitor_code=c.internal_code).count()
    return render_template("scraping/index.html", competitors=competitors, configs=configs, url_counts=url_counts)


# ── Config page ────────────────────────────────────────────────────────────

@bp.route("/<code>", methods=["GET"])
def config_view(code):
    competitor = Competitor.query.filter_by(internal_code=code).first_or_404()
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()

    page = int(request.args.get("page", 1))
    per_page = 50
    q = ScrapingUrl.query.filter_by(competitor_code=code)
    total_urls = q.count()
    urls_page = q.order_by(ScrapingUrl.id.asc()).paginate(page=page, per_page=per_page, error_out=False)

    stats = {
        "total":   total_urls,
        "pending": ScrapingUrl.query.filter_by(competitor_code=code, status="pending").count(),
        "scraped": ScrapingUrl.query.filter_by(competitor_code=code, status="scraped").count(),
        "error":   ScrapingUrl.query.filter_by(competitor_code=code, status="error").count(),
    }
    # Preia starea job-ului din cache in-memory
    job = _jobs.get(code)
    if job is None:
        db_job = ScrapingJob.get_running(code)
        if db_job:
            # Job "running" in DB dar fara thread activ in memorie = crash/restart server.
            # Il marcam ca eroare imediat — nu il "reconectam" ca activ.
            db_job.status = "error"
            db_job.finished_at = datetime.utcnow()
            db.session.commit()
        job = {}
    return render_template(
        "scraping/config.html",
        competitor=competitor,
        config=config,
        urls_page=urls_page,
        stats=stats,
        job=job,
    )


# ── Save config ────────────────────────────────────────────────────────────

@bp.route("/<code>/save", methods=["POST"])
def save_config(code):
    Competitor.query.filter_by(internal_code=code).first_or_404()
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()
    if not config:
        config = ScrapingConfig(competitor_code=code)
        db.session.add(config)

    config.sel_sku        = request.form.get("sel_sku", "").strip() or None
    config.sel_title      = request.form.get("sel_title", "").strip() or None
    config.sel_pret       = request.form.get("sel_pret", "").strip() or None
    config.sel_brand      = request.form.get("sel_brand", "").strip() or None
    config.sel_descriere  = request.form.get("sel_descriere", "").strip() or None
    config.sel_categorie  = request.form.get("sel_categorie", "").strip() or None
    config.url_filter     = request.form.get("url_filter", "").strip() or None
    config.user_agent     = request.form.get("user_agent", "").strip() or None
    try: config.delay           = float(request.form.get("delay", "1.0"))
    except ValueError: config.delay = 1.0
    try: config.timeout         = int(request.form.get("timeout", "15"))
    except ValueError: config.timeout = 15
    try: config.max_retries     = int(request.form.get("max_retries", "2"))
    except ValueError: config.max_retries = 2
    try: config.retry_delay     = float(request.form.get("retry_delay", "5.0"))
    except ValueError: config.retry_delay = 5.0
    config.randomize_delay = request.form.get("randomize_delay") == "1"
    config.respect_robots  = request.form.get("respect_robots") == "1"
    config.block_resources = request.form.get("block_resources") == "1"

    db.session.commit()
    flash("Configuratie salvata.", "success")
    return redirect(url_for("scraping.config_view", code=code))


# ── Analyze sitemap → save URLs in DB ─────────────────────────────────────

@bp.route("/<code>/analyze-sitemap", methods=["POST"])
@csrf.exempt
def analyze_sitemap(code):
    """Fetch sitemap, extrage URL-uri, le salveaza in DB (deduplicat), returneaza stats."""
    from app.services.web_scraping_service import fetch_sitemap_urls
    Competitor.query.filter_by(internal_code=code).first_or_404()

    data = request.get_json()
    sitemap_url = (data.get("sitemap_url") or "").strip()
    url_filter  = (data.get("url_filter") or "").strip() or None
    replace     = data.get("replace", False)  # daca True, sterge URL-urile existente

    if not sitemap_url:
        return jsonify({"error": "URL sitemap necesar"}), 400

    try:
        urls = fetch_sitemap_urls(sitemap_url, url_filter)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 422

    if replace:
        ScrapingUrl.query.filter_by(competitor_code=code).delete()
        db.session.commit()

    # Deduplicare fata de ce exista deja
    existing = {r.url for r in ScrapingUrl.query.filter_by(competitor_code=code).with_entities(ScrapingUrl.url).all()}
    new_urls = [u for u in urls if u not in existing]

    for u in new_urls:
        db.session.add(ScrapingUrl(competitor_code=code, url=u, status="pending"))
    db.session.commit()

    # Salveaza sitemap_url in config
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()
    if not config:
        config = ScrapingConfig(competitor_code=code)
        db.session.add(config)
    config.sources = json.dumps([{"type": "sitemap", "url": sitemap_url}])
    config.url_filter = url_filter
    db.session.commit()

    return jsonify({
        "total": len(urls),
        "added": len(new_urls),
        "existing": len(existing),
    })


# ── URLs list (AJAX paginare) ──────────────────────────────────────────────

@bp.route("/<code>/urls", methods=["GET"])
@csrf.exempt
def urls_list(code):
    page = int(request.args.get("page", 1))
    per_page = 50
    status_filter = request.args.get("status", "")

    q = ScrapingUrl.query.filter_by(competitor_code=code)
    if status_filter:
        q = q.filter_by(status=status_filter)

    total = q.count()
    items = q.order_by(ScrapingUrl.id.asc()).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "items": [
            {
                "id": u.id,
                "url": u.url,
                "status": u.status,
                "product_id": u.product_id,
                "product_title": u.product.title if u.product else None,
                "product_sku": u.product.sku if u.product else None,
                "error_msg": u.error_msg,
                "scraped_at": u.scraped_at.isoformat() if u.scraped_at else None,
            }
            for u in items
        ],
    })


# ── Delete all URLs ────────────────────────────────────────────────────────

@bp.route("/<code>/urls/clear", methods=["POST"])
@csrf.exempt
def clear_urls(code):
    Competitor.query.filter_by(internal_code=code).first_or_404()
    ScrapingUrl.query.filter_by(competitor_code=code).delete()
    db.session.commit()
    return jsonify({"ok": True})


# ── Reset status URL-uri ──────────────────────────────────────────────────

@bp.route("/<code>/urls/reset", methods=["POST"])
@csrf.exempt
def reset_urls(code):
    """Reseteaza status URL-uri la 'pending'.
    which: 'errors' | 'scraped' | 'all' | 'suspicious'
    suspicious = produse fara pret sau cu titlu generic/scurt"""
    from app.models.competitor_product import CompetitorProduct
    Competitor.query.filter_by(internal_code=code).first_or_404()
    data = request.get_json() or {}
    which = data.get("which", "errors")

    GENERIC_TITLES = {
        "home", "acasa", "index", "404", "403", "500",
        "not found", "page not found", "error", "forbidden",
        "maintenance", "se incarca", "loading", "redirecting",
        "access denied", "robot check", "blocked", "captcha",
    }

    q = ScrapingUrl.query.filter_by(competitor_code=code)

    if which == "errors":
        q = q.filter(ScrapingUrl.status == "error")
    elif which == "scraped":
        q = q.filter(ScrapingUrl.status == "scraped")
    elif which == "suspicious":
        # Gaseste URL-urile scraped cu produse suspecte
        scraped_urls = q.filter(
            ScrapingUrl.status == "scraped",
            ScrapingUrl.product_id.isnot(None)
        ).all()
        product_ids = [su.product_id for su in scraped_urls]
        products = {p.id: p for p in CompetitorProduct.query.filter(
            CompetitorProduct.id.in_(product_ids)
        ).all()} if product_ids else {}

        reset_count = 0
        for su in scraped_urls:
            p = products.get(su.product_id)
            if not p:
                continue
            t = (p.title or "").strip().lower()
            if t in GENERIC_TITLES or len(t) < 5 or p.pret is None:
                su.status = "pending"
                su.error_msg = None
                reset_count += 1
        db.session.commit()
        return jsonify({"ok": True, "reset": reset_count})
    # else: "all" — nicio filtrare suplimentara

    count = q.count()
    q.update({"status": "pending", "error_msg": None}, synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True, "reset": count})


# ── Verificare rezultate post-scraping ────────────────────────────────────

@bp.route("/<code>/verify", methods=["GET"])
def verify_results(code):
    """Verifica produsele scraped pentru titluri generice si preturi lipsa."""
    from app.models.competitor_product import CompetitorProduct
    Competitor.query.filter_by(internal_code=code).first_or_404()

    GENERIC_TITLES = {
        "home", "acasa", "index", "404", "403", "500",
        "not found", "page not found", "error", "forbidden",
        "maintenance", "se incarca", "loading", "redirecting",
        "access denied", "robot check", "blocked", "captcha",
    }

    scraped_urls = ScrapingUrl.query.filter_by(
        competitor_code=code, status="scraped"
    ).filter(ScrapingUrl.product_id.isnot(None)).all()

    total_scraped = len(scraped_urls)
    if not total_scraped:
        return jsonify({"total_scraped": 0, "suspicious_count": 0, "issues": {}})

    product_ids = [su.product_id for su in scraped_urls]
    products = {p.id: p for p in CompetitorProduct.query.filter(
        CompetitorProduct.id.in_(product_ids)
    ).all()}

    issues = {"titlu_generic": 0, "fara_pret": 0, "sku_auto": 0}
    suspicious_count = 0

    for su in scraped_urls:
        p = products.get(su.product_id)
        if not p:
            continue
        t = (p.title or "").strip().lower()
        has_issue = False
        if t in GENERIC_TITLES or len(t) < 5:
            issues["titlu_generic"] += 1
            has_issue = True
        if p.pret is None:
            issues["fara_pret"] += 1
            has_issue = True
        if p.sku and p.sku.startswith("sc-"):
            issues["sku_auto"] += 1
            has_issue = True
        if has_issue:
            suspicious_count += 1

    return jsonify({
        "total_scraped": total_scraped,
        "suspicious_count": suspicious_count,
        "issues": issues,
    })


# ── Curata URL-uri media ramase (imagini, PDF etc.) ────────────────────────

@bp.route("/<code>/urls/clean-media", methods=["POST"])
@csrf.exempt
def clean_media_urls(code):
    """Sterge URL-urile de imagini/media ramase din importuri anterioare."""
    from app.services.web_scraping_service import _is_page_url
    Competitor.query.filter_by(internal_code=code).first_or_404()
    all_urls = ScrapingUrl.query.filter_by(competitor_code=code).all()
    deleted = 0
    for su in all_urls:
        if not _is_page_url(su.url):
            db.session.delete(su)
            deleted += 1
    db.session.commit()
    return jsonify({"ok": True, "deleted": deleted})


# ── Test selector pe un URL ────────────────────────────────────────────────

@bp.route("/<code>/test", methods=["POST"])
@csrf.exempt
def test_url(code):
    from app.services.web_scraping_service import test_scrape_url, make_session
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()
    data = request.get_json()
    url = (data.get("url") or "").strip()
    selectors = {
        "sku":       (data.get("sel_sku") or "").strip() or None,
        "title":     (data.get("sel_title") or "").strip() or None,
        "pret":      (data.get("sel_pret") or "").strip() or None,
        "brand":     (data.get("sel_brand") or "").strip() or None,
        "descriere": (data.get("sel_descriere") or "").strip() or None,
        "categorie": (data.get("sel_categorie") or "").strip() or None,
    }
    if not url:
        return jsonify({"error": "URL-ul este necesar"}), 400
    user_agent = config.user_agent if config else None
    block_res = config.block_resources if config and config.block_resources is not None else True
    session = make_session(user_agent=user_agent, base_url=url, block_resources=block_res)
    return jsonify(test_scrape_url(url, selectors, session=session, user_agent=user_agent))


# ── Auto-discover selectori ────────────────────────────────────────────────

@bp.route("/<code>/discover", methods=["POST"])
@csrf.exempt
def discover_selectors(code):
    from app.services.web_scraping_service import auto_discover_selectors, make_session
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL necesar"}), 400
    user_agent = config.user_agent if config else None
    block_res = config.block_resources if config and config.block_resources is not None else True
    session = make_session(user_agent=user_agent, base_url=url, block_resources=block_res)
    return jsonify(auto_discover_selectors(url, user_agent=user_agent, session=session))


# ── Logs ───────────────────────────────────────────────────────────────────

@bp.route("/<code>/logs", methods=["GET"])
@csrf.exempt
def get_logs(code):
    job_id  = request.args.get("job_id", "")
    offset  = int(request.args.get("offset", 0))
    limit   = int(request.args.get("limit", 100))
    q = ScrapingLog.query.filter_by(competitor_code=code)
    if job_id:
        q = q.filter_by(job_id=job_id)
    total = q.count()
    items = q.order_by(ScrapingLog.id.asc()).offset(offset).limit(limit).all()
    return jsonify({
        "total": total,
        "items": [
            {
                "id": l.id, "status": l.status, "message": l.message,
                "url": l.url, "duration_ms": l.duration_ms,
                "ts": l.created_at.strftime("%H:%M:%S"),
            } for l in items
        ]
    })


@bp.route("/<code>/logs/delete", methods=["POST"])
@csrf.exempt
def delete_logs(code):
    """Sterge log-urile unui job (sau toate daca job_id lipseste)."""
    Competitor.query.filter_by(internal_code=code).first_or_404()
    data = request.get_json() or {}
    job_id = data.get("job_id")
    q = ScrapingLog.query.filter_by(competitor_code=code)
    if job_id:
        q = q.filter_by(job_id=job_id)
    deleted = q.delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True, "deleted": deleted})


@bp.route("/<code>/logs/jobs", methods=["GET"])
@csrf.exempt
def get_log_jobs(code):
    """Lista job-urilor distincte (job_id + prima intrare start)."""
    rows = db.session.execute(
        db.text("""
            SELECT job_id, MIN(created_at) as started, COUNT(*) as entries,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as ok_count,
                   SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as err_count
            FROM scraping_logs
            WHERE competitor_code = :code
            GROUP BY job_id ORDER BY started DESC LIMIT 20
        """),
        {"code": code}
    ).fetchall()
    return jsonify([{
        "job_id": r[0],
        "started": r[1][:16] if r[1] else "",
        "entries": r[2], "ok": r[3], "errors": r[4]
    } for r in rows])


# ── Start scraping job ─────────────────────────────────────────────────────

@bp.route("/<code>/start", methods=["POST"])
@csrf.exempt
def start_job(code):
    Competitor.query.filter_by(internal_code=code).first_or_404()
    config = ScrapingConfig.query.filter_by(competitor_code=code).first()

    data = request.get_json() or {}
    include_errors = data.get("include_errors", False)
    random_order   = data.get("random_order", False)

    statuses = ["pending"] + (["error"] if include_errors else [])
    pending = ScrapingUrl.query.filter_by(competitor_code=code).filter(
        ScrapingUrl.status.in_(statuses)
    ).count()
    if not pending:
        return jsonify({"error": "Nu exista URL-uri de procesat."}), 400
    if not config or not config.sel_title:
        return jsonify({"error": "Selectorul Titlu este obligatoriu (tab Selectori CSS)."}), 400
    # Verifica in cache SI in DB (pentru robustete dupa restart)
    if _jobs.get(code, {}).get("status") == "running":
        return jsonify({"error": "Job deja in executie."}), 409
    db_running = ScrapingJob.get_running(code)
    if db_running:
        # Job "running" in DB — verifica daca mai exista thread activ in memorie.
        # Daca nu, job-ul a crashat fara sa-si actualizeze statusul (ex: restart server).
        # Il marcam automat ca eroare in loc sa blocam pornirea.
        if code not in _jobs:
            db_running.status = "error"
            db_running.finished_at = datetime.utcnow()
            db.session.commit()
        else:
            return jsonify({"error": "Job deja in executie (DB)."}), 409

    job_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Extrage valorile din config ca primitive INAINTE de a porni thread-ul.
    # Instanta ORM este legata de sesiunea cererii curente care se inchide
    # inainte ca thread-ul sa ruleze, cauzand "not bound to a Session".
    if config:
        _selectors   = config.selectors()
        _delay       = config.delay or 1.0
        _randomize   = config.randomize_delay
        _timeout     = config.timeout or 15
        _max_retries = config.max_retries if config.max_retries is not None else 2
        _retry_delay = config.retry_delay or 5.0
        _user_agent  = config.user_agent or None
        _block_res   = config.block_resources if config.block_resources is not None else True
    else:
        _selectors   = {}
        _delay       = 1.0
        _randomize   = True
        _timeout     = 15
        _max_retries = 2
        _retry_delay = 5.0
        _user_agent  = None
        _block_res   = True

    # Persista job-ul in DB
    db_job = ScrapingJob(job_id=job_id, competitor_code=code, status="running")
    db.session.add(db_job)
    db.session.commit()

    _ts = datetime.utcnow().strftime("%H:%M:%S")
    _jobs[code] = {
        "status": "running",
        "progress": [{
            "status": "start",
            "message": f"Job {job_id} pornit, se initializeaza thread-ul...",
            "url": None, "duration_ms": None, "ts": _ts,
        }],
        "stats": {},
        "job_id": job_id, "stop_requested": False,
    }
    app = current_app._get_current_object()

    def run():
        # Prinde erori de import inainte de app context — altfel thread-ul moare silentios
        try:
            from app.services.web_scraping_service import scrape_product_page, _sleep_delay, make_session
            from app.models.competitor_product import CompetitorProduct
            from app.models.price_history import PriceHistory
        except Exception as _import_err:
            _jobs[code]["status"] = "error"
            _jobs[code]["error"] = str(_import_err)
            _jobs[code]["progress"].append({
                "status": "error",
                "message": f"Eroare import servicii: {_import_err}",
                "url": None, "duration_ms": None,
                "ts": datetime.utcnow().strftime("%H:%M:%S"),
            })
            return

        # Confirma ca thread-ul a pornit (vizibil in log inainte de app context)
        _jobs[code]["progress"].append({
            "status": "start",
            "message": "Thread activ, se pregateste contextul aplicatiei...",
            "url": None, "duration_ms": None,
            "ts": datetime.utcnow().strftime("%H:%M:%S"),
        })

        def log(status, message, url=None, duration_ms=None, current=None, total=None):
            entry = {
                "status": status, "message": message,
                "url": url, "duration_ms": duration_ms,
                "ts": datetime.utcnow().strftime("%H:%M:%S"),
            }
            if current is not None:
                entry["current"] = current
            if total is not None:
                entry["total"] = total
            _jobs[code]["progress"].append(entry)
            # Scrie in DB in context separat pentru a nu bloca thread-ul la erori DB
            try:
                entry = ScrapingLog(
                    competitor_code=code, job_id=job_id,
                    status=status, message=message,
                    url=url, duration_ms=duration_ms
                )
                db.session.add(entry)
                db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass

        def _stopped():
            return bool(_jobs[code].get("stop_requested"))

        def _sleep_interruptible(delay, randomize):
            """Sleep care se intrerupe imediat la cerere de stop (verifica la 200ms)."""
            import time as _t
            import random as _rand
            if delay <= 0:
                return
            actual = delay * _rand.uniform(0.5, 1.5) if randomize else float(delay)
            end = _t.time() + actual
            while _t.time() < end:
                if _stopped():
                    return
                _t.sleep(min(0.2, max(0, end - _t.time())))

        with app.app_context():
            try:
                selectors   = _selectors
                delay       = _delay
                randomize   = _randomize
                timeout     = _timeout
                max_retries = _max_retries
                retry_delay = _retry_delay
                user_agent  = _user_agent

                _statuses = ["pending"] + (["error"] if include_errors else [])
                pending_urls = ScrapingUrl.query.filter_by(
                    competitor_code=code
                ).filter(
                    ScrapingUrl.status.in_(_statuses)
                ).order_by(ScrapingUrl.id.asc()).all()

                if random_order:
                    import random as _random
                    _random.shuffle(pending_urls)

                # Session HTTP persistenta — refoloseste TCP + pastreaza cookies
                block_res = _block_res
                job_session = make_session(
                    user_agent=user_agent,
                    base_url=pending_urls[0].url if pending_urls else None,
                    block_resources=block_res,
                )

                total = len(pending_urls)
                inserted = updated = errors = 0
                import_ts = datetime.utcnow()

                extras = []
                if include_errors: extras.append("include_errors")
                if random_order:   extras.append("random_order")
                extras_str = f" | {','.join(extras)}" if extras else ""
                log("start", f"Job pornit: {total} URL-uri | delay={delay}s randomize={randomize} timeout={timeout}s retries={max_retries}{extras_str}")

                from app.services.web_scraping_service import _is_page_url
                from urllib.parse import urlparse

                for idx, su in enumerate(pending_urls, 1):
                    if _stopped():
                        _jobs[code]["status"] = "stopped"
                        log("done", f"Oprit manual la {idx-1}/{total}. {inserted} inserate, {updated} actualizate, {errors} erori.")
                        _jobs[code]["stats"] = {"total": total, "inserted": inserted, "updated": updated, "errors": errors}
                        db_job = ScrapingJob.get_by_job_id(job_id)
                        if db_job:
                            db_job.status = "stopped"; db_job.finished_at = datetime.utcnow()
                            db_job.total = total; db_job.inserted = inserted
                            db_job.updated = updated; db_job.errors = errors
                            db.session.commit()
                        return

                    # Sari peste URL-uri de imagini/media ramase accidental in BD
                    if not _is_page_url(su.url):
                        su.status = "error"
                        su.error_msg = "URL media (ignorat)"
                        db.session.commit()
                        continue

                    url_path = urlparse(su.url).path.rstrip("/")[-55:] or su.url[-55:]

                    result = scrape_product_page(
                        su.url, selectors,
                        timeout=timeout, max_retries=max_retries,
                        retry_delay=retry_delay, user_agent=user_agent,
                        session=job_session,
                    )
                    dur = result.get("duration_ms")

                    if result.get("error") or not result.get("title"):
                        err_short = (result.get("error") or "Titlu negasit")
                        err_short = err_short.split("\n")[0][:120]
                        su.status    = "error"
                        su.error_msg = err_short
                        errors += 1
                        db.session.commit()
                        log("error", f"[{idx}/{total}] {err_short} | {url_path}", url=su.url, duration_ms=dur, current=idx, total=total)
                        _sleep_interruptible(delay, randomize)
                        continue

                    sku = result["sku"] or f"sc-{code.lower()}-{su.id}"
                    existing = CompetitorProduct.query.filter_by(cod_competitor=code, sku=sku).first()

                    if existing:
                        pret_val = result["pret"]
                        if pret_val is not None and existing.pret != pret_val:
                            db.session.add(PriceHistory(product_id=existing.id, pret=pret_val, sursa="scraping"))
                        existing.title = result["title"]; existing.pret = result["pret"]
                        existing.url = su.url
                        if result["brand"]:     existing.brand = result["brand"]
                        if result["descriere"]: existing.descriere = result["descriere"]
                        if result["categorie"]: existing.categorie = result["categorie"]
                        existing.imported_at = import_ts
                        su.product_id = existing.id
                        updated += 1
                        action = "actualizat"
                    else:
                        prod = CompetitorProduct(
                            cod_competitor=code, sku=sku,
                            title=result["title"], pret=result["pret"],
                            brand=result["brand"], descriere=result["descriere"],
                            categorie=result["categorie"], url=su.url,
                            asociere="", imported_at=import_ts,
                        )
                        db.session.add(prod)
                        db.session.flush()
                        su.product_id = prod.id
                        inserted += 1
                        action = "inserat"

                    su.status = "scraped"
                    su.scraped_at = datetime.utcnow()
                    db.session.commit()

                    pret_str = f" | {result['pret']:.2f} lei" if result.get("pret") else " | fara pret"
                    sku_str  = f" | SKU:{result['sku']}" if result.get("sku") else ""
                    log("ok", f"[{idx}/{total}] {action} — {result['title'][:50]}{pret_str}{sku_str} | {url_path}",
                        url=su.url, duration_ms=dur, current=idx, total=total)

                    _sleep_interruptible(delay, randomize)

                stats = {"total": total, "inserted": inserted, "updated": updated, "errors": errors}
                _jobs[code]["stats"] = stats
                _jobs[code]["status"] = "done"
                log("done", f"Finalizat: {inserted} inserate, {updated} actualizate, {errors} erori din {total}")
                db_job = ScrapingJob.get_by_job_id(job_id)
                if db_job:
                    db_job.status = "done"; db_job.finished_at = datetime.utcnow()
                    db_job.total = total; db_job.inserted = inserted
                    db_job.updated = updated; db_job.errors = errors
                    db.session.commit()
                create_notification(
                    "Scraping finalizat",
                    f"{code}: {inserted} inserate, {updated} actualizate, {errors} erori.",
                    "success",
                )
            except Exception as exc:
                _jobs[code]["status"] = "error"
                _jobs[code]["error"] = str(exc)
                try:
                    log("error", f"Exceptie critica: {exc}")
                    db_job = ScrapingJob.get_by_job_id(job_id)
                    if db_job:
                        db_job.status = "error"; db_job.finished_at = datetime.utcnow()
                        db.session.commit()
                except Exception:
                    pass

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


# ── Force-reset job blocat ────────────────────────────────────────────────

@bp.route("/<code>/force-reset", methods=["POST"])
@csrf.exempt
def force_reset(code):
    """Curata un job 'running' ramas blocat in DB fara thread activ (ex: dupa crash)."""
    _jobs.pop(code, None)
    stale = ScrapingJob.query.filter_by(competitor_code=code, status="running").all()
    for j in stale:
        j.status = "error"
        j.finished_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "reset": len(stale)})


# ── Stop job ──────────────────────────────────────────────────────────────

@bp.route("/<code>/stop", methods=["POST"])
@csrf.exempt
def stop_job(code):
    job = _jobs.get(code)
    if not job or job.get("status") != "running":
        # Verifica si in DB (dupa restart)
        db_job = ScrapingJob.get_running(code)
        if not db_job:
            return jsonify({"error": "Niciun job activ."}), 400
        db_job.stop_requested = True
        db.session.commit()
        return jsonify({"ok": True})
    job["stop_requested"] = True
    # Persista si in DB ca sa supravietuiasca restart-ului
    db_job = ScrapingJob.get_by_job_id(job["job_id"])
    if db_job:
        db_job.stop_requested = True
        db.session.commit()
    return jsonify({"ok": True})


# ── Job status polling (fallback pentru browsere fara SSE) ────────────────

@bp.route("/<code>/status", methods=["GET"])
@csrf.exempt
def job_status(code):
    job = _jobs.get(code)
    if not job:
        # Fallback: citeste din DB
        db_job = ScrapingJob.query.filter_by(
            competitor_code=code
        ).order_by(ScrapingJob.started_at.desc()).first()
        if not db_job:
            return jsonify({"status": "idle"})
        return jsonify({
            "status": db_job.status,
            "progress": [],
            "offset": 0,
            "stats": db_job.as_dict(),
        })
    offset = int(request.args.get("offset", 0))
    new_progress = job["progress"][offset:]
    return jsonify({
        "status": job["status"],
        "progress": new_progress,
        "offset": offset + len(new_progress),
        "stats": job.get("stats", {}),
        "error": job.get("error"),
    })


# ── SSE stream ────────────────────────────────────────────────────────────

@bp.route("/<code>/stream", methods=["GET"])
def job_stream(code):
    """Server-Sent Events: trimite progresul job-ului fara polling."""
    import time

    def generate():
        offset = 0
        try:
            while True:
                job = _jobs.get(code)

                status  = job["status"] if job else "idle"
                entries = (job["progress"][offset:] if job else [])
                offset += len(entries)

                payload = {
                    "status": status,
                    "progress": entries,
                    "stats":  job.get("stats", {}) if job else {},
                    "error":  job.get("error")     if job else None,
                }
                yield f"data: {json.dumps(payload)}\n\n"

                if status not in ("running",):
                    return

                time.sleep(1.0)
        except GeneratorExit:
            pass
        except Exception as exc:
            try:
                yield f"data: {json.dumps({'status': 'error', 'progress': [], 'error': str(exc), 'stats': {}})}\n\n"
            except Exception:
                pass

    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp
