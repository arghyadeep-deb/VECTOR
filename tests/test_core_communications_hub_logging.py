"""Regression: core/communications/hub.py's get_pending_count() used the
"[VECTOR] suppressed exception (degraded mode)" placeholder (loguru's
exc_info=True does not capture the real exception the way stdlib logging
does) -- same systemic bug class fixed 50+ times this cycle. CommsHub is
documented DORMANT (not imported by the running VECTOR), fixed anyway per
this cycle's "fix narrow bugs even in dormant code" bar.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.communications.hub import CommsHub


def test_get_pending_count_logs_real_exception_not_placeholder():
    hub = CommsHub.__new__(CommsHub)
    bad_adapter = MagicMock()
    bad_adapter.pending_count.side_effect = RuntimeError("boom")
    hub._adapters = {"telegram": bad_adapter}

    with patch("core.communications.hub.logger") as mock_logger:
        total = hub.get_pending_count()

    assert total == 0
    assert mock_logger.warning.called
    args = mock_logger.warning.call_args[0]
    assert "degraded mode" not in args[0]
    assert "boom" in str(mock_logger.warning.call_args)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
