"""pytest bootstrap for the isolated Digital Twin lab.

Run ONLY explicitly (never part of default `pytest` discovery — the main
`pytest.ini` sets `testpaths = tests`, which does not include this
directory):

    pytest "VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests" -v

Adds both the repo root (so `core.*`/`vectorcode.*` imports resolve, exactly
like the main tests/conftest.py already does) and the lab's own directory
(so sibling modules like `twin`, `scenario`, `isolation` import as bare
top-level names) to sys.path.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_LAB_DIR = _TESTS_DIR.parent
_REPO_ROOT = _LAB_DIR.parents[1]

for _p in (str(_LAB_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_isolated_temp_dirs():
    """Every `IsolatedVectorEnv()` created in this session (isolation.py)
    writes to its own `vector_twin_<run_id>_*` directory under the OS temp
    folder and does not delete it (so a failed test's on-disk state can be
    inspected). Sweep them up once at session end so a lab test run doesn't
    silently accumulate scratch SQLite files run after run. Only ever
    touches directories matching this session's own naming prefix."""
    yield
    tmp_root = Path(tempfile.gettempdir())
    for child in tmp_root.glob("vector_twin_*"):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
