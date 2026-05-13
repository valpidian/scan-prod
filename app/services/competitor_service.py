from __future__ import annotations

import re
from urllib.parse import urlparse

from app.extensions import db
from app.models.competitor import Competitor
from app.utils.helpers import normalize_text
from app.utils.logging_helpers import audit


def normalize_competitor_url(source_url: str) -> tuple[str, str]:
    text = normalize_text(source_url)
    if not text:
        raise ValueError("URL-ul competitorului este obligatoriu.")

    if "://" not in text:
        text = f"https://{text}"

    parsed = urlparse(text)
    if not parsed.netloc:
        raise ValueError("URL-ul competitorului nu este valid.")

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    path = (parsed.path or "").rstrip("/")
    normalized_url = f"{parsed.scheme.lower()}://{host}"
    if path:
        normalized_url += path

    return normalized_url, host


def generate_internal_code() -> str:
    existing_codes = db.session.query(Competitor.internal_code).all()
    max_number = 0
    for (code,) in existing_codes:
        match = re.search(r"(\d+)$", code or "")
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"CMP{max_number + 1:03d}"


def create_or_get_competitor(source_url: str):
    normalized_url, host = normalize_competitor_url(source_url)
    existing = Competitor.query.filter_by(source_host=host).first()
    if existing:
        return existing, False

    competitor = Competitor(
        internal_code=generate_internal_code(),
        source_url=normalized_url,
        source_host=host,
        display_name=host,
        is_active=True,
    )
    db.session.add(competitor)
    db.session.commit()

    audit(
        "Competitor adaugat | code=%s | host=%s | url=%s",
        competitor.internal_code,
        competitor.source_host,
        competitor.source_url,
    )
    return competitor, True


def get_competitor_by_code(internal_code: str):
    code = normalize_text(internal_code).upper()
    if not code:
        return None
    return Competitor.query.filter_by(internal_code=code).first()
