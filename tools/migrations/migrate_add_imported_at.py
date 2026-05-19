#!/usr/bin/env python
"""
Script de migrare pentru adăugarea coloanei imported_at în competitor_products.
"""

import sys
from pathlib import Path

# Adaugă directorul app în path
sys.path.insert(0, str(Path(__file__).parent))

from app.extensions import db
from app.models.competitor_product import CompetitorProduct


def add_imported_at_column():
    """
    Adaugă coloana imported_at la tabelul competitor_products dacă nu există.
    """
    print("Verificare structură database...")
    
    # Inspectează tabelul curent
    inspector = db.inspect(db.engine)
    columns = inspector.get_columns('competitor_products')
    column_names = {col['name'] for col in columns}
    
    if 'imported_at' in column_names:
        print("✓ Coloana 'imported_at' există deja. Nimic de făcut.")
        return True
    
    print("Adăugare coloană 'imported_at'...")
    
    try:
        # Obțin dialektul database
        dialect = db.engine.dialect.name
        
        if dialect == 'sqlite':
            # SQLite nu suportă ALTER TABLE cu ADD COLUMN pe coloane cu valori default în mod direct
            # Se va adăuga fără valoare default inițial
            db.engine.execute('ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP')
            print("✓ Coloana adăugată în SQLite")
        
        elif dialect == 'mysql':
            db.engine.execute(
                'ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP NULL AFTER updated_at'
            )
            db.engine.execute(
                'CREATE INDEX idx_imported_at ON competitor_products(imported_at)'
            )
            print("✓ Coloana adăugată în MySQL")
        
        elif dialect == 'postgresql':
            db.engine.execute(
                'ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP'
            )
            db.engine.execute(
                'CREATE INDEX idx_imported_at ON competitor_products(imported_at)'
            )
            print("✓ Coloana adăugată în PostgreSQL")
        
        print("✓ Migrare finalizată cu succes!")
        return True
        
    except Exception as e:
        print(f"✗ Eroare la migrare: {str(e)}")
        return False


def check_database_health():
    """
    Verifică sănătatea database-ului.
    """
    print("\nVerificare sănătate database...")
    
    try:
        # Verifică conexiunea
        result = db.session.execute('SELECT 1')
        print("✓ Conexiune la database OK")
        
        # Verifică tabelele
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'competitor_products' in tables:
            print("✓ Tabelul 'competitor_products' există")
            
            # Numără produsele
            from app.models.competitor_product import CompetitorProduct
            count = CompetitorProduct.query.count()
            print(f"  - Produse existente: {count}")
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
    
    # Verifică database-ul
    if not check_database_health():
        print("\n✗ Database nu este sănătos. Verifică configurația.")
        sys.exit(1)
    
    # Adaugă coloana
    print()
    if add_imported_at_column():
        print("\n✓ Migrare completă!")
        sys.exit(0)
    else:
        print("\n✗ Migrare eșuată!")
        sys.exit(1)
