import re
import time
import json
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from app.utils.normalizers import normalize_price
from app.utils.helpers import normalize_text

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

_BASE_HEADERS = {
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _make_headers(user_agent=None):
    ua = user_agent or random.choice(_USER_AGENTS)
    return {**_BASE_HEADERS, "User-Agent": ua}


def _get(url, timeout=15, user_agent=None):
    resp = requests.get(url, headers=_make_headers(user_agent), timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp


def _get_with_retry(url, timeout=15, max_retries=2, retry_delay=5.0, user_agent=None):
    """Fetch cu retry automat la erori 429/5xx. Returneaza (resp, duration_ms, error)."""
    last_error = None
    for attempt in range(max_retries + 1):
        t0 = time.time()
        try:
            resp = requests.get(
                url, headers=_make_headers(user_agent),
                timeout=timeout, allow_redirects=True
            )
            duration_ms = int((time.time() - t0) * 1000)
            if resp.status_code == 429:
                wait = retry_delay * (attempt + 1)
                last_error = f"HTTP 429 Too Many Requests (retry {attempt+1}/{max_retries}, wait {wait:.0f}s)"
                if attempt < max_retries:
                    time.sleep(wait)
                    continue
                return None, duration_ms, last_error
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code} (retry {attempt+1}/{max_retries})"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                return None, duration_ms, last_error
            resp.raise_for_status()
            return resp, duration_ms, None
        except requests.exceptions.Timeout:
            duration_ms = int((time.time() - t0) * 1000)
            last_error = f"Timeout dupa {timeout}s (retry {attempt+1}/{max_retries})"
            if attempt < max_retries:
                time.sleep(retry_delay)
        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            last_error = str(exc)
            if attempt < max_retries:
                time.sleep(retry_delay)
    return None, duration_ms, last_error


def _sleep_delay(delay, randomize=True):
    if delay <= 0:
        return
    if randomize:
        actual = delay * random.uniform(0.5, 1.5)
    else:
        actual = delay
    time.sleep(actual)


def fetch_sitemap_urls(sitemap_url, url_filter=None, timeout=15):
    """Extrage URL-uri dintr-un sitemap XML (inclusiv sitemap index)."""
    resp = _get(sitemap_url, timeout=timeout)
    soup = BeautifulSoup(resp.content, "xml")

    sitemaps = soup.find_all("sitemap")
    if sitemaps:
        urls = []
        for sm in sitemaps:
            loc = sm.find("loc")
            if loc:
                urls.extend(fetch_sitemap_urls(loc.text.strip(), url_filter, timeout))
        return urls

    locs = [tag.text.strip() for tag in soup.find_all("loc")]
    if url_filter:
        pattern = re.compile(url_filter, re.IGNORECASE)
        locs = [u for u in locs if pattern.search(u)]
    return locs


def collect_urls(sources, url_filter=None):
    seen = set()
    result = []
    for src in sources:
        src_type = src.get("type", "url")
        src_url = src.get("url", "").strip()
        if not src_url:
            continue
        if src_type == "sitemap":
            for u in fetch_sitemap_urls(src_url, url_filter):
                if u not in seen:
                    seen.add(u)
                    result.append(u)
        else:
            if src_url not in seen:
                seen.add(src_url)
                result.append(src_url)
    return result


def _extract(soup, selector):
    if not selector:
        return None
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else None


def scrape_product_page(url, selectors, timeout=15, max_retries=2, retry_delay=5.0, user_agent=None):
    resp, duration_ms, error = _get_with_retry(url, timeout=timeout, max_retries=max_retries,
                                               retry_delay=retry_delay, user_agent=user_agent)
    if error or resp is None:
        return {"url": url, "error": error or "No response", "duration_ms": duration_ms}
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        raw_pret = _extract(soup, selectors.get("pret"))
        pret_val = normalize_price(raw_pret) if raw_pret else None
        sku   = _extract(soup, selectors.get("sku")) or ""
        title = _extract(soup, selectors.get("title")) or ""
        return {
            "url": url,
            "sku":       normalize_text(sku) if sku else None,
            "title":     normalize_text(title) if title else None,
            "pret":      pret_val,
            "brand":     normalize_text(_extract(soup, selectors.get("brand")) or "") or None,
            "descriere": normalize_text(_extract(soup, selectors.get("descriere")) or "") or None,
            "categorie": normalize_text(_extract(soup, selectors.get("categorie")) or "") or None,
            "error":     None,
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        return {"url": url, "error": str(exc), "duration_ms": duration_ms}


def test_scrape_url(url, selectors, timeout=15):
    return scrape_product_page(url, selectors, timeout)


# ── Auto-descoperire selectori ─────────────────────────────────────────────

_CSS_HINTS = {
    "title": [
        "h1[itemprop='name']", "[itemprop='name']",
        "h1.product-title", "h1.product_title", "h1.entry-title",
        "h1.product-name", "h1",
    ],
    "pret": [
        "[itemprop='price']", "[data-price]",
        ".woocommerce-Price-amount", ".price ins .amount",
        ".product-price", ".current-price", ".special-price",
        ".price", "[class*='price']",
    ],
    "sku": [
        "[itemprop='sku']", ".sku span", ".sku",
        ".product-reference", "[class*='product-code']",
        "[class*='product-id']", "[class*='sku']",
    ],
    "brand": [
        "[itemprop='brand'] [itemprop='name']", "[itemprop='brand']",
        ".product-brand", ".brand a", ".brand",
        "[class*='brand']", "[itemprop='manufacturer']",
    ],
    "descriere": [
        "[itemprop='description']",
        ".product-short-description", ".product-description",
        "#tab-description", ".description", "[class*='description']",
    ],
    "categorie": [
        ".breadcrumb-item:last-child a", ".breadcrumb li:last-child a",
        ".breadcrumbs li:last-child a", ".breadcrumb li:last-child",
        "[itemprop='category']", "[class*='breadcrumb'] li:last-child",
    ],
}


def _css_selector_for(el):
    """Construieste cel mai specific selector CSS testabil pentru un element BS4."""
    tag = el.name
    itemprop = el.get("itemprop")
    if itemprop:
        return f"{tag}[itemprop='{itemprop}']"
    el_id = el.get("id")
    if el_id:
        return f"#{el_id}"
    classes = [c for c in (el.get("class") or []) if len(c) > 2]
    if classes:
        return f"{tag}." + ".".join(classes[:2])
    return tag


def _extract_structured(html, base_url):
    """
    Extrage campuri produs din JSON-LD / microdata / OpenGraph cu extruct.
    Returneaza dict {field: value}.
    """
    import extruct
    from price_parser import Price

    found = {}
    try:
        data = extruct.extract(
            html, base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
    except Exception:
        return found

    for syntax in ("json-ld", "microdata"):
        for item in data.get(syntax, []):
            typ = item.get("@type", "")
            if isinstance(typ, list):
                typ = " ".join(typ)
            if "product" not in typ.lower():
                continue
            if "name" in item and "title" not in found:
                found["title"] = str(item["name"])[:200]
            if "sku" in item and "sku" not in found:
                found["sku"] = str(item["sku"])
            if "brand" in item and "brand" not in found:
                b = item["brand"]
                found["brand"] = str(b.get("name", b) if isinstance(b, dict) else b)
            if "description" in item and "descriere" not in found:
                found["descriere"] = str(item["description"])[:300]
            if "category" in item and "categorie" not in found:
                found["categorie"] = str(item["category"])
            offers = item.get("offers") or item.get("Offers")
            if offers and "pret" not in found:
                if isinstance(offers, list):
                    offers = offers[0]
                raw = offers.get("price") or offers.get("lowPrice", "")
                p = Price.fromstring(str(raw))
                if p.amount:
                    found["pret"] = str(p.amount_text)

    for item in data.get("opengraph", []):
        props = {p["property"]: p["content"] for p in item.get("properties", [])}
        if "og:title" in props and "title" not in found:
            found["title"] = props["og:title"]

    return found


def auto_discover_selectors(url, timeout=15):
    """
    Nivel 1 — extruct: JSON-LD / microdata / OpenGraph → valori directe.
    Nivel 2 — CSS hints + price-parser: cauta in DOM selectori functionali.

    Returneaza dict:
    {
      field: {
        "source": "structured" | "css" | "not_found",
        "value": "...",          # preview valoare gasita
        "selector": "...",       # cel mai bun selector CSS
        "candidates": [{selector, preview, score}, ...]
      }
    }
    """
    from price_parser import Price

    try:
        resp = _get(url, timeout=timeout)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        return {"error": str(exc)}

    structured = _extract_structured(html, url)
    results = {}

    for field, hints in _CSS_HINTS.items():
        struct_val = structured.get(field)
        candidates = []
        seen = set()

        for hint in hints:
            try:
                els = soup.select(hint)
            except Exception:
                continue
            for el in els[:2]:
                text = el.get_text(strip=True)
                if not text:
                    continue
                # Validare per camp
                if field == "pret":
                    p = Price.fromstring(text)
                    if not p.amount:
                        raw_attr = el.get("data-price") or el.get("content") or ""
                        p2 = Price.fromstring(raw_attr)
                        if not p2.amount:
                            continue
                        text = raw_attr
                if field == "title" and len(text) > 300:
                    continue
                if field == "descriere" and len(text) < 10:
                    continue

                # Construieste selector specific; fallback la hint
                sel = _css_selector_for(el)
                try:
                    if not soup.select_one(sel):
                        sel = hint
                except Exception:
                    sel = hint

                if sel in seen:
                    continue
                seen.add(sel)

                score = max(10, 95 - hints.index(hint) * 10)
                if struct_val and struct_val[:50] in text:
                    score = 100  # confirmat de date structurate

                candidates.append({
                    "selector": sel,
                    "hint": hint,
                    "preview": text[:150],
                    "score": score,
                })

        candidates.sort(key=lambda x: -x["score"])

        results[field] = {
            "source": "structured" if struct_val else ("css" if candidates else "not_found"),
            "value": struct_val or (candidates[0]["preview"] if candidates else None),
            "selector": candidates[0]["selector"] if candidates else None,
            "candidates": candidates[:5],
        }

    return results


def run_scraping_job(competitor_code, config, progress_callback=None):
    from app.extensions import db
    from app.models.competitor_product import CompetitorProduct
    from app.models.price_history import PriceHistory
    from app.services.notification_service import create_notification

    sources = json.loads(config.sources or "[]")
    selectors = config.selectors()
    urls = collect_urls(sources, config.url_filter)

    total = len(urls)
    inserted = updated = errors = 0
    import_timestamp = datetime.utcnow()

    for idx, url in enumerate(urls, 1):
        result = scrape_product_page(url, selectors, timeout=15)

        if result.get("error") or not result.get("title"):
            errors += 1
            if progress_callback:
                progress_callback(idx, total, result)
            if config.delay > 0:
                time.sleep(config.delay)
            continue

        sku = result["sku"] or f"scraped-{idx}"
        title = result["title"]
        pret_val = result["pret"]

        existing = CompetitorProduct.query.filter_by(
            cod_competitor=competitor_code, sku=sku
        ).first()

        if existing:
            if pret_val is not None and existing.pret != pret_val:
                db.session.add(PriceHistory(product_id=existing.id, pret=pret_val, sursa="scraping"))
                if existing.pret_alerta and pret_val <= existing.pret_alerta:
                    create_notification(
                        "Alerta pret",
                        f"#{existing.id} {existing.title[:50]} → {pret_val:.2f} lei",
                        "warning",
                    )
            existing.title = title
            existing.pret = pret_val
            existing.url = url
            if result["brand"]:     existing.brand = result["brand"]
            if result["descriere"]: existing.descriere = result["descriere"]
            if result["categorie"]: existing.categorie = result["categorie"]
            existing.imported_at = import_timestamp
            updated += 1
        else:
            db.session.add(CompetitorProduct(
                cod_competitor=competitor_code,
                sku=sku,
                title=title,
                pret=pret_val,
                brand=result["brand"],
                descriere=result["descriere"],
                categorie=result["categorie"],
                url=url,
                asociere="",
                imported_at=import_timestamp,
            ))
            inserted += 1

        db.session.commit()

        if progress_callback:
            progress_callback(idx, total, result)
        if config.delay > 0:
            time.sleep(config.delay)

    return {"total": total, "inserted": inserted, "updated": updated, "errors": errors}
