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

_repo_root = str(Path(__file__).resolve().parent.parent)
_vc_src = str(Path(__file__).resolve().parent / "src")
for _path in (_repo_root, _vc_src):
    if _path not in sys.path:
        sys.path.insert(0, _path)
