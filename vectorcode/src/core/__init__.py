"""Core shim package."""
from vectorcode.src.vc_core import *
try:
    from vectorcode.src.core import config
except ImportError:
    pass
