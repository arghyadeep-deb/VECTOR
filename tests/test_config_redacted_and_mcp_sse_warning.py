"""Regression for 2 misleading-safety-net findings during the Phase 3
whole-repo audit (2026-10-02):

1. core/config.py's _Redacted(str) class only overrides __repr__ -- str(),
   f"{...}", and loguru's own "{}" placeholder all return the REAL
   plaintext value (confirmed: it's a true str subclass). Every one of
   ~30 real credentials wrapped via _secret() has this gap. NOT fixed
   (overriding __str__ would break core/inference/vectorcode_llm.py's own
   str(CONFIG["api_keys"]["anthropic_key"]) extraction and any similar
   real-use call site) -- the class's docstring was corrected to state
   this accurately instead of overclaiming "prevents accidental secret
   leaks in logs" when it does not, for the most common logging pattern
   in this exact codebase (f-strings / loguru "{}").

2. core/mcp_server.py's SSE non-localhost warning used to tell the
   operator "Set VECTOR_MCP_API_KEY env var for auth" -- nothing in the
   codebase ever reads that env var. Fixed the warning text to state
   there is no SSE auth mechanism today, instead of pointing at a
   non-functional one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_redacted_repr_is_safe_but_str_and_format_are_not():
    from core.config import _secret

    wrapped = _secret("realsecretvalue12345")
    assert "realsecretvalue12345" not in repr(wrapped)
    # Document the real, current gap -- str()/f-string DO return the real
    # value. If this assertion ever starts failing because __str__ was
    # overridden, every str(CONFIG[...]) consumer (e.g.
    # core/inference/vectorcode_llm.py:337) must be migrated to an
    # explicit real-value accessor FIRST, or those integrations will
    # silently break.
    assert str(wrapped) == "realsecretvalue12345"
    assert f"{wrapped}" == "realsecretvalue12345"


def test_redacted_docstring_documents_the_real_gap():
    from core.config import _Redacted

    doc = _Redacted.__doc__ or ""
    assert "str()" in doc or "__str__" in doc
    assert "FLAG FOR OWNER" in doc


def test_mcp_server_sse_warning_does_not_reference_unused_env_var():
    import inspect
    import core.mcp_server as mcp_server

    src = inspect.getsource(mcp_server.main)
    # The actual logger.warning() call text must not tell the operator to
    # set an env var that's never read -- a trailing comment documenting
    # the removed claim (for future readers) is fine and expected.
    warning_call = src[src.index("logger.warning(f\"[VECTOR][mcp] SSE"):]
    warning_call = warning_call[:warning_call.index(")") + 1]
    assert "VECTOR_MCP_API_KEY" not in warning_call
    assert "no SSE authentication mechanism" in warning_call


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
