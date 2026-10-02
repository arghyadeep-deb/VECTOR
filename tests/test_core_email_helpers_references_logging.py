"""Regression: core/email/helpers.py's build_references_chain() logged
"[VECTOR] suppressed exception (degraded mode)" via
logger.warning(msg, exc_info=True) on malformed email_references JSON --
loguru does not treat exc_info= as a traceback-capturing kwarg the way
stdlib logging does, so the real parse error was silently dropped. Fixed
to log the real exception. Behavior (falling back to an empty references
list) is unchanged -- this is a logging-content fix only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from core.email.helpers import build_references_chain


def test_malformed_references_json_logs_real_exception_and_degrades_gracefully():
    captured = []
    sink_id = logger.add(lambda msg: captured.append(msg), level="WARNING")
    try:
        result = build_references_chain({
            "id": "msg-1",
            "email_references": "{not valid json",
        })
    finally:
        logger.remove(sink_id)

    # Behavior unchanged: degrades to just the original message id.
    assert result["references"] == ["msg-1"]

    warning_text = "".join(str(m) for m in captured)
    assert "suppressed exception" not in warning_text
    assert "malformed email_references JSON" in warning_text


def test_valid_references_json_still_works():
    result = build_references_chain({
        "id": "msg-2",
        "email_references": '["ref-a", "ref-b"]',
    })
    assert result["references"] == ["ref-a", "ref-b", "msg-2"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
