"""pytest conftest — ensure VectorCode package paths are on sys.path."""
import sys
from pathlib import Path

_TESTS_DIR    = Path(__file__).parent
_VC_PYTHON    = _TESTS_DIR.parent                    # vectorcode/python/
_VC_ROOT      = _VC_PYTHON.parent                    # vectorcode/
_VC_SRC       = _VC_ROOT / "src"                     # vectorcode/src/  (restructured)
_PROJECT_ROOT = _VC_ROOT.parent                      # V.E.C.T.O.R. Codebase/

for p in (_PROJECT_ROOT, _VC_ROOT, _VC_SRC):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

# Gap 15: Legacy tests are now enabled.
# Previously: collect_ignore_glob = ["legacy_ported/*"]
# The legacy_ported/ directory has its own conftest.py with proper fixtures.
# Run with: pytest vectorcode/python/tests/
# Skip legacy only: pytest vectorcode/python/tests/ --ignore=vectorcode/python/tests/legacy_ported

