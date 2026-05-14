import re

_RE_CURRENCY = re.compile(r'[^\d.,]', re.IGNORECASE)
_RE_THOUSANDS_DOT = re.compile(r'(\d)\.(?=\d{3}(?:[,.]|$))')


def normalize_price(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    # Elimina simboluri valutare si text (lei, ron, eur, usd etc.)
    text = re.sub(r'(?i)\s*(lei|ron|eur|usd|euro|\$|€)\s*', '', text).strip()
    # Elimina spatii
    text = text.replace(" ", "")
    # Detecteaza format european: 1.234,56 -> 1234.56
    if re.search(r'\d\.\d{3},', text):
        text = text.replace('.', '').replace(',', '.')
    # Detecteaza format cu virgula ca separator zecimal: 50,00
    elif re.search(r',\d{1,2}$', text):
        text = text.replace(',', '.')
    # Elimina orice alt caracter non-numeric (mai putin punct)
    text = re.sub(r'[^\d.]', '', text)
    if not text:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def normalize_competitor_code(value):
    return str(value or "").strip().upper()

