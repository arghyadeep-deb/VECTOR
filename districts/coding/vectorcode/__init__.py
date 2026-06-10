"""
Deprecated. Use `from vectorcode.src import X` instead.
"""
import sys
import warnings
from pathlib import Path

# Cache installed SDK packages BEFORE vectorcode/src goes on sys.path.
# vectorcode/src/mcp/ shadows the official MCP SDK package.
try:
    import mcp  # noqa: F401
except ImportError:
    pass
try:
    import fastmcp  # noqa: F401
except ImportError:
    pass

_vc_src = str(Path(__file__).resolve().parent.parent.parent.parent / "vectorcode" / "src")
if _vc_src not in sys.path:
    sys.path.insert(0, _vc_src)

__path__ = [_vc_src]

warnings.warn(
    "districts.coding.vectorcode is deprecated. Use vectorcode.src instead.",
    DeprecationWarning, stacklevel=2,
)
