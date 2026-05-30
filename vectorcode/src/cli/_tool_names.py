from loguru import logger
"""CLI shim for _tool_names."""
try:
    from vectorcode.src.vector_cli._tool_names import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

def resolve_tool_names(names): return names
