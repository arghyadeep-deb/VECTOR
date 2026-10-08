"""Security regressions for the remote MCP HTTP transport."""
from __future__ import annotations

import os
import socket

import httpx
import pytest

from vectorcode.src.vc_mcp.protocol import MCPRequest
from vectorcode.src.vc_mcp.transport import StreamableHTTPTransport


def _transport(url: str, handler, **kwargs) -> StreamableHTTPTransport:
    transport = StreamableHTTPTransport(url, **kwargs)
    transport._client.close()
    transport._client = httpx.Client(transport=httpx.MockTransport(handler))
    return transport


@pytest.fixture(autouse=True)
def _pin_test_host(monkeypatch):
    original = socket.getaddrinfo

    def resolve(host, *args, **kwargs):
        if host == "mcp.example.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return original(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_private_mcp_endpoint_is_blocked_before_network_io() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    transport = _transport("http://169.254.169.254/latest/meta-data", handler)
    with pytest.raises(RuntimeError, match="Blocked unsafe MCP endpoint"):
        transport.send(MCPRequest(method="tools/list", id=1))
    assert calls == []
    transport.close()


def test_redirect_destination_is_rechecked_before_second_request(monkeypatch) -> None:
    checked: list[str] = []

    def fake_check(url: str) -> str | None:
        checked.append(url)
        return "private redirect" if url.endswith("/admin") else None

    monkeypatch.setattr("vectorcode.src.vc_mcp.transport.check_ssrf", fake_check)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"Location": "/admin"})

    transport = _transport("https://mcp.example.test/rpc", handler)
    with pytest.raises(RuntimeError, match="Blocked unsafe MCP endpoint"):
        transport.send(MCPRequest(method="tools/list", id=1))
    assert checked == ["https://mcp.example.test/rpc", "https://mcp.example.test/admin"]
    assert len(calls) == 1
    transport.close()


def test_environment_backed_bearer_token_is_attached_and_secret_wrapped(monkeypatch) -> None:
    monkeypatch.setenv("MCP_REMOTE_API_KEY", "top-secret-token")
    secret = StreamableHTTPTransport.bearer_token_from_config(
        {"headers": {"Authorization": "Bearer ${MCP_REMOTE_API_KEY}"}}
    )
    assert secret is not None
    assert "top-secret-token" not in repr(secret)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer top-secret-token"
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    transport = _transport("https://mcp.example.test/rpc", handler, bearer_token=secret)
    transport.send(MCPRequest(method="tools/list", id=1))
    transport.close()


def test_missing_configured_bearer_secret_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("MCP_MISSING_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="is not set"):
        StreamableHTTPTransport.bearer_token_from_config(
            {"bearer_token_env": "MCP_MISSING_TOKEN"}
        )


def test_dns_result_is_pinned_and_private_rebinding_is_rejected(monkeypatch) -> None:
    answers = [
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: answers.pop(0))
    pinned, _, _ = StreamableHTTPTransport._pin_destination("https://mcp.example.test/rpc")
    assert pinned.startswith("https://93.184.216.34")
    with pytest.raises(RuntimeError, match="private or reserved"):
        StreamableHTTPTransport._pin_destination("https://mcp.example.test/rpc")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
