"""pytest conftest — ensure VectorCode package paths are on sys.path."""
import sys
from pathlib import Path

# Add the directories where Python files live so both `from vectorcode.X` and
# `from X` work consistently in tests.
_TESTS_DIR = Path(__file__).parent
_VC_PYTHON = _TESTS_DIR.parent  # vectorcode/python/
_VC_PACKAGE = _VC_PYTHON / "vectorcode"  # vectorcode/python/vectorcode/

for p in (_VC_PYTHON, _VC_PACKAGE):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
