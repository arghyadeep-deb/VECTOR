"""
Deprecated. Use `from vectorcode.src import X` instead.
"""
import warnings
from pathlib import Path

# Cache installed SDK packages BEFORE vectorcode/src goes on sys.path.
# vectorcode/src/mcp/ shadows the official MCP SDK package.
try:
    import mcp  # noqa: F401
except ImportError:
    __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
try:
    import fastmcp  # noqa: F401
except ImportError:
    __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
from vectorcode.src.bootstrap import ensure_paths

ensure_paths()
_vc_src = str(Path(__file__).resolve().parent.parent.parent.parent / "vectorcode" / "src")
__path__ = [_vc_src]

warnings.warn(
    "districts.coding.vectorcode is deprecated. Use vectorcode.src instead.",
    DeprecationWarning, stacklevel=2,
)
