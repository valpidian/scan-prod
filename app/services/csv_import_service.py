import csv
from pathlib import Path
from datetime import datetime

from flask import current_app
from app.extensions import db
from app.models.competitor import Competitor
from app.models.competitor_product import CompetitorProduct
from app.utils.logging_helpers import audit
from app.utils.helpers import normalize_text, safe_filename
from app.utils.normalizers import normalize_price


EXPECTED_COLUMNS = {"sku", "title", "pret"}
OPTIONAL_COLUMNS = {"brand", "descriere", "categorie"}


def import_csv(file_storage, competitor_code, upload_folder, mapping=None, default_categorie=None):
    """
    Importa CSV cu maparea coloanelor specificata.
    
    Args:
        file_storage: FileStorage object din request
        competitor_code: Codul intern al competitorului
        upload_folder: Cale folder upload
        mapping: Dict cu maparea {csv_column: database_field}
        
    Returns:
        tuple: (imported_count, file_path)
    """
    competitor_code = str(competitor_code or "").strip().upper()
    competitor = Competitor.query.filter_by(internal_code=competitor_code).first()
    if competitor is None:
        raise ValueError("Codul intern al competitorului nu exista. Adauga URL-ul din sectiunea Competitori.")

    target_path = Path(upload_folder) / safe_filename(file_storage.filename)
    file_storage.save(target_path)

    imported = 0
    import_timestamp = datetime.utcnow()
    
    with target_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames:
            # Daca nu e specificat mapping, foloseste coloanele directe (backward compatibility)
            if not mapping:
                available = {name.strip().lower() for name in reader.fieldnames}
                if not EXPECTED_COLUMNS.issubset(available):
                    missing = ", ".join(sorted(EXPECTED_COLUMNS - available))
                    raise ValueError(f"Lipsesc coloane necesare: {missing}")
                # Creeaza mapping cu aceleasi nume coloane
                mapping = {col: col for col in EXPECTED_COLUMNS}
            
            # Inversam mappingul: transformam {csv_column: db_field} in {db_field: csv_column}
            # pentru a putea accesa usor coloanele din CSV
            reversed_mapping = {v: k for k, v in mapping.items()}

        for row in reader:
            # Extrage valorile folosind mappingul inversat
            try:
                sku_col = reversed_mapping.get("sku", "sku")
                title_col = reversed_mapping.get("title", "title")
                pret_col = reversed_mapping.get("pret", "pret")
                brand_col = reversed_mapping.get("brand", "brand")
                descriere_col = reversed_mapping.get("descriere", "descriere")
                categorie_col = reversed_mapping.get("categorie")

                sku = row.get(sku_col, "").strip()
                title = row.get(title_col, "").strip()
                pret = row.get(pret_col, "").strip()
                brand = row.get(brand_col, "").strip()
                descriere = row.get(descriere_col, "").strip()
                categorie = (
                    row.get(categorie_col, "").strip() if categorie_col
                    else default_categorie or ""
                )

                if not sku or not title:
                    continue

                product = CompetitorProduct(
                    cod_competitor=competitor_code,
                    sku=normalize_text(sku),
                    title=normalize_text(title),
                    pret=normalize_price(pret) if pret else None,
                    brand=normalize_text(brand) if brand else None,
                    descriere=normalize_text(descriere) if descriere else None,
                    categorie=normalize_text(categorie) if categorie else None,
                    asociere="",
                    imported_at=import_timestamp,
                )
                db.session.add(product)
                imported += 1
            except Exception as e:
                # Log si continua cu randul urmator
                current_app.logger.warning(f"Eroare la import randul: {row}, Eroare: {str(e)}")
                continue

    db.session.commit()
    audit(
        "CSV import finalizat | code=%s | host=%s | rows=%s | file=%s | saved=%s",
        competitor.internal_code,
        competitor.source_host,
        imported,
        file_storage.filename,
        target_path,
    )
    return imported, target_path
