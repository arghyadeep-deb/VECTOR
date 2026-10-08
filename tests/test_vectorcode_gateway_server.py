"""Regression tests for the standalone HTTP gateway server."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SOURCE_ROOT = Path("vectorcode/src").resolve()
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from gateway.server import GatewayServer  # noqa: E402


def test_unauthenticated_gateway_defaults_to_loopback() -> None:
    assert GatewayServer().host == "127.0.0.1"


def test_run_endpoint_fails_closed_without_invoking_ungoverned_runner() -> None:
    server = GatewayServer()
    server._run_task = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("ungoverned runner must not execute")
    )

    response = TestClient(server.build_app()).post("/run", json={"input": "hello"})

    assert response.status_code == 503
    assert "Permission Gateway" in response.json()["detail"]
    assert server._sessions == {}


def test_stream_endpoint_fails_closed_without_invoking_ungoverned_runner() -> None:
    server = GatewayServer()
    server._run_task_sync = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("ungoverned runner must not execute")
    )

    response = TestClient(server.build_app()).post("/stream", json={"input": "hello"})

    assert response.status_code == 503
    assert "Permission Gateway" in response.json()["detail"]
    assert server._sessions == {}
