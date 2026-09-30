"""Regression test for core/api/routers/code_intel.py's path-confinement bypass.

Found by a Claude self-fork's deep-verify pass on core/api/routers/ batch 1
(Phase 3 whole-repo audit, 2026-09-30). _safe_path() rejected out-of-root
paths using a naive `str(resolved).startswith(str(_PROJECT_ROOT))` check --
the classic CWE-22 prefix-matching bypass: a sibling directory that happens
to share the same string prefix as the project root (e.g.
"...\\V.E.C.T.O.R. CodebaseEVIL\\secret.txt" against root
"...\\V.E.C.T.O.R. Codebase") passes startswith() without being inside the
root at all. Fixed with Path.is_relative_to(), which respects path-component
boundaries instead of raw string prefixes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.code_intel import SearchRequest, _PROJECT_ROOT, _safe_path


def test_sibling_directory_sharing_string_prefix_is_rejected():
    """The exact bypass shape: a sibling dir whose name starts with the
    project root's own folder name string."""
    evil_path = str(_PROJECT_ROOT) + "EVIL" + "/secret.txt"
    with pytest.raises(ValueError, match="outside the VECTOR codebase"):
        _safe_path(evil_path)


def test_path_traversal_dotdot_is_rejected():
    traversal = str(_PROJECT_ROOT / ".." / ".." / "etc" / "passwd")
    with pytest.raises(ValueError, match="outside the VECTOR codebase"):
        _safe_path(traversal)


def test_genuine_in_root_path_is_accepted():
    in_root = str(_PROJECT_ROOT / "core" / "config.py")
    assert _safe_path(in_root) == in_root


def test_project_root_itself_is_accepted():
    assert _safe_path(str(_PROJECT_ROOT)) == str(_PROJECT_ROOT)


def test_search_request_model_rejects_sibling_prefix_path():
    evil_path = str(_PROJECT_ROOT) + "EVIL"
    with pytest.raises(ValidationError):
        SearchRequest(query="test", project_path=evil_path)


def test_search_request_model_accepts_real_subpath():
    real_path = str(_PROJECT_ROOT / "core")
    req = SearchRequest(query="test", project_path=real_path)
    assert req.project_path == real_path


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
