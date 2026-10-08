"""VCMCP-4 regressions for JSON-RPC notification semantics."""
from __future__ import annotations

import pytest

from vectorcode.src.vc_mcp.protocol import INVALID_PARAMS, INVALID_REQUEST, MCPError, MCPRequest
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_mcp.transport import InProcessTransport


def test_missing_id_is_preserved_as_notification() -> None:
    request = MCPRequest.from_json(
        '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
    )
    assert request.id is None
    assert "id" not in request.to_dict()


def test_explicit_zero_id_remains_a_normal_request() -> None:
    request = MCPRequest.from_json(
        '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":0}'
    )
    assert request.id == 0


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ('{"method":"tools/list"}', INVALID_REQUEST),
        ('{"jsonrpc":"1.0","method":"tools/list"}', INVALID_REQUEST),
        ('{"jsonrpc":"2.0","method":4}', INVALID_REQUEST),
        ('{"jsonrpc":"2.0","method":"tools/list","params":[]}', INVALID_PARAMS),
        ('{"jsonrpc":"2.0","method":"tools/list","id":true}', INVALID_REQUEST),
    ],
)
def test_request_shape_is_validated(payload: str, code: int) -> None:
    with pytest.raises(MCPError) as exc_info:
        MCPRequest.from_json(payload)
    assert exc_info.value.code == code


def test_server_and_inprocess_transport_suppress_notification_response() -> None:
    server = MCPServer(tools=[])
    notification = MCPRequest(method="notifications/initialized", id=None)
    assert server.handle(notification) is None
    transport = InProcessTransport(server)
    assert transport.send_notification(notification) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
