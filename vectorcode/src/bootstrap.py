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
    """Add repo root and vectorcode/src to sys.path if not already present.

    Insertion order matters: vectorcode/src has its own internal core/ package
    (config.py, credentials.py, events.py, registry.py, types.py — a shim over
    vc_core, see vectorcode/src/core/__init__.py) that collides by name with
    VECTOR's real top-level core/ package. Whichever directory sys.path
    resolves first wins any bare `import core` / `from core.X import Y` for
    the rest of the process (sys.modules caches the parent package's __path__
    on first touch). Inserting vectorcode/src LAST keeps it closer to the
    front but still behind repo root, so the real core/ package always wins.
    """
    repo_root = str(_REPO_ROOT)
    vectorcode_src = str(_VECTORCODE_SRC)

    # Reposition both entries every time; otherwise an already-present repo
    # root can be left behind a newly inserted vectorcode/src entry.
    sys.path[:] = [p for p in sys.path if p not in (repo_root, vectorcode_src)]
    sys.path.insert(0, vectorcode_src)
    sys.path.insert(0, repo_root)


# Run on import (side-effect)
ensure_paths()
