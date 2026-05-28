"""
VectorCode — VECTOR's local coding agent.
Use `from vectorcode.src import X` for all imports.
"""
import sys
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

_vc_src = str(Path(__file__).resolve().parent / "src")
if _vc_src not in sys.path:
    sys.path.insert(0, _vc_src)
