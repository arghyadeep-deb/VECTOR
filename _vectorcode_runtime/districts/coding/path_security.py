"""Shared filesystem-confinement predicates for coding-district tools."""

from __future__ import annotations

import os
from pathlib import Path


def is_path_within(candidate: Path, root: Path) -> bool:
    """Return whether resolved ``candidate`` is inside resolved ``root``.

    ``normcase`` is required on Windows so containment follows the platform's
    case-insensitive path semantics rather than user-controlled spelling.
    """
    candidate_norm = os.path.normcase(str(candidate.resolve()))
    root_norm = os.path.normcase(str(root.resolve()))
    try:
        return os.path.commonpath((candidate_norm, root_norm)) == root_norm
    except ValueError:
        return False


if __name__ == "__main__":
    assert is_path_within(Path(__file__), Path(__file__).parent)
