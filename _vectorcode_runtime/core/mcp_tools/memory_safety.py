"""Safety helpers for MCP episodic memory import/export tools."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


MEMORY_EXPORT_DIRNAME = "memory_exports"
MEMORY_CLEAR_CONFIRM = "CONFIRM_CLEAR_MEMORY"


def memory_export_dir() -> Path:
    """Return the single approved directory for MCP memory import/export."""
    from core.runtime_paths import data_path

    directory = data_path(MEMORY_EXPORT_DIRNAME)
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def resolve_memory_path(path: str, *, default_name: str) -> Tuple[Optional[Path], Optional[str]]:
    """Resolve a memory import/export path inside the approved directory.

    Blank paths use ``default_name``. Bare filenames are placed inside the
    approved export directory. Absolute paths or traversal that escape that
    directory are rejected.
    """
    base = memory_export_dir()
    raw = (path or "").strip()
    candidate = (base / default_name) if not raw else Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except Exception as exc:
        return None, f"invalid path: {exc}"
    if resolved != base and base not in resolved.parents:
        return None, (
            f"path outside approved memory directory ({base}); "
            "use a filename or a path inside that directory"
        )
    return resolved, None


__all__ = [
    "MEMORY_CLEAR_CONFIRM",
    "MEMORY_EXPORT_DIRNAME",
    "memory_export_dir",
    "resolve_memory_path",
]
