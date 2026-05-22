"""
Deprecated. Use `from vectorcode.src import X` instead.
"""
import sys
import warnings
from pathlib import Path

_vc_src = str(Path(__file__).resolve().parent.parent.parent.parent / "vectorcode" / "src")
if _vc_src not in sys.path:
    sys.path.insert(0, _vc_src)

warnings.warn(
    "districts.coding.vectorcode is deprecated. Use vectorcode.src instead.",
    DeprecationWarning, stacklevel=2,
)
