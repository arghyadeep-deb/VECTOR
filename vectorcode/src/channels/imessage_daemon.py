"""iMessage daemon channel shim."""
try:
    from vectorcode.src.comms.imessage_daemon import *
except ImportError:
    pass
def is_running() -> bool:
    return False

