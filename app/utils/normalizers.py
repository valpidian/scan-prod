import re


def normalize_price(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None

    # price_parser gestioneaza corect toate formatele internationale:
    # "40,00 lei" → 40.0, "1.234,56" → 1234.56, "4.999" → 4999.0
    try:
        from price_parser import Price
        p = Price.fromstring(text)
        if p.amount is not None:
            return round(float(p.amount), 2)
    except Exception:
        pass

    # Fallback regex pentru cazuri edge (price_parser nu a gasit nimic)
    text = re.sub(r'(?i)\s*(lei|ron|eur|usd|euro|\$|€)\s*', '', text).strip()
    text = re.sub(r'\s', '', text)
    if re.search(r'\d\.\d{3},', text):
        text = text.replace('.', '').replace(',', '.')
    elif re.search(r',\d{1,2}$', text):
        text = text.replace(',', '.')
    text = re.sub(r'[^\d.]', '', text)
    if not text:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def normalize_competitor_code(value):
    return str(value or "").strip().upper()

