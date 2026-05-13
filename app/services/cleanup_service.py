import re


# Regex pentru URL-uri (http/https/ftp)
_RE_URL = re.compile(
    r'https?://[^\s<>"\']+|ftp://[^\s<>"\']+',
    re.IGNORECASE
)

# Regex pentru taguri HTML
_RE_HTML_TAG = re.compile(r'<[^>]+>')

# Regex pentru entitati HTML (&amp; &nbsp; etc.)
_RE_HTML_ENTITY = re.compile(r'&[a-zA-Z]{2,6};|&#\d{1,5};')

# Regex pentru cai fisiere (Windows si Unix) si extensii comune
_RE_FILEPATH = re.compile(
    r'(?:[a-zA-Z]:\\|/)[^\s<>"\']*\.(?:pdf|jpg|jpeg|png|gif|webp|svg|doc|docx|xls|xlsx|zip|rar|csv|xml|json)',
    re.IGNORECASE
)

# Regex pentru siruri de spatii multiple
_RE_MULTI_SPACE = re.compile(r'\s{2,}')


def strip_html(text):
    """Elimina taguri HTML si entitati."""
    if not text:
        return text
    text = _RE_HTML_TAG.sub(' ', text)
    text = _RE_HTML_ENTITY.sub(' ', text)
    return text


def strip_urls(text):
    """Elimina URL-uri http/https/ftp."""
    if not text:
        return text
    return _RE_URL.sub('', text)


def strip_filepaths(text):
    """Elimina cai de fisiere si referinte la fisiere."""
    if not text:
        return text
    return _RE_FILEPATH.sub('', text)


def normalize_whitespace(text):
    """Normalizeaza spatiile multiple intr-unul singur."""
    if not text:
        return text
    return _RE_MULTI_SPACE.sub(' ', text).strip()


def clean_text(text):
    """Aplica toate curatarile pe un text."""
    if not text:
        return text
    text = strip_html(text)
    text = strip_urls(text)
    text = strip_filepaths(text)
    text = normalize_whitespace(text)
    return text or None


def analyze_field(value):
    """Returneaza ce probleme are un camp."""
    if not value:
        return []
    issues = []
    if _RE_HTML_TAG.search(value):
        issues.append('html')
    if _RE_URL.search(value):
        issues.append('url')
    if _RE_FILEPATH.search(value):
        issues.append('filepath')
    if _RE_HTML_ENTITY.search(value):
        issues.append('entity')
    return issues


def clean_product(product):
    """
    Curata campurile unui produs.
    Returneaza dict cu campurile modificate si tipurile de probleme gasite.
    """
    changes = {}
    issues_found = set()

    for field in ('title', 'brand', 'descriere', 'sku'):
        original = getattr(product, field, None)
        if not original:
            continue
        issues = analyze_field(original)
        if issues:
            cleaned = clean_text(original)
            if cleaned != original:
                changes[field] = {'before': original, 'after': cleaned}
                issues_found.update(issues)

    return changes, list(issues_found)
