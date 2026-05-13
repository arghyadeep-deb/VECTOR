"""
conftest.py — ensure project root is on sys.path for all VectorCode tests.
Tests in vc7 need `core.mcp_server` which lives in the project root.
"""
import sys
from pathlib import Path

# project root = V.E.C.T.O.R. Codebase/  (conftest is at python/tests/conftest.py → 4 up)
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent)
# vectorcode package parent = V.E.C.T.O.R. Codebase/vectorcode/python/
# sys.path needs the PARENT of vectorcode/, not vectorcode/ itself
_VC_PARENT = str(Path(__file__).parent.parent)

for _p in (_PROJECT_ROOT, _VC_PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
