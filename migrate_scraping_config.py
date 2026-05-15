import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "scan_pret.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(scraping_configs)")
existing = {r[1] for r in cur.fetchall()}

new_cols = [
    ("randomize_delay", "BOOLEAN NOT NULL DEFAULT 1"),
    ("timeout",         "INTEGER NOT NULL DEFAULT 15"),
    ("max_retries",     "INTEGER NOT NULL DEFAULT 2"),
    ("retry_delay",     "FLOAT NOT NULL DEFAULT 5.0"),
    ("user_agent",      "VARCHAR(512)"),
    ("respect_robots",  "BOOLEAN NOT NULL DEFAULT 0"),
]

for col, typedef in new_cols:
    if col not in existing:
        cur.execute(f"ALTER TABLE scraping_configs ADD COLUMN {col} {typedef}")
        print(f"Added: {col}")
    else:
        print(f"Skip (exists): {col}")

conn.commit()
conn.close()
print("Migration done.")
