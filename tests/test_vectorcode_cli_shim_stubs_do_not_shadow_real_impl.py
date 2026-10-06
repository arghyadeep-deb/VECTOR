"""Regression for vectorcode/src/cli/{_bg_state,_tool_names}.py:

Both were "compatibility shim" modules that tried
`from vectorcode.src.vector_cli.X import *` and then, unconditionally (not
just in the except branch), redefined the real names with a trivial stub.
Since the wildcard import actually succeeds on this install, the stub
always won, silently replacing the real implementation with a broken one:

- _bg_state.get_status() returned a plain dict instead of a BgStatus
  instance, breaking every caller that reads BgStatus's real attributes
  (chat_cmd.py's startup banner / notification dispatcher).
- _tool_names.resolve_tool_names(names) took one positional argument,
  while every real caller (vector_cli/ask.py, vector_cli/chat_cmd.py)
  calls it with three -- a guaranteed TypeError on every agent-mode
  ask/chat invocation.

Same bug shape already found and fixed in vectorcode/src/cli/scan_cmd.py
this cycle (its stub PrivacyScanner shadowed the real one the same way).
"""
from __future__ import annotations

from vectorcode.src.cli import _bg_state, _tool_names
from vectorcode.src.vector_cli._bg_state import BgStatus as RealBgStatus
from vectorcode.src.vector_cli._bg_state import get_status as real_get_status
from vectorcode.src.vector_cli._tool_names import (
    resolve_tool_names as real_resolve_tool_names,
)


def test_bg_state_exports_the_real_get_status_and_bgstatus():
    assert _bg_state.get_status is real_get_status
    assert _bg_state.BgStatus is RealBgStatus

    status = _bg_state.get_status()
    assert isinstance(status, RealBgStatus)
    # The real dataclass has these attributes; the old stub dict did not.
    assert hasattr(status, "rust_extension")
    assert hasattr(status, "all_ready")


def test_tool_names_exports_the_real_resolve_tool_names_with_full_signature():
    assert _tool_names.resolve_tool_names is real_resolve_tool_names

    # Real callers (vector_cli/ask.py, vector_cli/chat_cmd.py) pass three
    # positional arguments -- the old stub only accepted one.
    result = _tool_names.resolve_tool_names("a,b", None, None)
    assert result == ["a", "b"]

    # Config fallback path.
    result = _tool_names.resolve_tool_names(None, None, ["x", "y"])
    assert result == ["x", "y"]
