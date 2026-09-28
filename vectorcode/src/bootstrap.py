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

# Windows console safety (mirrors core/__init__.py): force stdout/stderr to
# UTF-8 so the emoji status lines at the bottom of vectorcode modules don't
# raise UnicodeEncodeError on a cp1252 console. Runs on import, so it covers
# both `import vectorcode.src.bootstrap` and `from ... import ensure_paths`.
# Idempotent and a no-op when already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        if (
            _stream is not None
            and hasattr(_stream, "reconfigure")
            and (getattr(_stream, "encoding", "") or "").lower() not in ("utf-8", "utf8")
        ):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VECTORCODE_SRC = Path(__file__).resolve().parent


class _PreferInstalledMcp:
    """Resolve the top-level name ``mcp`` from the INSTALLED package, never vectorcode/src/mcp/.

    vectorcode/src is put on sys.path so its many bare imports work, and its own ``mcp/`` folder then hid
    the installed MCP SDK: after ensure_paths(), ``from mcp.server.fastmcp import FastMCP`` failed for
    every other consumer (VECTOR's MCP server, coding_assistant, scraper, vector_mlops, backtest) unless
    the SDK had happened to be imported first. This finder only intercepts ``mcp`` itself; submodules
    resolve through the parent package's own __path__, and every other bare import (tools, recipes, ...)
    keeps resolving to vectorcode/src as before. If no installed ``mcp`` exists it steps aside.
    """

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if fullname != "mcp" or path is not None:
            return None
        import importlib.machinery

        here = str(_VECTORCODE_SRC)
        others = [p for p in sys.path if p and Path(p).resolve() != _VECTORCODE_SRC and p != here]
        spec = importlib.machinery.PathFinder.find_spec("mcp", others)
        if spec is not None and spec.origin and Path(spec.origin).resolve().is_relative_to(_VECTORCODE_SRC):
            return None
        return spec


def _install_import_guards() -> None:
    if not any(f is _PreferInstalledMcp for f in sys.meta_path):
        sys.meta_path.insert(0, _PreferInstalledMcp)


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
    _install_import_guards()


# Run on import (side-effect)
ensure_paths()
