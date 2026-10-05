"""Regression test: callers of get_rust_module() must handle a None return,
not just an ImportError.

get_rust_module() returns None (its documented contract), not an
ImportError, when the vectorcode Rust extension isn't compiled. Two call
sites dereferenced the result unconditionally and only caught
(ImportError, ModuleNotFoundError):
  - vc_tools/think.py: ThinkTool.execute() called _rust.ThinkTool() with no
    None-check, so the "pure-Python fallback" comment was dead code -- the
    "zero-cost reasoning scratchpad" tool crashed on every single call on a
    machine without the compiled extension.
  - vc_security/file_policy.py: is_sensitive_file() (fixed in an earlier
    commit this round, tested in test_vectorcode_vc_tools_storage_ingest_sensitive.py).

A third site, vc_tools/storage/bm25.py's BM25Memory, has no pure-Python
fallback at all (despite its docstring claiming "Uses the rank_bm25
library") -- fixed to fail with a clear RuntimeError instead of a
confusing AttributeError.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vectorcode.src.vc_tools.think import ThinkTool


def test_think_tool_falls_back_when_rust_module_is_none() -> None:
    tool = ThinkTool()
    with patch(
        "vectorcode.src._rust_bridge.get_rust_module",
        return_value=None,
    ):
        result = tool.execute(thought="reasoning step one")

    assert result.success
    assert result.content == "reasoning step one"


def test_bm25_memory_raises_clear_error_when_rust_module_is_none() -> None:
    from vectorcode.src.vc_tools.storage.bm25 import BM25Memory

    with patch(
        "vectorcode.src.vc_tools.storage.bm25.get_rust_module",
        return_value=None,
    ):
        with pytest.raises(RuntimeError, match="compiled vectorcode Rust extension"):
            BM25Memory()
