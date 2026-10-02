"""Regression: 3 "[VECTOR] suppressed exception (degraded mode)" placeholder
loguru calls in core/jcode/ silently dropped the real exception --
logger.warning(msg, exc_info=True) does not work like stdlib logging under
loguru. Same systemic bug class fixed 45+ times this cycle. Found during the
Phase 3 whole-repo audit (2026-10-02).
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.jcode.session_persistence import SessionPersistence
from core.jcode.ambient_scheduler import AmbientScheduler


def test_list_sessions_logs_real_exception_on_bad_json(tmp_path):
    store = SessionPersistence(sessions_dir=tmp_path)
    (tmp_path / "corrupt.json").write_text("{not valid json")
    with patch("core.jcode.session_persistence.logger") as mock_logger:
        sessions = store.list_sessions()
    assert sessions == []
    assert mock_logger.warning.called
    args = mock_logger.warning.call_args[0]
    assert "degraded mode" not in args[0]
    assert "corrupt.json" in str(mock_logger.warning.call_args)


def test_load_directives_logs_real_exception_on_bad_json(tmp_path):
    sched = AmbientScheduler(base_dir=tmp_path)
    sched._directives_file.write_text("{not valid json")
    with patch("core.jcode.ambient_scheduler.logger") as mock_logger:
        result = sched.load_directives()
    assert result == []
    assert mock_logger.warning.called
    assert "degraded mode" not in mock_logger.warning.call_args[0][0]


def test_load_queue_logs_real_exception_on_bad_json(tmp_path):
    sched = AmbientScheduler(base_dir=tmp_path)
    sched._queue_file.write_text("{not valid json")
    with patch("core.jcode.ambient_scheduler.logger") as mock_logger:
        result = sched.peek_queue()
    assert result == []
    assert mock_logger.warning.called
    assert "degraded mode" not in mock_logger.warning.call_args[0][0]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
