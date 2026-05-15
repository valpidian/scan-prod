import time
import requests
from bs4 import BeautifulSoup

from app.utils.normalizers import normalize_price


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def scrape_price(url, css_selector, timeout=15):
    """Fetches url and extracts price using css_selector. Returns float or None."""
    if not url or not css_selector:
        return None
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        el = soup.select_one(css_selector)
        if el:
            return normalize_price(el.get_text(strip=True))
    except Exception:
        pass
    return None


def scrape_competitor_products(competitor_code, price_selector, delay=1.0):
    """
    Scrapes all products of a competitor that have a url.
    Yields dicts: {product_id, old_pret, new_pret, status}
    delay: seconds between requests to avoid overloading the site
    """
    from app.models.competitor_product import CompetitorProduct

    products = (
        CompetitorProduct.query
        .filter_by(cod_competitor=competitor_code)
        .filter(CompetitorProduct.url.isnot(None), CompetitorProduct.url != "")
        .all()
    )

    for product in products:
        new_pret = scrape_price(product.url, price_selector)
        yield {
            "product_id": product.id,
            "old_pret": product.pret,
            "new_pret": new_pret,
            "changed": new_pret is not None and new_pret != product.pret,
        }
        if delay > 0:
            time.sleep(delay)
