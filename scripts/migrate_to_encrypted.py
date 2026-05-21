#!/usr/bin/env python3
"""
scripts/migrate_to_encrypted.py — Phase 1D: Migrate plain SQLite → SQLCipher.

Usage:
    VECTOR_DB_KEY=your_key python scripts/migrate_to_encrypted.py

Creates vector_memory_encrypted.db alongside the original.
Rename manually after verifying: mv vector_memory.db vector_memory_plain.db && mv vector_memory_encrypted.db vector_memory.db
"""
import os, sys, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_KEY = os.environ.get("VECTOR_DB_KEY", "")
if not DB_KEY:
    print("ERROR: Set VECTOR_DB_KEY env var before running this script.")
    sys.exit(1)

try:
    import sqlcipher3 as sqlcipher
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        print("ERROR: Install sqlcipher3-binary first: pip install sqlcipher3-binary")
        sys.exit(1)

import sqlite3

src = Path("vector_memory.db")
dst = Path("vector_memory_encrypted.db")

if not src.exists():
    print(f"ERROR: {src} not found. Run from the codebase root.")
    sys.exit(1)

print(f"Migrating {src} → {dst} ...")

# Read all data from plain DB
plain = sqlite3.connect(str(src))
plain.row_factory = sqlite3.Row

# Create encrypted DB
enc = sqlcipher.connect(str(dst))
enc.execute("PRAGMA key=?", (DB_KEY,))
enc.execute("PRAGMA cipher_compatibility = 4")

# Copy schema + data table by table
tables = [r[0] for r in plain.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for table in tables:
    # Get CREATE statement
    ddl = plain.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if ddl and ddl[0]:
        enc.execute(ddl[0])
    rows = plain.execute(f"SELECT * FROM {table}").fetchall()
    if rows:
        cols = len(rows[0])
        placeholders = ",".join("?" * cols)
        enc.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", [tuple(r) for r in rows])
    print(f"  {table}: {len(rows)} rows")

enc.commit()
plain.close()
enc.close()

print(f"\nDone. Encrypted DB: {dst}")
print("To activate:")
print(f"  mv vector_memory.db vector_memory_plain.db")
print(f"  mv vector_memory_encrypted.db vector_memory.db")
print(f"  # Then set VECTOR_DB_KEY={DB_KEY} in your .env")
