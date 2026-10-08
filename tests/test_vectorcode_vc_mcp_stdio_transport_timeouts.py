"""VCMCP-3 regressions for bounded asyncio stdio transport I/O."""
from __future__ import annotations

import sys
import time

import pytest

from vectorcode.src.vc_mcp.protocol import MCPRequest
from vectorcode.src.vc_mcp.transport import StdioTransport


def test_silent_child_times_out_instead_of_hanging() -> None:
    transport = StdioTransport(
        [sys.executable, "-c", "import sys, time; sys.stdin.readline(); time.sleep(60)"],
        request_timeout=0.15,
    )
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="did not respond"):
            transport.send(MCPRequest(method="tools/list", id=1))
        assert time.monotonic() - started < 2
        assert transport._process is None
    finally:
        transport.close()


def test_partial_line_times_out_and_stderr_is_drained() -> None:
    script = (
        "import sys, time; sys.stdin.readline(); "
        "sys.stderr.write('x' * 200000); sys.stderr.flush(); "
        "sys.stdout.write('{\\\"jsonrpc\\\":\\\"2.0\\\"'); sys.stdout.flush(); time.sleep(60)"
    )
    transport = StdioTransport(
        [sys.executable, "-c", script],
        request_timeout=0.3,
    )
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="did not respond"):
            transport.send(MCPRequest(method="tools/list", id=1))
        assert time.monotonic() - started < 2
    finally:
        transport.close()


def test_notification_write_does_not_wait_for_response() -> None:
    transport = StdioTransport(
        [sys.executable, "-c", "import sys, time; sys.stdin.readline(); time.sleep(60)"],
        request_timeout=0.15,
    )
    started = time.monotonic()
    try:
        transport.send_notification(MCPRequest(method="notifications/initialized", id=None))
        assert time.monotonic() - started < 1
        assert transport._process is not None
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
