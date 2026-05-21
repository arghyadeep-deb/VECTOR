"""iMessage daemon channel shim."""
try:
    from vectorcode.src.comms.imessage_daemon import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
def is_running() -> bool:
    return False

