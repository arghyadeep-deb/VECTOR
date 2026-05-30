from loguru import logger
"""CLI shim for _chat_banner."""
try:
    from vectorcode.src.vector_cli._chat_banner import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

def render_startup_banner(): pass
