"""
conftest.py — ensure project root is on sys.path for all VectorCode tests.
Tests in vc7 need `core.mcp_server` which lives in the project root.
"""
import sys
from pathlib import Path

# project root = V.E.C.T.O.R. Codebase/
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)
# vectorcode package = V.E.C.T.O.R. Codebase/vectorcode/python/vectorcode/
_VC_PKG = str(Path(__file__).parent.parent / "vectorcode")

for _p in (_PROJECT_ROOT, _VC_PKG):
    if _p not in sys.path:
        sys.path.insert(0, _p)
