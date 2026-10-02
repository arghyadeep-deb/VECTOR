"""Regression: core/scheduler/scheduler.py used stdlib `logging` throughout
(CLAUDE.md rule 6: use loguru everywhere), ported from VectorCode and never
converted -- unlike the file's own explicit, documented exception for
`threading` (a deliberate design choice with its own comment), there was no
such justification for the logging library choice. Converted to loguru;
this proves the module still imports and runs with a loguru-backed logger,
and that the croniter-ImportError fallback path still works correctly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scheduler.scheduler import TaskScheduler, logger


def test_scheduler_module_uses_loguru_logger():
    # loguru's Logger object exposes .opt(); stdlib logging.Logger does not.
    assert hasattr(logger, "opt")


def test_compute_next_cron_basic_fallback_still_works():
    from datetime import datetime, timezone
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    result = TaskScheduler._compute_next_cron("30 14 * * *", now)
    assert result is not None
    assert "14:30" in result


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
