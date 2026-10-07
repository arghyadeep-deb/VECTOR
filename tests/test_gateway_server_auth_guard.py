"""Regression tests for OD-50: standalone gateway network authentication."""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vectorcode" / "src"))

from gateway.server import GatewayServer  # noqa: E402


def test_network_accessible_gateway_without_key_refuses_start(monkeypatch):
    monkeypatch.delenv("VECTOR_GATEWAY_KEY", raising=False)

    async def fail_if_served(_server):
        pytest.fail("network-accessible gateway reached uvicorn without authentication")

    monkeypatch.setattr("uvicorn.Server.serve", fail_if_served)
    server = GatewayServer(host="0.0.0.0", port=0)

    with pytest.raises(RuntimeError, match=r"VECTOR_GATEWAY_KEY.*127\.0\.0\.1"):
        asyncio.run(server.start())


def test_loopback_gateway_without_key_may_start(monkeypatch):
    monkeypatch.delenv("VECTOR_GATEWAY_KEY", raising=False)
    served = False

    async def record_serve(_server):
        nonlocal served
        served = True

    monkeypatch.setattr("uvicorn.Server.serve", record_serve)

    server = GatewayServer(host="127.0.0.1", port=0)
    asyncio.run(server.start())

    assert served, "loopback gateway should reach uvicorn even without authentication"


def test_network_accessible_gateway_rejects_placeholder_key(monkeypatch):
    monkeypatch.setenv("VECTOR_GATEWAY_KEY", "changeme")

    async def fail_if_served(_server):
        pytest.fail("gateway reached uvicorn with a placeholder key")

    monkeypatch.setattr("uvicorn.Server.serve", fail_if_served)
    server = GatewayServer(host="0.0.0.0", port=0)

    with pytest.raises(RuntimeError, match=r"too short or a placeholder"):
        asyncio.run(server.start())


def test_key_protected_gateway_requires_valid_bearer_token(monkeypatch):
    api_key = "real-gateway-secret"
    monkeypatch.setenv("VECTOR_GATEWAY_KEY", api_key)
    client = TestClient(GatewayServer(host="0.0.0.0", port=0).build_app())

    assert client.get("/status").status_code == 401
    assert client.get(
        "/status", headers={"Authorization": "Bearer wrong-secret"}
    ).status_code == 401

    response = client.get(
        "/status", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health_is_public_and_wildcard_cors_disables_credentials(monkeypatch):
    monkeypatch.setenv("VECTOR_GATEWAY_KEY", "real-gateway-secret")
    client = TestClient(GatewayServer(host="0.0.0.0", port=0).build_app())

    assert client.get("/health").status_code == 200

    response = client.options(
        "/status",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
