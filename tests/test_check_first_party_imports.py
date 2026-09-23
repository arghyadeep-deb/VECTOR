"""Regression test for the 2026-09-24 external review's Phase 1 finding:
5 first-party imports pointed at modules that never existed (db_guardian.py,
content_arm.py, simulation.py, research.py, core/mining/*), silently
swallowed by broad except blocks so the features just did nothing.

Drives the real scripts/check_first_party_imports.py checker against the
real repo -- this is a regression guard for the checker AND for the 5
fixed import sites (any of them breaking again fails this test).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_first_party_imports import _check_file, _iter_first_party_files, REPO_ROOT  # noqa: E402


def test_no_broken_first_party_imports():
    all_problems: list[str] = []
    for path in _iter_first_party_files():
        all_problems.extend(_check_file(path))
    assert not all_problems, (
        "broken first-party imports found (excluding the documented "
        "KNOWN_DEAD_IMPORTS allowlist):\n" + "\n".join(all_problems)
    )


def test_the_5_originally_broken_imports_now_resolve():
    """The exact sites the 2026-09-24 external review found broken."""
    for rel_path in (
        "core/memory/db_guardian.py",
        "districts/growth/content_arm.py",
        "core/api/routers/simulation.py",
        "core/api/routers/research.py",
        "core/mining/__init__.py",
        "core/mining/discovery.py",
    ):
        problems = _check_file(REPO_ROOT / rel_path)
        assert not problems, f"{rel_path} has broken imports again: {problems}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
