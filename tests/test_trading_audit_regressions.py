"""Regression tests for the 2026-10-07 core.trading audit."""

import inspect
from functools import wraps
from unittest.mock import Mock, patch

from core.trading.cli import announcements
from core.trading.cli.main import MessageBuffer, _atomic_write_text
from core.trading.agents.utils.memory import TradingMemoryLog


def test_announcements_preserves_explicit_zero_timeout() -> None:
    response = Mock()
    response.json.return_value = {"announcements": ["ok"]}

    with patch("core.trading.cli.announcements.httpx.get", return_value=response) as get:
        result = announcements.fetch_announcements("https://example.invalid", timeout=0)

    assert result == {"announcements": ["ok"], "require_attention": False}
    get.assert_called_once_with("https://example.invalid", timeout=0)


def test_message_buffer_wrappers_unwrap_to_original_bound_method() -> None:
    """Repeated CLI runs must not build wrapper-on-wrapper call chains."""
    buffer = MessageBuffer()
    original = buffer.add_message

    @wraps(original)
    def first_wrapper(*args, **kwargs):
        return original(*args, **kwargs)

    buffer.add_message = first_wrapper
    assert inspect.unwrap(buffer.add_message) == original


def test_memory_atomic_write_flushes_and_fsyncs_before_replace(tmp_path) -> None:
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})

    with patch("core.trading.agents.utils.memory.os.fsync") as fsync:
        log._atomic_write("durable")

    fsync.assert_called_once()
    assert (tmp_path / "memory.md").read_text(encoding="utf-8") == "durable"
    assert list(tmp_path.glob(".memory.md.*.tmp")) == []


def test_report_atomic_write_cleans_temp_file_on_replace_failure(tmp_path) -> None:
    target = tmp_path / "report.md"

    with patch("core.trading.cli.main.os.replace", side_effect=OSError("disk full")):
        try:
            _atomic_write_text(target, "report")
        except OSError:
            pass
        else:
            raise AssertionError("replace failure should propagate")

    assert not target.exists()
    assert list(tmp_path.glob(".report.md.*.tmp")) == []
