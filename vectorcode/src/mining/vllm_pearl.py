"""Shim: re-exports from core.mining.vllm_pearl."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent.parent))
try:
    from core.mining.vllm_pearl import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
