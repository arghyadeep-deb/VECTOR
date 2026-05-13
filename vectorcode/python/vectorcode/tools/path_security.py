# Ported from GitHub/NousResearch_hermes-agent/repo/tools/path_security.py
"""Shared path validation helpers."""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_within_dir(path: Path, root: Path) -> Optional[str]:
    """Ensure path resolves within root. Returns error string or None."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"
    return None


def has_traversal_component(path_str: str) -> bool:
    """Return True if path_str contains .. traversal components."""
    return ".." in Path(path_str).parts
