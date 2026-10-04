"""Regression tests for the standalone HTTP gateway server."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


SOURCE_ROOT = Path("vectorcode/src").resolve()
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from gateway.server import GatewayServer, RunResponse  # noqa: E402


def test_unauthenticated_gateway_defaults_to_loopback() -> None:
    assert GatewayServer().host == "127.0.0.1"


def test_run_endpoint_uses_async_runner_without_worker_thread_event_loop_lookup() -> None:
    server = GatewayServer()
    app = server.build_app()
    run_route = next(route for route in app.routes if route.path == "/run")
    run_endpoint = run_route.endpoint

    async def fake_run_task(session_id, request):
        return RunResponse(
            session_id=session_id,
            response="ok",
            tool_calls_made=0,
            iterations_used=1,
            model=request.model,
            status="complete",
        )

    server._run_task = fake_run_task
    request_model = run_route.dependant.body_params[0].field_info.annotation(input="hello")
    result = asyncio.run(run_endpoint(request_model))

    assert result["response"] == "ok"
    assert result["status"] == "complete"
