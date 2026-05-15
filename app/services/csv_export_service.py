import csv
from pathlib import Path

from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.utils.logging_helpers import audit


def export_competitor_products(competitor_code, export_folder):
    competitor_code = str(competitor_code or "").strip().upper()
    competitor = Competitor.query.filter_by(internal_code=competitor_code).first()
    if competitor is None:
        raise ValueError("Codul intern al competitorului nu exista.")

    rows = CompetitorProduct.query.filter_by(cod_competitor=competitor.internal_code).all()
    export_path = Path(export_folder) / f"{competitor.internal_code.lower()}_export.csv"

    with export_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["id", "cod_competitor", "sku", "title", "pret", "pret_preluat", "pret_preluat_sursa", "brand", "descriere", "url", "asociere", "imported_at"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())

    audit(
        "CSV export generat | code=%s | host=%s | rows=%s | path=%s",
        competitor.internal_code,
        competitor.source_host,
        len(rows),
        export_path,
    )
    return export_path, len(rows)
