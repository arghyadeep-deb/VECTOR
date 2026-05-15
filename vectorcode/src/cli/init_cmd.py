"""CLI shim for init_cmd."""
try:
    from vectorcode.src.vector_cli.init_cmd import *
except ImportError:
    pass

def init(**kw) -> None:
    """Initialize VECTOR configuration."""
    pass
