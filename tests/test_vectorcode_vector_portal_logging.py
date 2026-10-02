"""Regression: vectorcode/src/vector_cli/proxy/adapters/vector_portal.py used
stdlib `logging.getLogger(__name__)` instead of loguru (CLAUDE.md rule 6),
with %s-style placeholders that would silently break under loguru's own
{} formatter -- same systemic bug fixed 60+ times this cycle. Also removed
a call to vector_cli.auth._write_shared_nous_state(), a name that has never
existed anywhere in auth.py's git history -- importing this module raised
ImportError immediately.

NOTE: this module cannot actually be imported even after that fix --
`from vector_cli.proxy.adapters.base import UpstreamAdapter, UpstreamCredential`
fails because `vectorcode/src/vector_cli/proxy/adapters/base.py` (and
`proxy/__init__.py`, `proxy/adapters/__init__.py`) do not exist anywhere in
the repo. vector_portal.py is the ONLY file under proxy/ -- an orphaned
fragment of an incomplete port, not a narrow bug. Flagged for the owner
(needs a real base-class implementation decision, not a guess), not
built here. This test is source-level only; it cannot import the module.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_FILE = (
    Path(__file__).parent.parent
    / "vectorcode" / "src" / "vector_cli" / "proxy" / "adapters" / "vector_portal.py"
)


def test_uses_loguru_not_stdlib_logging():
    src = _FILE.read_text(encoding="utf-8")
    assert "from loguru import logger" in src
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_printf_style_placeholders_remain():
    src = _FILE.read_text(encoding="utf-8")
    assert not re.search(r'logger\.\w+\([^)]*%s', src)


def test_write_shared_nous_state_reference_removed():
    src = _FILE.read_text(encoding="utf-8")
    # Skip the module docstring (which explains this exact fix in prose,
    # and so legitimately names the removed function) -- check only the
    # real code after it.
    code_body = src.split('"""', 2)[-1]
    assert "_write_shared_nous_state" not in code_body


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
