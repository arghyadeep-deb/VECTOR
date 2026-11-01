from __future__ import annotations

import os
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Return the resolved VECTOR repository root."""
    return _PROJECT_ROOT


def get_data_root() -> Path:
    """Return VECTOR's runtime data root.

    Production defaults to the repo-local ``data`` directory. Tests and smoke
    runs can set ``VECTOR_TEST_DATA_DIR`` or ``VECTOR_DATA_DIR`` to keep
    generated artifacts out of the real runtime state.
    """
    raw = os.environ.get("VECTOR_TEST_DATA_DIR") or os.environ.get("VECTOR_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return _PROJECT_ROOT / "data"


def data_path(*parts: str) -> Path:
    return get_data_root().joinpath(*parts)
