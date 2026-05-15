"""CLI shim for _tool_names."""
try:
    from vectorcode.src.vector_cli._tool_names import *
except ImportError:
    pass

def resolve_tool_names(names): return names
