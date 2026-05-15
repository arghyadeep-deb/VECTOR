"""CLI shim for _chat_banner."""
try:
    from vectorcode.src.vector_cli._chat_banner import *
except ImportError:
    pass

def render_startup_banner(): pass
