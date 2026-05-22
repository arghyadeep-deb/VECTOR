"""
VectorCode — VECTOR's local coding agent.
Use `from vectorcode.src import X` for all imports.
"""
import sys
from pathlib import Path

_vc_src = str(Path(__file__).resolve().parent / "src")
if _vc_src not in sys.path:
    sys.path.insert(0, _vc_src)
