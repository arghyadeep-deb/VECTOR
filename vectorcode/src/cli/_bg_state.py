"""CLI shim for _bg_state."""
try:
    from vectorcode.src.vector_cli._bg_state import *
except ImportError:
    pass

def get_status(): return {"status": "idle"}

class BgStatus:
    idle = "idle"
    running = "running"
