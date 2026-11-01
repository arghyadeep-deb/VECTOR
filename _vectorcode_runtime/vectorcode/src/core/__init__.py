"""
Gap 11: This src/core/ directory is a shim that re-exports from src/vc_core/.
Prefer importing from vectorcode.src.vc_core directly.
"""
from loguru import logger
from vectorcode.src.vc_core import *  # noqa: F401, F403
try:
    from vectorcode.src.core import config  # noqa: F401
except ImportError as e:
    logger.debug("[VECTOR][core] config shim import failed: {}", e)
