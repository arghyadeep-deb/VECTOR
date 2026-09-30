"""Regression test for core/api/routers/knowledge.py's directory-confinement
bypass (CWE-22) and an unconfined wiki_root gap, found by a Claude self-fork's
deep-verify pass on a 30-file batch of core/api/routers/ (Phase 3 whole-repo
audit, Claude/Codex 50/50 split, 2026-09-30).

Same bug class as core/api/routers/code_intel.py's _safe_path() (commit
3e05e02d7 this cycle): `str(resolved).startswith(str(root))` is a classic
CWE-22 prefix-matching bypass -- a sibling directory sharing the same string
prefix as an allowed root passes startswith() without being inside the root
at all. Fixed with Path.is_relative_to(), which respects path-component
boundaries.

Separately, parse_wiki() and merge_wiki() in this same file took a caller-
supplied wiki_root with ZERO confinement check at all, unlike their sibling
endpoints (scan_domain, knowledge_graph) which both correctly used
_safe_path() -- an inconsistency within the same file. Fixed by routing both
through the same helper.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.knowledge import _safe_path, parse_wiki, merge_wiki, ParseWikiReq, MergeWikiReq
from fastapi import HTTPException


def test_safe_path_rejects_sibling_with_shared_string_prefix():
    """The exact CWE-22 bypass: a sibling dir whose name starts with the
    same characters as an allowed root must NOT be treated as inside it."""
    import core.api.routers.knowledge as knowledge_mod

    root = knowledge_mod._PROJECT_ROOT
    evil_sibling = root.parent / (root.name + "EVIL") / "secret.txt"

    with pytest.raises(ValueError, match="outside allowed directories"):
        _safe_path(str(evil_sibling))


def test_safe_path_accepts_real_paths_inside_root():
    import core.api.routers.knowledge as knowledge_mod
    root = knowledge_mod._PROJECT_ROOT
    inside = root / "docs" / "OPEN_ISSUES.md"
    result = _safe_path(str(inside))
    assert result == inside.resolve()


def test_safe_path_accepts_the_root_itself():
    import core.api.routers.knowledge as knowledge_mod
    root = knowledge_mod._PROJECT_ROOT
    result = _safe_path(str(root))
    assert result == root


def test_safe_path_rejects_dotdot_traversal():
    import core.api.routers.knowledge as knowledge_mod
    root = knowledge_mod._PROJECT_ROOT
    traversal = str(root / ".." / ".." / "Windows" / "System32")
    with pytest.raises(ValueError, match="outside allowed directories"):
        _safe_path(traversal)


@pytest.mark.asyncio
async def test_parse_wiki_rejects_path_outside_allowed_roots():
    """parse_wiki() previously had NO confinement check at all -- any
    directory on disk was acceptable. Now must reject an out-of-tree path.
    _safe_path() raises ValueError, which these endpoints' generic
    `except Exception` handler wraps as a 500 (not the 400 used for a
    resolved-but-missing directory) -- what matters for this regression is
    that the real, unconfined path is rejected at all, not the exact code."""
    with tempfile.TemporaryDirectory() as td:
        outside = Path(td) / "not_the_wiki"
        outside.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            await parse_wiki(ParseWikiReq(wiki_root=str(outside)))
        assert "outside allowed directories" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_merge_wiki_rejects_path_outside_allowed_roots():
    with tempfile.TemporaryDirectory() as td:
        outside = Path(td) / "not_the_wiki"
        outside.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            await merge_wiki(MergeWikiReq(wiki_root=str(outside)))
        assert "outside allowed directories" in str(exc_info.value.detail)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
