"""Shim: re-exports from core.mining.apple_mps_pearl."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent.parent))
try:
    from core.mining.apple_mps_pearl import *
except ImportError:
    pass
