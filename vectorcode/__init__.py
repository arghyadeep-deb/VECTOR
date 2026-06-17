"""
VectorCode — VECTOR's local coding agent.
Use `from vectorcode.src import X` for all imports.
"""
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

from vectorcode.src.bootstrap import ensure_paths

ensure_paths()
