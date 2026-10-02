"""Regression: WebhookServer defaulted to host="0.0.0.0" (all network
interfaces) while exposing an unauthenticated /notify endpoint that
dispatches arbitrary internal events to every registered handler -- same
vulnerability class already fixed in core/mcp_server.py and MCP's --http
mode this cycle (bind to 127.0.0.1 by default, not every interface).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.comms.webhook_server import WebhookServer


def test_default_host_is_localhost_not_all_interfaces():
    server = WebhookServer()
    assert server.host == "127.0.0.1"


def test_explicit_host_override_still_works():
    server = WebhookServer(host="0.0.0.0")
    assert server.host == "0.0.0.0"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
