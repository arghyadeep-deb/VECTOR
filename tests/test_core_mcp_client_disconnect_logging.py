"""Regression: core/mcp/client.py's MCPClient.disconnect() used the
"[VECTOR] suppressed exception (degraded mode)" placeholder (loguru's
exc_info=True does not capture the real exception the way stdlib logging
does) -- same systemic bug fixed 50+ times this cycle. MCPClient is dormant
(zero real callers anywhere, confirmed via repo-wide grep -- the matches
elsewhere in the repo are a different MCPClient class), fixed anyway per
this cycle's "fix narrow bugs even in dormant code" bar.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mcp.client import MCPClient


def test_disconnect_logs_real_exception_not_placeholder():
    client = MCPClient(servers=[])
    bad_transport = MagicMock()
    bad_transport.disconnect.side_effect = RuntimeError("boom")
    client._transports = {"bad": bad_transport}

    with patch("core.mcp.client.logger") as mock_logger:
        asyncio.get_event_loop().run_until_complete(client.disconnect())

    assert mock_logger.warning.called
    args = mock_logger.warning.call_args[0]
    assert "degraded mode" not in args[0]
    assert "boom" in str(mock_logger.warning.call_args)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
