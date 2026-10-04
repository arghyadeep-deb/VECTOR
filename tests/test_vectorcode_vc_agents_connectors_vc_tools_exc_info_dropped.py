"""Regression for a repo-wide bug across vectorcode/src/{vc_agents,connectors,vc_tools}/:

``logger.debug("...", exc_info=True)`` (and the corresponding ``.warning(...)``
call in connectors/apple_health.py) was called on a loguru logger, not a
stdlib one. loguru's bound methods do not recognize the stdlib ``exc_info``
kwarg at all -- it is silently accepted and dropped, so the traceback never
appears in the log. Every one of these calls was a "suppressed exception"
diagnostic whose entire purpose was to record what got swallowed; with
exc_info=True silently ignored, the diagnostic was permanently blind to the
actual exception.

Fixed by replacing every occurrence with loguru's real equivalent:
``logger.opt(exception=True).debug(...)``, which does attach the current
exception's traceback to the log record.

67 occurrences across 13 files were fixed this slice:
vc_agents/{image_agent,insight_agent,memory_agent,reasoning_agent,
skill_agent,tool_agent,video_agent,_abc}.py, connectors/{__init__,
apple_health}.py, vc_tools/{__init__,_abc}.py, vc_tools/storage/__init__.py.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_SRC_ROOT = _REPO_ROOT / "vectorcode" / "src"

_FIXED_FILES = [
    "vc_agents/image_agent.py",
    "vc_agents/insight_agent.py",
    "vc_agents/memory_agent.py",
    "vc_agents/reasoning_agent.py",
    "vc_agents/skill_agent.py",
    "vc_agents/tool_agent.py",
    "vc_agents/video_agent.py",
    "vc_agents/_abc.py",
    "connectors/__init__.py",
    "connectors/apple_health.py",
    "vc_tools/__init__.py",
    "vc_tools/_abc.py",
    "vc_tools/storage/__init__.py",
]


@pytest.mark.parametrize("rel_path", _FIXED_FILES)
def test_no_exc_info_kwarg_passed_to_loguru_logger(rel_path: str) -> None:
    src = (_SRC_ROOT / rel_path).read_text(encoding="utf-8")
    assert "exc_info=True" not in src, (
        f"{rel_path} still passes exc_info=True to a loguru logger call -- "
        "loguru silently drops this kwarg instead of attaching the traceback"
    )
    # Every file importing loguru directly (not just re-exporting it) should
    # still parse as valid Python after the scripted fix.
    ast.parse(src, filename=rel_path)


def test_loguru_silently_drops_exc_info_kwarg_confirmed_live() -> None:
    """Proves the underlying hazard this fix avoids: loguru's logger.debug()
    accepts exc_info=True without error but never attaches a traceback."""
    import io
    from loguru import logger as _logger

    buf = io.StringIO()
    handler_id = _logger.add(buf, format="{message}")
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            _logger.debug("suppressed", exc_info=True)
        dropped_output = buf.getvalue()
        assert "Traceback" not in dropped_output
        assert "ValueError" not in dropped_output

        buf.truncate(0)
        buf.seek(0)
        try:
            raise ValueError("boom")
        except ValueError:
            _logger.opt(exception=True).debug("suppressed")
        fixed_output = buf.getvalue()
        assert "Traceback" in fixed_output
        assert "ValueError" in fixed_output
    finally:
        _logger.remove(handler_id)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
