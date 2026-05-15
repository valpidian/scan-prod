#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migrare optimizari v2:
  1. Creaza tabela scraping_jobs
  2. Creaza tabela product_associations
  3. Migreaza datele din competitor_products.asociere
  4. Adauga indexuri compuse
  5. Creaza tabel FTS5 pentru cautare rapida
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import sys
from sqlalchemy import text

from app import create_app
from app.extensions import db


# ── Helpers ────────────────────────────────────────────────────────────────

def _table_exists(conn, name):
    r = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return r is not None


def _index_exists(conn, name):
    r = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
        {"n": name},
    ).fetchone()
    return r is not None


def _trigger_exists(conn, name):
    r = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='trigger' AND name=:n"),
        {"n": name},
    ).fetchone()
    return r is not None


# ── Task 1: scraping_jobs ──────────────────────────────────────────────────

def create_scraping_jobs(conn):
    if _table_exists(conn, "scraping_jobs"):
        print("✓ Tabela 'scraping_jobs' exista deja.")
        return
    conn.execute(text("""
        CREATE TABLE scraping_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          VARCHAR(32)  NOT NULL UNIQUE,
            competitor_code VARCHAR(32)  NOT NULL,
            status          VARCHAR(20)  NOT NULL DEFAULT 'running',
            stop_requested  BOOLEAN      NOT NULL DEFAULT 0,
            total           INTEGER      DEFAULT 0,
            inserted        INTEGER      DEFAULT 0,
            updated         INTEGER      DEFAULT 0,
            errors          INTEGER      DEFAULT 0,
            started_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at     TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scraping_jobs_job_id ON scraping_jobs(job_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scraping_jobs_competitor_code ON scraping_jobs(competitor_code)"))
    print("✓ Tabela 'scraping_jobs' creata.")


# ── Task 2: product_associations ───────────────────────────────────────────

def create_product_associations(conn):
    if _table_exists(conn, "product_associations"):
        print("✓ Tabela 'product_associations' exista deja.")
        return
    conn.execute(text("""
        CREATE TABLE product_associations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id    INTEGER NOT NULL REFERENCES competitor_products(id) ON DELETE CASCADE,
            associated_id INTEGER NOT NULL REFERENCES competitor_products(id) ON DELETE CASCADE,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_product_association UNIQUE (product_id, associated_id)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_product_associations_product_id ON product_associations(product_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_product_associations_associated_id ON product_associations(associated_id)"))
    print("✓ Tabela 'product_associations' creata.")


# ── Task 3: Migrare date asociere ──────────────────────────────────────────

def migrate_asociere(conn):
    rows = conn.execute(
        text("SELECT id, asociere FROM competitor_products WHERE asociere IS NOT NULL AND asociere != ''")
    ).fetchall()

    if not rows:
        print("✓ Nu exista date de migrat din 'asociere'.")
        return

    migrated = 0
    skipped = 0
    errors = 0

    for row in rows:
        product_id = row[0]
        asociere_raw = row[1] or ""
        parts = [p.strip() for p in asociere_raw.split(";") if p.strip().isdigit()]
        for part in parts:
            associated_id = int(part)
            if associated_id == product_id:
                continue
            low, high = min(product_id, associated_id), max(product_id, associated_id)
            # Verifica daca perechea exista deja
            exists = conn.execute(
                text("SELECT id FROM product_associations WHERE product_id=:p AND associated_id=:a"),
                {"p": low, "a": high},
            ).fetchone()
            if exists:
                skipped += 1
                continue
            # Verifica ca ambele produse exista
            prod_exists = conn.execute(
                text("SELECT id FROM competitor_products WHERE id IN (:p, :a)"),
                {"p": low, "a": high},
            ).fetchall()
            if len(prod_exists) < 2:
                errors += 1
                continue
            try:
                conn.execute(
                    text("INSERT INTO product_associations (product_id, associated_id) VALUES (:p, :a)"),
                    {"p": low, "a": high},
                )
                migrated += 1
            except Exception as e:
                errors += 1

    print(f"✓ Migrare asociere: {migrated} adaugate, {skipped} deja existente, {errors} erori.")


# ── Task 4: Indexuri compuse ───────────────────────────────────────────────

def create_composite_indexes(conn):
    if not _index_exists(conn, "ix_cp_competitor_sku"):
        conn.execute(text(
            "CREATE INDEX ix_cp_competitor_sku ON competitor_products(cod_competitor, sku)"
        ))
        print("✓ Index 'ix_cp_competitor_sku' creat.")
    else:
        print("✓ Index 'ix_cp_competitor_sku' exista deja.")

    if not _index_exists(conn, "ix_su_code_status"):
        conn.execute(text(
            "CREATE INDEX ix_su_code_status ON scraping_urls(competitor_code, status)"
        ))
        print("✓ Index 'ix_su_code_status' creat.")
    else:
        print("✓ Index 'ix_su_code_status' exista deja.")


# ── Task 5: FTS5 ───────────────────────────────────────────────────────────

_FTS_TABLE = "competitor_products_fts"

def create_fts5(conn):
    if _table_exists(conn, _FTS_TABLE):
        print("✓ Tabela FTS5 exista deja.")
        _ensure_fts_triggers(conn)
        return

    # FTS5 content table — nu dubleaza datele, citeste din tabela originala
    conn.execute(text(f"""
        CREATE VIRTUAL TABLE {_FTS_TABLE}
        USING fts5(
            title,
            sku,
            brand,
            content='competitor_products',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """))
    print(f"✓ Tabela FTS5 '{_FTS_TABLE}' creata.")

    # Populare initiala
    conn.execute(text(f"""
        INSERT INTO {_FTS_TABLE}(rowid, title, sku, brand)
        SELECT id, COALESCE(title,''), COALESCE(sku,''), COALESCE(brand,'')
        FROM competitor_products
    """))
    print("✓ FTS5 populat cu date existente.")

    _ensure_fts_triggers(conn)


def _ensure_fts_triggers(conn):
    triggers = {
        "fts_ai_competitor_products": f"""
            CREATE TRIGGER fts_ai_competitor_products
            AFTER INSERT ON competitor_products BEGIN
                INSERT INTO {_FTS_TABLE}(rowid, title, sku, brand)
                VALUES (new.id, COALESCE(new.title,''), COALESCE(new.sku,''), COALESCE(new.brand,''));
            END
        """,
        "fts_ad_competitor_products": f"""
            CREATE TRIGGER fts_ad_competitor_products
            AFTER DELETE ON competitor_products BEGIN
                INSERT INTO {_FTS_TABLE}({_FTS_TABLE}, rowid, title, sku, brand)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.sku,''), COALESCE(old.brand,''));
            END
        """,
        "fts_au_competitor_products": f"""
            CREATE TRIGGER fts_au_competitor_products
            AFTER UPDATE ON competitor_products BEGIN
                INSERT INTO {_FTS_TABLE}({_FTS_TABLE}, rowid, title, sku, brand)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.sku,''), COALESCE(old.brand,''));
                INSERT INTO {_FTS_TABLE}(rowid, title, sku, brand)
                VALUES (new.id, COALESCE(new.title,''), COALESCE(new.sku,''), COALESCE(new.brand,''));
            END
        """,
    }
    for name, ddl in triggers.items():
        if not _trigger_exists(conn, name):
            conn.execute(text(ddl))
            print(f"✓ Trigger '{name}' creat.")
        else:
            print(f"✓ Trigger '{name}' exista deja.")


# ── Main ───────────────────────────────────────────────────────────────────

def run_all():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        try:
            print("\n── 1. scraping_jobs ─────────────────────────────────")
            create_scraping_jobs(conn)

            print("\n── 2. product_associations ──────────────────────────")
            create_product_associations(conn)

            print("\n── 3. Migrare date asociere ─────────────────────────")
            migrate_asociere(conn)

            print("\n── 4. Indexuri compuse ───────────────────────────────")
            create_composite_indexes(conn)

            print("\n── 5. FTS5 ──────────────────────────────────────────")
            create_fts5(conn)

            conn.commit()
            print("\n✓ Toate migrarile au fost aplicate cu succes.\n")
        except Exception as e:
            conn.rollback()
            print(f"\n✗ Eroare: {e}")
            sys.exit(1)
        finally:
            conn.close()


if __name__ == "__main__":
    print("=" * 55)
    print("Migrare Optimizari — scan-pret")
    print("=" * 55)
    run_all()
