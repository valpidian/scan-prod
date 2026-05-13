def normalize_price(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "")
    text = text.replace(",", ".")
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def normalize_competitor_code(value):
    return str(value or "").strip().upper()

