"""Resolve VECTOR_HOME for standalone skill scripts.

Skill scripts may run outside the VectorCode process (e.g. system Python,
nix env, CI) where ``vector_constants`` is not importable.  This module
provides the same ``get_vector_home()`` and ``display_vector_home()``
contracts as ``vector_constants`` without requiring it on ``sys.path``.

When ``vector_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``vector_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``VECTOR_HOME = Path(os.environ.get(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from vector_constants import display_vector_home as display_vector_home
    from vector_constants import get_vector_home as get_vector_home
except (ModuleNotFoundError, ImportError):

    def get_vector_home() -> Path:
        """Return the VectorCode home directory (default: ~/.vectorcode).

        Mirrors ``vector_constants.get_vector_home()``."""
        val = os.environ.get("VECTOR_HOME", "").strip()
        return Path(val) if val else Path.home() / ".vector"

    def display_vector_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``vector_constants.display_vector_home()``."""
        home = get_vector_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
