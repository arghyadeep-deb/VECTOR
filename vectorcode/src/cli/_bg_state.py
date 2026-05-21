"""CLI shim for _bg_state."""
try:
    from vectorcode.src.vector_cli._bg_state import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

def get_status(): return {"status": "idle"}

class BgStatus:
    idle = "idle"
    running = "running"
