import asyncio

from fastapi.testclient import TestClient

from core.api import create_app
from core.loop.permission_gateway import GatewayResult
from core.runtime.executor import AutonomousExecutor


class FakeGateway:
    def __init__(self, result: GatewayResult):
        self.result = result
        self.seen = []

    def _classify(self, action_type: str) -> str:
        if action_type == "unknown_action":
            return "UNKNOWN"
        return self.result.level

    async def execute(self, action):
        self.seen.append(action)
        return self.result


def test_executor_dry_run_only_plans() -> None:
    gateway = FakeGateway(GatewayResult(True, "GREEN", True, {"status": "ok"}, "ok"))
    report = asyncio.run(
        AutonomousExecutor(permission_gateway=gateway).execute(
            "respond",
            {"message": "hello"},
            dry_run=True,
        )
    )

    assert report.status == "planned"
    assert report.gateway is None
    assert gateway.seen == []


def test_executor_reports_verified_execution() -> None:
    gateway = FakeGateway(GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"))
    report = asyncio.run(
        AutonomousExecutor(permission_gateway=gateway).execute("respond", {"message": "ok"})
    )

    assert report.status == "executed"
    assert report.verification["ok"] is True
    assert gateway.seen[0].action_type == "respond"


def test_executor_blocks_denied_gateway_result() -> None:
    gateway = FakeGateway(GatewayResult(False, "UNKNOWN", False, {}, "Unknown action"))
    report = asyncio.run(
        AutonomousExecutor(permission_gateway=gateway).execute("unknown_action", {})
    )

    assert report.status == "blocked"
    assert report.verification["ok"] is False
    assert "not_approved" in report.verification["checks"]


def test_executor_treats_agent_authored_success_status_as_success() -> None:
    """2026-09-23 regression test: a real, working district agent's own
    run() result reaches here UNMODIFIED on success (Governor.dispatch()
    returns it as-is, core/city/governor.py:2701) -- and most real agents
    (districts/agency/client_manager.py, districts/calls/*, districts/
    content/*, districts/investment/*, ~100+ call sites) use "success", not
    "ok", as their own native status string. A prior fix briefly flipped
    this check to a whitelist of exactly {"ok", "executed"}, which would
    have wrongly certified this as a FAILURE."""
    gateway = FakeGateway(
        GatewayResult(True, "GREEN", True, {"status": "success", "client": "acme"}, "Auto")
    )
    report = asyncio.run(
        AutonomousExecutor(permission_gateway=gateway).execute("hand_content", {})
    )

    assert report.status == "executed"
    assert report.verification["ok"] is True


def test_executor_does_not_treat_not_implemented_as_success() -> None:
    gateway = FakeGateway(
        GatewayResult(
            True,
            "GREEN",
            True,
            {"status": "not_implemented", "note": "not wired"},
            "Auto",
        )
    )
    report = asyncio.run(
        AutonomousExecutor(permission_gateway=gateway).execute("play_music", {})
    )

    assert report.status == "failed"
    assert report.verification["ok"] is False
    assert "result_status:not_implemented" in report.verification["checks"]


def test_execute_plan_endpoint_returns_contract(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_API_KEY", "test-executor-key")
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")
    )
    client = TestClient(app, client=("127.0.0.1", 50000))
    token = client.get("/csrf-token").json()["csrf_token"]

    response = client.post(
        "/execute/plan",
        json={"action_type": "respond", "params": {"message": "hi"}},
        headers={"X-CSRF-Token": token, "Authorization": "Bearer test-executor-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "planned"
    assert body["plan"]["action_type"] == "respond"
    assert body["plan"]["steps"][2]["name"] == "gateway_execute"


def test_execute_run_endpoint_can_dry_run_without_gateway_side_effects(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_API_KEY", "test-executor-key")
    app = create_app()
    gateway = FakeGateway(GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"))
    app.state.permission_gateway = gateway
    client = TestClient(app, client=("127.0.0.1", 50001))
    token = client.get("/csrf-token").json()["csrf_token"]

    response = client.post(
        "/execute/run",
        json={"action_type": "respond", "params": {"message": "hi"}, "dry_run": True},
        headers={"X-CSRF-Token": token, "Authorization": "Bearer test-executor-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "planned"
    assert body["gateway"] is None
    assert gateway.seen == []
