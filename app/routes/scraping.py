import json
import threading
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import csrf, db
from app.models.competitor import Competitor
from app.models.scraping_config import ScrapingConfig
from app.models.scraping_url import ScrapingUrl
from app.models.scraping_log import ScrapingLog
from app.services.notification_service import create_notification

bp = Blueprint("scraping", __name__)

_jobs = {}  # code -> {status, progress, stats, job_id}


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
    job = _jobs.get(code, {})
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


# ── Test selector pe un URL ────────────────────────────────────────────────

@bp.route("/<code>/test", methods=["POST"])
@csrf.exempt
def test_url(code):
    from app.services.web_scraping_service import test_scrape_url
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
    return jsonify(test_scrape_url(url, selectors))


# ── Auto-discover selectori ────────────────────────────────────────────────

@bp.route("/<code>/discover", methods=["POST"])
@csrf.exempt
def discover_selectors(code):
    from app.services.web_scraping_service import auto_discover_selectors
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL necesar"}), 400
    return jsonify(auto_discover_selectors(url))


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

    pending = ScrapingUrl.query.filter_by(competitor_code=code, status="pending").count()
    if not pending:
        return jsonify({"error": "Nu exista URL-uri pending."}), 400
    if not config or not config.sel_title:
        return jsonify({"error": "Selectorul Titlu este obligatoriu (tab Selectori CSS)."}), 400
    if _jobs.get(code, {}).get("status") == "running":
        return jsonify({"error": "Job deja in executie."}), 409

    job_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    _jobs[code] = {"status": "running", "progress": [], "stats": {}, "job_id": job_id}
    app = current_app._get_current_object()

    def run():
        from app.services.web_scraping_service import scrape_product_page, _sleep_delay
        from app.models.competitor_product import CompetitorProduct
        from app.models.price_history import PriceHistory

        def log(status, message, url=None, duration_ms=None):
            entry = ScrapingLog(
                competitor_code=code, job_id=job_id,
                status=status, message=message,
                url=url, duration_ms=duration_ms
            )
            db.session.add(entry)
            db.session.commit()
            _jobs[code]["progress"].append({
                "status": status, "message": message,
                "url": url, "duration_ms": duration_ms,
                "ts": datetime.utcnow().strftime("%H:%M:%S"),
            })

        with app.app_context():
            try:
                selectors   = config.selectors()
                delay       = config.delay or 1.0
                randomize   = config.randomize_delay
                timeout     = config.timeout or 15
                max_retries = config.max_retries if config.max_retries is not None else 2
                retry_delay = config.retry_delay or 5.0
                user_agent  = config.user_agent or None

                pending_urls = ScrapingUrl.query.filter_by(
                    competitor_code=code, status="pending"
                ).order_by(ScrapingUrl.id.asc()).all()

                total = len(pending_urls)
                inserted = updated = errors = 0
                import_ts = datetime.utcnow()

                log("start", f"Job pornit: {total} URL-uri pending | delay={delay}s randomize={randomize} timeout={timeout}s retries={max_retries}")

                for idx, su in enumerate(pending_urls, 1):
                    # Verifica daca s-a cerut oprirea
                    if _jobs[code].get("stop_requested"):
                        _jobs[code]["status"] = "stopped"
                        log("done", f"Oprit manual la {idx-1}/{total}. {inserted} inserate, {updated} actualizate, {errors} erori.")
                        _jobs[code]["stats"] = {"total": total, "inserted": inserted, "updated": updated, "errors": errors}
                        return

                    result = scrape_product_page(
                        su.url, selectors,
                        timeout=timeout, max_retries=max_retries,
                        retry_delay=retry_delay, user_agent=user_agent
                    )
                    dur = result.get("duration_ms")

                    if result.get("error") or not result.get("title"):
                        su.status   = "error"
                        su.error_msg = result.get("error") or "Titlu negasit"
                        errors += 1
                        db.session.commit()
                        log("error", f"[{idx}/{total}] {su.error_msg}", url=su.url, duration_ms=dur)
                        _jobs[code]["progress"][-1].update({"current": idx, "total": total})
                        _sleep_delay(delay, randomize)
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

                    pret_str = f" | {result['pret']} lei" if result.get('pret') else ""
                    log("ok", f"[{idx}/{total}] {action} — {result['title'][:60]}{pret_str}",
                        url=su.url, duration_ms=dur)
                    _jobs[code]["progress"][-1].update({"current": idx, "total": total})

                    _sleep_delay(delay, randomize)

                stats = {"total": total, "inserted": inserted, "updated": updated, "errors": errors}
                _jobs[code]["stats"] = stats
                _jobs[code]["status"] = "done"
                log("done", f"Finalizat: {inserted} inserate, {updated} actualizate, {errors} erori din {total}")
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
                except Exception:
                    pass

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


# ── Stop job ──────────────────────────────────────────────────────────────

@bp.route("/<code>/stop", methods=["POST"])
@csrf.exempt
def stop_job(code):
    job = _jobs.get(code)
    if not job or job.get("status") != "running":
        return jsonify({"error": "Niciun job activ."}), 400
    job["stop_requested"] = True
    return jsonify({"ok": True})


# ── Job status polling ─────────────────────────────────────────────────────

@bp.route("/<code>/status", methods=["GET"])
@csrf.exempt
def job_status(code):
    job = _jobs.get(code)
    if not job:
        return jsonify({"status": "idle"})
    offset = int(request.args.get("offset", 0))
    new_progress = job["progress"][offset:]
    return jsonify({
        "status": job["status"],
        "progress": new_progress,
        "offset": offset + len(new_progress),
        "stats": job.get("stats", {}),
        "error": job.get("error"),
    })
