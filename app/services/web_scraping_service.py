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
    # Nu include "br" — requests nu are Brotli nativ si returneaza bytes comprimate nedecodati
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def _make_headers(user_agent=None):
    ua = user_agent or random.choice(_USER_AGENTS)
    return {**_BASE_HEADERS, "User-Agent": ua}


def make_session(user_agent=None, base_url=None, block_resources=False):
    """Session requests cu headers browser-like complete.
    Refoloseste conexiunile TCP si pastreaza cookie-urile intre requesturi.

    block_resources=True: adauga header Accept restrictiv care semnaleaza
    serverului ca dorim doar HTML (nu imagini/CSS/JS). Nu blocheaza efectiv
    download-ul la nivel de TCP (pentru asta ar fi nevoie de Playwright),
    dar elimina URL-urile de resurse din coada de scraping si reduce
    traficul de erori 404 pentru fisierele media."""
    from urllib.parse import urlparse
    ua = user_agent or random.choice(_USER_AGENTS)
    # Intotdeauna browser-like — */* e necesar pentru Cloudflare/bot detection.
    # "block_resources" nu se refera la Accept header (care nu blocheaza oricum
    # imaginile separate), ci la filtrarea URL-urilor media din coada de scraping.
    accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    # Nu setam Accept-Encoding explicit: requests/urllib3 il seteaza automat
    # cu "gzip, deflate" (encoding-uri pe care le poate decoda). Daca specificam
    # "br" (Brotli) fara pachetul brotli instalat, serverul returneaza raspuns
    # comprimat Brotli pe care requests nu il poate decoda → resp.text e bytes
    # comprimate → BeautifulSoup nu gaseste nimic.
    headers = {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    if base_url:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers["Referer"] = origin + "/"
    s = requests.Session()
    s.headers.update(headers)
    return s


def _get(url, timeout=15, user_agent=None, session=None):
    if session:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
    else:
        resp = requests.get(url, headers=_make_headers(user_agent), timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp


def _get_with_retry(url, timeout=15, max_retries=2, retry_delay=5.0, user_agent=None, session=None):
    """Fetch cu retry automat la erori 429/5xx. Returneaza (resp, duration_ms, error)."""
    last_error = None
    for attempt in range(max_retries + 1):
        t0 = time.time()
        try:
            if session:
                resp = session.get(url, timeout=timeout, allow_redirects=True)
            else:
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


_MEDIA_EXTENSIONS = frozenset([
    # Imagini
    ".jpg", ".jpeg", ".jfif", ".pjpeg", ".pjp",
    ".png", ".gif", ".webp", ".svg", ".svgz",
    ".ico", ".bmp", ".tiff", ".tif", ".avif",
    ".heic", ".heif", ".raw", ".cr2", ".nef", ".dng",
    # Documente
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt",
    # Arhive
    ".zip", ".rar", ".7z", ".gz", ".tar", ".bz2", ".xz", ".zst",
    # Video
    ".mp4", ".avi", ".mov", ".wmv", ".mkv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv",
    # Audio
    ".mp3", ".ogg", ".wav", ".flac", ".aac", ".m4a", ".wma", ".opus",
    # Scripturi / stiluri
    ".css", ".js", ".ts", ".jsx", ".tsx", ".map", ".min",
    # Fonturi
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Executabile / date binare
    ".exe", ".dll", ".so", ".dmg", ".deb", ".rpm", ".apk",
    ".iso", ".img",
])


def _is_page_url(url):
    """Returneaza True doar pentru URL-uri de pagini HTML (nu imagini/media/scripturi)."""
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    last_segment = path.rsplit("/", 1)[-1]
    if "." in last_segment:
        ext = "." + last_segment.rsplit(".", 1)[-1].split("?")[0]
        return ext not in _MEDIA_EXTENSIONS
    return True


def fetch_sitemap_urls(sitemap_url, url_filter=None, timeout=15):
    """Extrage URL-uri dintr-un sitemap XML (inclusiv sitemap index).
    Filtreaza automat URL-uri de imagini/media (image:loc si extensii media)."""
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

    # find_all("loc") cu lxml xml preia si <image:loc> — pastram doar <loc> directe
    locs = []
    for tag in soup.find_all("loc"):
        # Excludem tagurile care sunt copii ai <image:*> sau <video:*>
        parent = tag.parent
        if parent and parent.name and ":" in parent.name:
            continue
        url = tag.text.strip()
        if _is_page_url(url):
            locs.append(url)

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
    if not el:
        return None
    # data-price-amount = valoarea numerica curata pe site-uri Magento/OpenMage.
    # HTML-ul afisat contine formatare cu <sup> (ex: 2.489<sup>99</sup>Lei) care
    # rupe get_text() in "2.48999Lei" → interpretare gresita de price_parser.
    dpa = el.get("data-price-amount")
    if dpa:
        return dpa.strip()
    text = el.get_text(strip=True)
    if text:
        return text
    for attr in ("content", "value", "datetime", "alt", "title"):
        val = el.get(attr)
        if val:
            return str(val).strip()
    return None


def _clean_meta_content(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r"\s+", " ", value).strip()


def _is_valid_meta_value(field, content):
    if not content or content in {".", "-", "|"}:
        return False
    if field == "title":
        return len(content) <= 300
    if field == "descriere":
        return len(content) >= 10
    if field == "pret":
        from price_parser import Price
        return bool(Price.fromstring(content).amount)
    return True


def _response_debug(resp, requested_url):
    if not resp:
        return {
            "requested_url": requested_url,
            "final_url": None,
            "status_code": None,
            "content_type": None,
            "redirects": [],
        }
    redirects = []
    for hop in getattr(resp, "history", []) or []:
        redirects.append({
            "status_code": hop.status_code,
            "url": hop.url,
            "location": hop.headers.get("Location"),
        })
    return {
        "requested_url": requested_url,
        "final_url": getattr(resp, "url", None),
        "status_code": getattr(resp, "status_code", None),
        "content_type": resp.headers.get("Content-Type"),
        "redirects": redirects,
    }


def _meta_entry(field, prop_name, meta_selector, content, accepted, reason):
    preview = _clean_meta_content(content)[:200]
    return {
        "field": field,
        "property": prop_name,
        "selector": meta_selector,
        "content": preview,
        "accepted": bool(accepted),
        "reason": reason,
    }


def _collect_meta_tags(soup, limit=80):
    tags = []
    for tag in (soup.find_all("meta") or [])[:limit]:
        entry = {}
        for attr in ("property", "name", "content", "charset", "http-equiv"):
            value = tag.get(attr)
            if value is not None:
                entry[attr] = str(value)
        if entry:
            tags.append(entry)
    return tags


def scrape_product_page(url, selectors, timeout=15, max_retries=2, retry_delay=5.0, user_agent=None, session=None):
    resp, duration_ms, error = _get_with_retry(url, timeout=timeout, max_retries=max_retries,
                                               retry_delay=retry_delay, user_agent=user_agent, session=session)
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


def test_scrape_url(url, selectors, timeout=15, user_agent=None, session=None):
    result = scrape_product_page(
        url,
        selectors,
        timeout=timeout,
        user_agent=user_agent,
        session=session,
    )
    if session and "error" not in result:
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            result["debug"] = _response_debug(resp, url)
        except Exception as exc:
            result["debug"] = {"requested_url": url, "error": str(exc)}
    return result


# ── Auto-descoperire selectori ─────────────────────────────────────────────

# Mapari directe la meta properties — prioritate mare in auto-discovery
_METADATA_PROPERTIES = {
    "title": [
        ("og:title", "meta[property='og:title']"),
        ("twitter:title", "meta[name='twitter:title']"),
        ("title", "meta[name='title']"),
        ("product:title", "meta[property='product:title']"),
    ],
    "pret": [
        ("product:price:amount", "meta[property='product:price:amount']"),
        ("product:price:currency", "meta[property='product:price:currency']"),
    ],
    "sku": [
        ("product:retailer_item_id", "meta[property='product:retailer_item_id']"),
        ("product:item_id", "meta[property='product:item_id']"),
        ("sku", "meta[name='sku']"),
    ],
    "brand": [
        ("product:brand", "meta[property='product:brand']"),
        ("brand", "meta[name='brand']"),
    ],
    "descriere": [
        ("og:description", "meta[property='og:description']"),
        ("description", "meta[name='description']"),
        ("twitter:description", "meta[name='twitter:description']"),
        ("product:description", "meta[property='product:description']"),
    ],
    "categorie": [
        ("product:category", "meta[property='product:category']"),
        ("category", "meta[name='category']"),
    ],
}

_CSS_HINTS = {
    "title": [
        "h1[itemprop='name']", "[itemprop='name']",
        "h1.product-title", "h1.product_title", "h1.entry-title",
        "h1.product-name", "h1",
    ],
    "pret": [
        # Magento / OpenMage — pretul numeric e in atribut, nu in text
        "span[data-price-amount][data-price-type='finalPrice']",
        ".product-info-price [data-price-amount]",
        "[data-price-amount]",
        # Schema.org / generic
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


def auto_discover_selectors(url, timeout=15, user_agent=None, session=None):
    """
    Nivel 1 — Metadate (OpenGraph, product:* properties) → PRIORITARE
    Nivel 2 — Structurate (JSON-LD / microdata) → fallback
    Nivel 3 — CSS hints + price-parser → fallback

    Returneaza dict:
    {
      field: {
        "source": "metadata" | "structured" | "css" | "not_found",
        "value": "...",          # preview valoare gasita
        "selector": "...",       # cel mai bun selector CSS
        "candidates": [{selector, preview, score, source}, ...]
      }
    }
    """
    from price_parser import Price

    try:
        http_session = session or make_session(user_agent=user_agent, base_url=url, block_resources=True)
        resp, _, error = _get_with_retry(
            url,
            timeout=timeout,
            max_retries=1,
            retry_delay=1.0,
            user_agent=user_agent,
            session=http_session,
        )
        if error or resp is None:
            return {"error": error or "No response", "debug": _response_debug(resp, url)}
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        return {"error": str(exc), "debug": _response_debug(None, url)}

    structured = _extract_structured(html, url)
    results = {}
    metadata_debug = {}
    response_debug = _response_debug(resp, url)
    response_debug["meta_tags"] = _collect_meta_tags(soup)
    response_debug["document_title"] = _clean_meta_content(soup.title.get_text(" ", strip=True)) if soup.title else None

    for field, hints in _CSS_HINTS.items():
        struct_val = structured.get(field)
        candidates = []
        seen = set()
        metadata_debug[field] = []

        # ── NIVEL 1: Metadate (OpenGraph, product:* properties) ────────────
        if field in _METADATA_PROPERTIES:
            for prop_name, meta_selector in _METADATA_PROPERTIES[field]:
                try:
                    meta_el = soup.select_one(meta_selector)
                    if not meta_el:
                        continue
                    content = _clean_meta_content(meta_el.get("content", "") or meta_el.get("value", ""))
                    debug_valid = True
                    debug_reason = "ok"
                    if not content:
                        debug_valid = False
                        debug_reason = "empty content"
                    elif field == "title" and len(content) > 300:
                        debug_valid = False
                        debug_reason = "title too long"
                    elif field == "descriere" and len(content) < 10:
                        debug_valid = False
                        debug_reason = "description too short"
                    elif field == "pret":
                        p = Price.fromstring(content)
                        if not p.amount:
                            debug_valid = False
                            debug_reason = "price not parseable"
                    metadata_debug[field].append(_meta_entry(field, prop_name, meta_selector, content, debug_valid, debug_reason))
                    if content:
                            # Validare per camp
                            valid = True
                            if field == "title" and len(content) > 300:
                                valid = False
                            if field == "descriere" and len(content) < 10:
                                valid = False
                            if field == "pret":
                                p = Price.fromstring(content)
                                if not p.amount:
                                    valid = False

                            if valid and meta_selector not in seen:
                                seen.add(meta_selector)
                                candidates.append({
                                    "selector": meta_selector,
                                    "preview": content[:150],
                                    "score": 100,  # Maxim — metadate sunt cele mai fiabile
                                    "source": "metadata",
                                })
                except Exception:
                    pass

        # ── NIVEL 2: Date structurate (JSON-LD, microdata) ──────────────────
        if struct_val and field not in seen:
            candidates.append({
                "selector": None,  # No CSS selector for structured data
                "preview": struct_val[:150],
                "score": 95,
                "source": "structured",
            })

        # ── NIVEL 3: CSS hints + price-parser ───────────────────────────────
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
                    # Prefer data-price-amount (Magento): HTML afisat poate fi
                    # fragmentat cu <sup> si get_text() da valori gresite.
                    dpa = el.get("data-price-amount")
                    if dpa:
                        p_dpa = Price.fromstring(dpa)
                        if p_dpa.amount:
                            text = dpa
                    if text != dpa:  # text vine din get_text() — valideaza
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

                score = max(10, 85 - hints.index(hint) * 10)
                if struct_val and struct_val[:50] in text:
                    score = 90  # Confirmat de date structurate

                candidates.append({
                    "selector": sel,
                    "preview": text[:150],
                    "score": score,
                    "source": "css",
                })

        candidates.sort(key=lambda x: -x["score"])

        # Determina sursa pentru rezultat final
        source = "not_found"
        if candidates:
            source = candidates[0].get("source", "css")

        results[field] = {
            "source": source,
            "value": candidates[0]["preview"] if candidates else None,
            "selector": candidates[0]["selector"] if candidates else None,
            "candidates": candidates[:5],
            "metadata_debug": metadata_debug.get(field, []),
        }

    results["debug"] = response_debug
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
