import csv
import json
from pathlib import Path
from app.utils.logging_helpers import audit
from app.utils.helpers import safe_filename


# Coloanele acceptate în baza de date
AVAILABLE_FIELDS = {
    "sku": "SKU / Cod produs",
    "title": "Titlu produs",
    "pret": "Preț",
    "brand": "Brand / Producător",
    "descriere": "Descriere",
}

# Sugestii de mapare automată pe baza numelor coloanelor
AUTO_MAPPING_KEYWORDS = {
    "sku": ["sku", "cod", "product_id", "product_code", "article", "article_number"],
    "title": ["title", "name", "product_name", "product", "descriere_scurta", "denumire"],
    "pret": ["pret", "price", "cost", "preț", "cost_price", "unit_price", "precio"],
    "brand": ["brand", "marca", "manufacturer", "producer", "fabrica", "supplier"],
    "descriere": ["descriere", "description", "details", "detail", "descrierea"],
}


def parse_csv_preview(file_path, max_rows=5):
    """
    Parseaza fisierul CSV si returneaza previzualizare cu coloane si sample data.
    """
    preview_data = {
        "columns": [],
        "sample_rows": [],
        "total_rows": 0,
    }

    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise ValueError("Fisierul CSV nu contine coloane valide")

            preview_data["columns"] = [name.strip() for name in reader.fieldnames]
            
            # Citeste sample rows
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                preview_data["sample_rows"].append(
                    {col: row.get(col, "") for col in preview_data["columns"]}
                )
                preview_data["total_rows"] += 1
            
            # Numara total de randuri
            csv_file.seek(0)
            preview_data["total_rows"] = sum(1 for _ in csv.reader(csv_file)) - 1  # -1 pentru header
            
    except Exception as e:
        raise ValueError(f"Eroare la citirea CSV: {str(e)}")

    return preview_data


def suggest_mapping(csv_columns):
    """
    Sugereaza mapare automata a coloanelor CSV la campurile bazei de date.
    """
    suggested_mapping = {}
    
    csv_columns_lower = [col.lower().strip() for col in csv_columns]
    
    for field, keywords in AUTO_MAPPING_KEYWORDS.items():
        for csv_col_lower, csv_col_orig in zip(csv_columns_lower, csv_columns):
            if csv_col_lower in keywords or any(kw in csv_col_lower for kw in keywords):
                suggested_mapping[csv_col_orig] = field
                break
    
    return suggested_mapping


def validate_mapping(mapping, csv_columns):
    """
    Valideaza mappingul introdus de utilizator.
    
    Args:
        mapping: dict cu maparea {csv_column: database_field}
        csv_columns: list cu coloanele din CSV
        
    Returns:
        tuple: (is_valid: bool, errors: list)
    """
    errors = []
    
    # Verifica daca toate coloanele mapate exista in CSV
    for csv_col in mapping.keys():
        if csv_col not in csv_columns:
            errors.append(f"Coloana '{csv_col}' nu exista in fisier")
    
    # Verifica daca toate campurile mapate sunt valide
    for db_field in mapping.values():
        if db_field and db_field not in AVAILABLE_FIELDS:
            errors.append(f"Campul '{db_field}' nu este valid")
    
    # Verifica daca sunt mapate campurile necesare
    required_fields = {"sku", "title", "pret", "brand", "descriere"}
    mapped_fields = set(v for v in mapping.values() if v)
    missing_fields = required_fields - mapped_fields
    if missing_fields:
        missing_str = ", ".join(sorted(missing_fields))
        errors.append(f"Campuri obligatorii nemapate: {missing_str}")
    
    return len(errors) == 0, errors


def save_mapping_session(file_path, mapping, session_filename=None):
    """
    Salveaza sesiunea de mapare intr-un fisier JSON pentru folosire ulterioara.
    """
    session_data = {
        "file_path": str(file_path),
        "mapping": mapping,
    }
    
    if not session_filename:
        session_filename = Path(file_path).stem + "_mapping.json"
    
    session_path = Path(file_path).parent / session_filename
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    
    return str(session_path)


def load_mapping_session(session_path):
    """
    Incarca sesiunea de mapare din fisier JSON.
    """
    with open(session_path, "r", encoding="utf-8") as f:
        session_data = json.load(f)
    
    return session_data.get("mapping", {})
