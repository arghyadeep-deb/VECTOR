"""Shared safety helpers for the MCP expansion modules (attacker-influenceable inputs)."""
from __future__ import annotations

import re
from pathlib import Path

_SECRET_NAME = re.compile(r"key|secret|token|passw|credential|dsn|cert|private", re.I)

# Never readable / writable through MCP file tools (secrets).
_SECRET_FILE_NAMES = {"google_credentials.json", "credentials.json", "token.json", "id_rsa", "id_ed25519"}
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm")
# Additionally never writable / deletable (governance + config code).
_PROTECTED_WRITE = ("core/config.py", "core/loop/permission_gateway.py", "claude.md", ".claude", ".git", ".github")


def is_sensitive_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(str(name)))


def redact(obj):
    """Deep-copy ``obj`` with the value of every secret-looking key replaced."""
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if is_sensitive_name(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def resolve_in_root(root: Path, raw: str) -> Path | None:
    """Resolve ``raw`` under ``root``; None if it escapes (CWE-22, symlink-safe)."""
    base = root.resolve()
    try:
        p = (base / raw).resolve()
    except (OSError, ValueError):
        return None
    return p if p == base or p.is_relative_to(base) else None


def is_secret_path(root: Path, p: Path) -> bool:
    try:
        rel = (root / p).resolve().relative_to(root.resolve())
    except ValueError:
        return True
    name = rel.name.lower()
    return (
        name == ".env" or name.startswith(".env.") or name in _SECRET_FILE_NAMES
        or name.endswith(_SECRET_SUFFIXES)
    )


def is_protected_write_path(root: Path, p: Path) -> bool:
    if is_secret_path(root, p):
        return True
    rel = (root / p).resolve().relative_to(root.resolve()).as_posix().lower()
    return any(rel == q or rel.startswith(q + "/") for q in _PROTECTED_WRITE)
