#!/usr/bin/env python3
"""Migrate the root plaintext SQLite database to an atomic SQLCipher copy."""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "vector_memory.db"
DEFAULT_DESTINATION = ROOT / "vector_memory_encrypted.db"


def _sql_literal(value: str) -> str:
    """Quote a SQLite string literal; PRAGMA values cannot be bound."""
    return "'" + value.replace("'", "''") + "'"


def _load_sqlcipher():
    try:
        import sqlcipher3 as sqlcipher
        return sqlcipher
    except ImportError:
        try:
            from pysqlcipher3 import dbapi2 as sqlcipher
            return sqlcipher
        except ImportError as exc:
            raise RuntimeError(
                "Install sqlcipher3-binary first: pip install sqlcipher3-binary"
            ) from exc


def migrate(source: Path, destination: Path, db_key: str, sqlcipher_module=None) -> None:
    """Create *destination* without exposing the key or leaving a partial DB."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("source and destination must differ")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sqlcipher = sqlcipher_module or _load_sqlcipher()

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    temp_path.unlink()

    plain = encrypted = None
    try:
        plain = sqlite3.connect(source)
        encrypted = sqlcipher.connect(str(temp_path))
        encrypted.execute("PRAGMA key = " + _sql_literal(db_key))
        encrypted.execute("PRAGMA cipher_compatibility = 4")
        encrypted.executescript("\n".join(plain.iterdump()))
        encrypted.commit()
        row = encrypted.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError(f"encrypted database integrity check failed: {row!r}")
        encrypted.close()
        encrypted = None
        plain.close()
        plain = None
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        if encrypted is not None:
            encrypted.close()
        if plain is not None:
            plain.close()
        temp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args(argv)
    db_key = os.environ.get("VECTOR_DB_KEY", "")
    if not db_key:
        print("ERROR: Set VECTOR_DB_KEY env var before running this script.", file=sys.stderr)
        return 1
    try:
        migrate(args.source, args.destination, db_key)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Done. Encrypted DB: {args.destination.resolve()}")
    print("Verify the encrypted copy, then replace the plaintext database manually.")
    print("Keep VECTOR_DB_KEY in the environment or OS keyring; it is never printed here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
