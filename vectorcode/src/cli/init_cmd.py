"""CLI shim for init_cmd."""
from loguru import logger
try:
    from vectorcode.src.vector_cli.init_cmd import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

def init(**kw) -> None:
    """Initialize VECTOR configuration."""
    pass
