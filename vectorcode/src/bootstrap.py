"""
vectorcode/src/bootstrap.py — Single path-setup module (Gap 21).

All files that previously had inline sys.path.insert() calls should instead do:
    import vectorcode.src.bootstrap  # noqa: F401  (side-effect import)

Or, if the file is run as __main__:
    from vectorcode.src.bootstrap import ensure_paths
    ensure_paths()

This replaces the ~8 copies of:
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VECTORCODE_SRC = Path(__file__).resolve().parent


def ensure_paths() -> None:
    """Add repo root and vectorcode/src to sys.path if not already present."""
    for p in [str(_REPO_ROOT), str(_VECTORCODE_SRC)]:
        if p not in sys.path:


# Run on import (side-effect)
ensure_paths()
