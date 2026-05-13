#!/usr/bin/env python
"""
Script de migrare pentru adăugarea coloanei imported_at în competitor_products.
"""

import sys
from pathlib import Path

from app import create_app
from app.extensions import db


def add_imported_at_column():
    """
    Adaugă coloana imported_at la tabelul competitor_products dacă nu există.
    """
    from sqlalchemy import text
    
    print("Verificare structură database...")
    
    inspector = db.inspect(db.engine)
    columns = inspector.get_columns('competitor_products')
    column_names = {col['name'] for col in columns}
    
    if 'imported_at' in column_names:
        print("✓ Coloana 'imported_at' există deja. Nimic de făcut.")
        return True
    
    print("Adăugare coloană 'imported_at'...")
    
    try:
        dialect = db.engine.dialect.name
        
        if dialect == 'sqlite':
            db.session.execute(text('ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP'))
            db.session.commit()
            print("✓ Coloana adăugată în SQLite")
        
        elif dialect == 'mysql':
            db.session.execute(text(
                'ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP NULL AFTER updated_at'
            ))
            db.session.execute(text(
                'CREATE INDEX idx_imported_at ON competitor_products(imported_at)'
            ))
            db.session.commit()
            print("✓ Coloana adăugată în MySQL")
        
        elif dialect == 'postgresql':
            db.session.execute(text(
                'ALTER TABLE competitor_products ADD COLUMN imported_at TIMESTAMP'
            ))
            db.session.execute(text(
                'CREATE INDEX idx_imported_at ON competitor_products(imported_at)'
            ))
            db.session.commit()
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
