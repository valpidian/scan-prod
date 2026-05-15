import csv
from pathlib import Path
from datetime import datetime

from flask import current_app
from app.extensions import db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.models.price_history import PriceHistory
from app.utils.logging_helpers import audit
from app.services.notification_service import create_notification
from app.utils.helpers import normalize_text, safe_filename
from app.utils.normalizers import normalize_price


EXPECTED_COLUMNS = {"sku", "title", "pret"}
OPTIONAL_COLUMNS = {"brand", "descriere", "categorie", "url"}


def import_csv(file_storage, competitor_code, upload_folder, mapping=None, default_categorie=None):
    competitor_code = str(competitor_code or "").strip().upper()
    competitor = Competitor.query.filter_by(internal_code=competitor_code).first()
    if competitor is None:
        raise ValueError("Codul intern al competitorului nu exista. Adauga URL-ul din sectiunea Competitori.")

    target_path = Path(upload_folder) / safe_filename(file_storage.filename)
    file_storage.save(target_path)

    inserted = 0
    updated = 0
    import_timestamp = datetime.utcnow()

    with target_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames:
            if not mapping:
                available = {name.strip().lower() for name in reader.fieldnames}
                if not EXPECTED_COLUMNS.issubset(available):
                    missing = ", ".join(sorted(EXPECTED_COLUMNS - available))
                    raise ValueError(f"Lipsesc coloane necesare: {missing}")
                mapping = {col: col for col in EXPECTED_COLUMNS}

            reversed_mapping = {v: k for k, v in mapping.items()}

        for row in reader:
            try:
                sku_col       = reversed_mapping.get("sku", "sku")
                title_col     = reversed_mapping.get("title", "title")
                pret_col      = reversed_mapping.get("pret", "pret")
                brand_col     = reversed_mapping.get("brand", "brand")
                descriere_col = reversed_mapping.get("descriere", "descriere")
                categorie_col = reversed_mapping.get("categorie")
                url_col       = reversed_mapping.get("url")

                sku       = row.get(sku_col, "").strip()
                title     = row.get(title_col, "").strip()
                pret      = row.get(pret_col, "").strip()
                brand     = row.get(brand_col, "").strip()
                descriere = row.get(descriere_col, "").strip()
                categorie = (
                    row.get(categorie_col, "").strip() if categorie_col
                    else default_categorie or ""
                )
                url = row.get(url_col, "").strip() if url_col else ""

                if not sku or not title:
                    continue

                sku_norm   = normalize_text(sku)
                title_norm = normalize_text(title)
                pret_val   = normalize_price(pret) if pret else None

                existing = CompetitorProduct.query.filter_by(
                    cod_competitor=competitor_code,
                    sku=sku_norm,
                ).first()

                if existing:
                    if pret_val is not None and existing.pret != pret_val:
                        db.session.add(PriceHistory(
                            product_id=existing.id,
                            pret=pret_val,
                            sursa="import",
                        ))
                        if existing.pret_alerta and pret_val <= existing.pret_alerta:
                            create_notification(
                                "Alerta pret",
                                f"#{existing.id} {existing.title[:50]} → {pret_val:.2f} lei"
                                f" (prag: {existing.pret_alerta:.2f} lei)",
                                "warning",
                            )
                    existing.title        = title_norm
                    existing.pret         = pret_val
                    if brand:     existing.brand     = normalize_text(brand)
                    if descriere: existing.descriere = normalize_text(descriere)
                    if categorie: existing.categorie = normalize_text(categorie)
                    if url:       existing.url       = url
                    existing.imported_at = import_timestamp
                    updated += 1
                else:
                    product = CompetitorProduct(
                        cod_competitor=competitor_code,
                        sku=sku_norm,
                        title=title_norm,
                        pret=pret_val,
                        brand=normalize_text(brand) if brand else None,
                        descriere=normalize_text(descriere) if descriere else None,
                        categorie=normalize_text(categorie) if categorie else None,
                        url=url or None,
                        asociere="",
                        imported_at=import_timestamp,
                    )
                    db.session.add(product)
                    inserted += 1

            except Exception as e:
                current_app.logger.warning(f"Eroare la import randul: {row}, Eroare: {str(e)}")
                continue

    db.session.commit()
    total = inserted + updated
    audit(
        "CSV import finalizat | code=%s | host=%s | inserate=%s | actualizate=%s | file=%s",
        competitor.internal_code,
        competitor.source_host,
        inserted,
        updated,
        file_storage.filename,
    )
    return total, target_path
