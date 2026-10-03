"""Regression: vectorcode/src/acp_adapter/events.py used stdlib
logging.getLogger(__name__) instead of loguru (CLAUDE.md rule 6), with
%s-style placeholders and exc_info=True -- loguru silently no-ops on an
unrecognized exc_info= kwarg (verified elsewhere this cycle with a
standalone repro), so both except-blocks were dropping the real exception.

This package has a hard dependency on the external `agent-client-protocol`
(acp) package, not installed in this sandbox (confirmed:
`from acp.schema import ...` in the sibling tools.py module raises
ModuleNotFoundError) -- verified via source inspection, not a live import,
same approach used for this package's other files this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_SRC = (Path(__file__).parent.parent / "vectorcode" / "src" / "acp_adapter" / "events.py").read_text(encoding="utf-8")


def test_imports_loguru_not_stdlib_logging():
    assert "from loguru import logger" in _SRC
    assert "import logging" not in _SRC
    assert "logging.getLogger" not in _SRC


def test_no_exc_info_kwarg_remains():
    # exc_info=True is a stdlib-logging-only kwarg; loguru silently
    # ignores it, which is exactly the bug this fix removes.
    assert "exc_info=True" not in _SRC


def test_except_blocks_use_opt_exception_for_real_traceback():
    assert _SRC.count("logger.opt(exception=True)") == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
