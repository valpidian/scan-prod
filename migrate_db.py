#!/usr/bin/env python
"""
Script de migrare pentru adăugarea coloanei imported_at în competitor_products.
"""

import sys
from pathlib import Path

from app import create_app
from app.extensions import db


COLUMNS_TO_ADD = [
    ("imported_at", "TIMESTAMP"),
    ("categorie",   "VARCHAR(120)"),
    ("pret_preluat", "FLOAT"),
    ("pret_preluat_sursa", "VARCHAR(50)"),
]


def add_missing_columns():
    from sqlalchemy import text

    print("Verificare structură database...")
    inspector = db.inspect(db.engine)
    columns = inspector.get_columns('competitor_products')
    existing = {col['name'] for col in columns}

    added = 0
    for col_name, col_type in COLUMNS_TO_ADD:
        if col_name in existing:
            print(f"✓ Coloana '{col_name}' există deja.")
            continue
        try:
            db.session.execute(text(f'ALTER TABLE competitor_products ADD COLUMN {col_name} {col_type}'))
            db.session.commit()
            print(f"✓ Coloana '{col_name}' adăugată.")
            added += 1
        except Exception as e:
            print(f"✗ Eroare la '{col_name}': {e}")
            return False

    print(f"✓ Migrare finalizată — {added} coloane adăugate.")
    return True


def add_imported_at_column():
    return add_missing_columns()


def check_database_health():
    """
    Verifică sănătatea database-ului.
    """
    from sqlalchemy import text
    print("\nVerificare sănătate database...")
    
    try:
        result = db.session.execute(text('SELECT 1'))
        print("✓ Conexiune la database OK")
        
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'competitor_products' in tables:
            print("✓ Tabelul 'competitor_products' există")
            # Nu numărăm produsele dacă coloana nu există
        else:
            print("✗ Tabelul 'competitor_products' nu există")
            return False
        
        if 'competitors' in tables:
            print("✓ Tabelul 'competitors' există")
        else:
            print("✗ Tabelul 'competitors' nu există")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ Eroare la verificare: {str(e)}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("Script Migrare - Adăugare Coloană imported_at")
    print("=" * 60)
    
    app = create_app()
    with app.app_context():
        if not check_database_health():
            print("\n✗ Database nu este sănătos.")
            sys.exit(1)
        
        print()
        if add_imported_at_column():
            print("\n✓ Migrare completă!")
            sys.exit(0)
        else:
            print("\n✗ Migrare eșuată!")
            sys.exit(1)
