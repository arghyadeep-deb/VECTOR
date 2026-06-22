"""
Regression test for missing persistent log sink in long-running launcher modes.

run_vector.py's loop/api modes only ever logged through loguru's default
stderr sink — confirmed by grep (zero `logger.add(<file>...)` calls anywhere
in the launcher). When the soak's background process's terminal went away,
even a CRITICAL unhandled-exception log line (run_vector.py's own
`_global_excepthook`/`_asyncio_exception_handler`) was unrecoverable —
there was nothing to inspect after the fact to root-cause why the process
stopped. This test locks in that a rotating file sink now exists for
long-running modes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_configure_file_logging_creates_log_file(tmp_path, monkeypatch):
    from loguru import logger
    import run_vector

    monkeypatch.setattr(run_vector, "data_path", lambda *p: tmp_path.joinpath(*p))

    sink_id = run_vector._configure_file_logging("loop")
    try:
        logger.critical("test critical message for sink verification")
        logger.complete()

        log_file = tmp_path / "logs" / "vector_loop.log"
        assert log_file.exists()
        assert "test critical message for sink verification" in log_file.read_text(encoding="utf-8")
    finally:
        logger.remove(sink_id)


def test_configure_file_logging_returns_none_when_disabled(monkeypatch):
    import run_vector

    monkeypatch.setenv("VECTOR_DISABLE_FILE_LOGGING", "1")
    try:
        result = run_vector._configure_file_logging("loop")
        assert result is None
    finally:
        monkeypatch.delenv("VECTOR_DISABLE_FILE_LOGGING", raising=False)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
