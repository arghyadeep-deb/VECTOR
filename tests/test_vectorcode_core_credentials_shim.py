"""Regression for vectorcode/src/core/credentials.py: it defined its own
disconnected TOOL_CREDENTIALS = {} (always empty) and a get_credential_status()
that always returned the literal string "unknown" instead of a dict -- unlike
every sibling file in this directory (config.py/events.py/registry.py/types.py),
which correctly re-export vc_core/. The real caller, vectorcode/src/vector_cli/
serve.py, does `for v in get_credential_status(tool).values()`, which would
raise AttributeError on a plain string. The bug was masked only because the
shim's TOOL_CREDENTIALS was always empty, so the broken call was never reached.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.core.credentials import TOOL_CREDENTIALS, get_credential_status
from vectorcode.src.vc_core.credentials import TOOL_CREDENTIALS as _REAL_CREDS


def test_tool_credentials_is_the_real_populated_dict():
    assert TOOL_CREDENTIALS is _REAL_CREDS
    assert len(TOOL_CREDENTIALS) > 0
    assert "web_search" in TOOL_CREDENTIALS


def test_get_credential_status_returns_dict_not_string():
    status = get_credential_status("web_search")
    assert isinstance(status, dict)
    # The exact shape serve.py relies on: iterable .values() of booleans.
    assert all(isinstance(v, bool) for v in status.values())


def test_get_credential_status_matches_real_module():
    from vectorcode.src.vc_core.credentials import get_credential_status as real_status
    assert get_credential_status("slack") == real_status("slack")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
