"""Regression: districts/coding/code_reviewer.py's review_with_llm() and
districts/coding/addy_code_reviewer.py's review_file() both read a
caller-supplied path with zero confinement, then fed the file contents into
an LLM prompt. Both are reachable directly via Governor dispatch (run()),
not just through core/mcp_tools/builtins.py's review_code MCP tool, which
already confines paths for a different call shape -- a dispatch that
bypasses that one gated tool had no protection at all. Confined both to the
repo root + .py suffix, matching the MCP tool's existing pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from districts.coding.code_reviewer import CodeReviewer
from districts.coding.addy_code_reviewer import AddyCodeReviewer


@pytest.mark.asyncio
async def test_review_with_llm_refuses_outside_repo_path(tmp_path):
    reviewer = CodeReviewer()
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'sk-real-secret'\n")
    result = await reviewer.review_with_llm(str(outside))
    assert "error" in result
    assert "repo" in result["error"].lower()


@pytest.mark.asyncio
async def test_review_with_llm_refuses_non_python_file():
    reviewer = CodeReviewer()
    result = await reviewer.review_with_llm(str(Path(__file__).resolve().parents[1] / ".env"))
    assert "error" in result


@pytest.mark.asyncio
async def test_review_with_llm_accepts_real_repo_py_file():
    reviewer = CodeReviewer()
    # Doesn't need to succeed end-to-end (no live LLM in CI) -- just must
    # pass the confinement check and reach the real file-not-found/LLM path,
    # not get refused for being "outside the repo".
    this_file = str(Path(__file__).resolve())
    result = await reviewer.review_with_llm(this_file)
    assert result.get("error") != "Path must be a .py file inside the VECTOR repo"


@pytest.mark.asyncio
async def test_addy_review_file_refuses_outside_repo_path(tmp_path):
    reviewer = AddyCodeReviewer()
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'sk-real-secret'\n")
    result = await reviewer.review_file(str(outside))
    assert result["status"] == "error"
    assert "repo" in result["error"].lower()


@pytest.mark.asyncio
async def test_addy_review_file_refuses_non_python_file():
    reviewer = AddyCodeReviewer()
    result = await reviewer.review_file(str(Path(__file__).resolve().parents[1] / ".env"))
    assert result["status"] == "error"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
