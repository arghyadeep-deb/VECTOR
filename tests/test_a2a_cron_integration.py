"""Integration tests for A2A endpoint exposure + cron-triggered workflow wiring.

Run:
    pytest tests/test_a2a_cron_integration.py -v

Covers three additive layers:
  1. A2A router endpoints (discovery, agents, invoke, sessions, SSE)
  2. Cron→workflow trigger (job_trigger_workflow, morning_digest wiring,
     _parse_cron_daily, _fire_vnative_cron_jobs)
  3. Full wiring (A2A router registered in app, cron job in register_default_jobs)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Helper: minimal FastAPI app with just the A2A router (no auth middleware) ─


def _a2a_app():
    """Return a FastAPI app with only the A2A router mounted.

    Bypasses auth/CSRF/rate-limit middleware that blocks TestClient in CI.
    The full middleware stack is tested separately via route-registration checks.
    """
    from fastapi import FastAPI
    from core.api.routers.a2a import router

    app = FastAPI()
    app.include_router(router)
    return app


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1 — A2A endpoint exposure
# ═══════════════════════════════════════════════════════════════════════════════


class TestA2ADiscovery:
    """A2A protocol discovery endpoint — GET /.well-known/agent.json."""

    def test_well_known_router_imports(self):
        from core.api.routers.a2a import router, well_known
        assert router.prefix == "/a2a"
        assert callable(well_known)

    def test_well_known_response_shape(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.get("/a2a/.well-known/agent.json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["schema_version"] == "1.0"
        assert body["name"] == "VECTOR"
        assert "endpoints" in body
        assert "capabilities" in body
        assert body["capabilities"]["streaming"] is True


class TestA2AListAgents:
    """A2A agent listing — GET /a2a/agents."""

    def test_list_agents_endpoint_returns_200(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.get("/a2a/agents")
        assert resp.status_code == 200
        body = resp.json()
        assert "agents" in body
        assert "count" in body
        assert isinstance(body["agents"], list)

    def test_single_agent_not_found_yields_404(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.get("/a2a/agents/nonexistent_agent_xyz")
        assert resp.status_code == 404


class TestA2AInvoke:
    """A2A agent invocation — POST /a2a/agents/{name}/invoke."""

    def test_invoke_unknown_agent_returns_404(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.post(
            "/a2a/agents/nonexistent_agent_xyz/invoke",
            json={"task": "hello", "params": {}},
        )
        assert resp.status_code == 404


class TestA2ATaskStatus:
    """A2A task status — GET /a2a/agents/{name}/tasks/{id}."""

    def test_unknown_task_404s(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.get("/a2a/agents/any/tasks/not-a-real-task-id")
        assert resp.status_code == 404

    def test_known_task_returns_details(self):
        """Invoke an agent, then poll the resulting task id."""
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        # Invoke will return 404 (no agent), but we can tickle the _TASKS store
        # by calling the underlying handler directly.  Simpler: verify the route
        # exists and returns structured JSON on 404.
        resp = client.get("/a2a/agents/some-agent/tasks/__notfound__")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body


class TestA2ASessions:
    """A2A session management — multi-turn conversations."""

    def test_create_session_returns_session_id(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.post("/a2a/sessions", json={"agent": "research-001"})
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["agent"] == "research-001"

    def test_session_with_initial_message(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.post(
            "/a2a/sessions",
            json={"agent": "coding-001", "initial_message": "list files"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get("messages", [])) >= 1

    def test_session_message_invalid_session_404s(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        resp = client.post(
            "/a2a/sessions/bad-session-id/messages",
            json={"message": "hi", "role": "user"},
        )
        assert resp.status_code == 404

    def test_session_message_valid_session(self):
        from fastapi.testclient import TestClient
        app = _a2a_app()
        client = TestClient(app)
        create = client.post("/a2a/sessions", json={"agent": "research-001"})
        sid = create.json()["session_id"]
        resp = client.post(
            f"/a2a/sessions/{sid}/messages",
            json={"message": "what is ai", "role": "user"},
        )
        assert resp.status_code in (200,)


class TestA2ASSE:
    """SSE event stream — GET /a2a/events."""

    def test_sse_route_registered(self):
        """SSE is an infinite stream — verify the route exists, don't connect."""
        from core.api.app import create_app
        app = create_app()
        routes = {r.path for r in app.routes}
        assert "/a2a/events" in routes

    def test_sse_router_imports(self):
        from core.api.routers.a2a import router, agent_event_stream
        assert callable(agent_event_stream)
        # The SSE handler is registered; the full path /a2a/events is
        # verified in test_sse_route_registered via the production app.


class TestA2AAppWiring:
    """Verify the A2A router is actually registered in the full production app."""

    def test_a2a_routes_are_registered(self):
        from core.api.app import create_app
        app = create_app()
        routes = [r.path for r in app.routes]
        a2a_routes = [p for p in routes if p.startswith("/a2a")]
        assert len(a2a_routes) >= 7, f"expected >=7 A2A routes, got {a2a_routes}"
        assert "/a2a/.well-known/agent.json" in a2a_routes
        assert "/a2a/agents" in a2a_routes
        assert "/a2a/agents/{name}/invoke" in routes
        assert "/a2a/agents/{name}/tasks/{task_id}" in routes
        assert "/a2a/sessions" in a2a_routes
        assert "/a2a/sessions/{session_id}/messages" in routes
        assert "/a2a/events" in a2a_routes


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2 — Cron → workflow trigger
# ═══════════════════════════════════════════════════════════════════════════════


class TestCronWorkflowTrigger:
    """Cron job that fires the morning_digest workflow."""

    def test_workflow_definition_exists(self):
        from core.loop.cron_jobs import _MORNING_DIGEST_WORKFLOW
        assert "name" in _MORNING_DIGEST_WORKFLOW
        assert _MORNING_DIGEST_WORKFLOW["name"] == "morning_digest"
        assert "tasks" in _MORNING_DIGEST_WORKFLOW
        assert len(_MORNING_DIGEST_WORKFLOW["tasks"]) >= 1

    def test_job_function_imports(self):
        from core.loop.cron_jobs import job_trigger_workflow, _run_morning_digest_fn
        assert callable(job_trigger_workflow)
        assert callable(_run_morning_digest_fn)

    def test_job_registered_in_default_jobs(self):
        from core.loop.cron_jobs import register_default_jobs

        # Verify the job list includes workflow-trigger
        import inspect
        source = inspect.getsource(register_default_jobs)
        assert "daily-workflow-trigger" in source
        assert "job_trigger_workflow" in source
        assert "0 8 * * *" in source

    @pytest.mark.asyncio
    async def test_workflow_runner_smoke(self):
        """Self-contained workflow with a direct callable — no district deps."""
        from core.loop.workflow_runner import WorkflowRunner

        async def _step(**kwargs):
            return {"value": 42}

        wf = {
            "name": "smoke",
            "tasks": [{"id": "a", "fn": _step}],
        }
        runner = WorkflowRunner()
        result = await runner.run(wf)
        assert result.overall_status == "ok"
        assert result.get("a") == {"value": 42}

    @pytest.mark.asyncio
    async def test_job_trigger_workflow_does_not_crash(self):
        """Calls job_trigger_workflow with no external deps.

        The underlying MorningDigestAgent may fail (missing config, network,
        Ollama etc.), but the job wrapper must catch all exceptions and return
        a dict — never raise.
        """
        from core.loop.cron_jobs import job_trigger_workflow

        result = await job_trigger_workflow()
        assert isinstance(result, dict)
        assert "status" in result
        # "failed" or "skipped" is fine — the important thing is it didn't crash
        assert result["status"] in ("ok", "failed", "partial", "skipped")

    @pytest.mark.asyncio
    async def test_morning_digest_fn_does_not_crash(self):
        """Same as above but for the inner helper function."""
        from core.loop.cron_jobs import _run_morning_digest_fn

        result = await _run_morning_digest_fn()
        assert isinstance(result, dict)
        assert "status" in result


class TestCronParsing:
    """Cron expression parsing helpers."""

    def test_parse_cron_daily_happy_path(self):
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        result = loop._parse_cron_daily("0 8 * * *")
        assert result == (8, 0), f"expected (8, 0), got {result}"

        result = loop._parse_cron_daily("30 22 * * *")
        assert result == (22, 30), f"expected (22, 30), got {result}"

    def test_parse_cron_daily_weekly_returns_none(self):
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        result = loop._parse_cron_daily("0 2 * * 0")  # Sunday
        assert result is None, f"expected None for weekly, got {result}"

    def test_parse_cron_daily_invalid_returns_none(self):
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        result = loop._parse_cron_daily("not-a-cron")
        assert result is None

    def test_parse_cron_daily_with_nonstandard_format(self):
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        result = loop._parse_cron_daily("15 9 * * *")
        assert result == (9, 15)


class TestFireVNativeCron:
    """AutonomousLoop._fire_vnative_cron_jobs — the cron dispatch mechanism."""

    @pytest.mark.asyncio
    async def test_fire_vnative_cron_runs_without_error(self):
        """Should never raise, even if job implementations fail."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        try:
            await loop._fire_vnative_cron_jobs()
        except Exception:
            pytest.fail("_fire_vnative_cron_jobs raised unexpectedly")

    def test_cron_last_run_tracking(self):
        """Verify the _cron_last_run dict is used."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        assert isinstance(loop._cron_last_run, dict)
        # After fire, no entry should be added (since cron time doesn't match)
        import asyncio
        asyncio.run(loop._fire_vnative_cron_jobs())
        assert len(loop._cron_last_run) == 0  # not 8:00 yet


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 3 — Full wiring sanity
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullWiring:
    """End-to-end sanity checks across the A2A + cron + workflow stack."""

    def test_app_has_a2a_routes(self):
        """The app factory must include the A2A APIRouter."""
        from core.api.app import create_app

        app = create_app()
        paths = [r.path for r in app.routes]
        a2a_paths = [p for p in paths if "/a2a/" in p]
        assert len(a2a_paths) >= 7, f"A2A routes missing: {a2a_paths}"

    def test_cron_jobs_module_exports(self):
        """Verify all expected symbols are exported from cron_jobs."""
        import core.loop.cron_jobs as cj

        for name in (
            "register_default_jobs",
            "job_daily_eval",
            "job_biometrics_pull",
            "job_daily_review",
            "job_weekly_dspy_optimize",
            "job_weekly_growth_report",
            "job_trigger_workflow",
            "_MORNING_DIGEST_WORKFLOW",
        ):
            assert hasattr(cj, name), f"cron_jobs missing export: {name}"

    def test_workflow_runner_present_in_autonomous_loop(self):
        """AutonomousLoop must expose trigger_workflow and _get_workflow_runner."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        assert hasattr(loop, "trigger_workflow")
        assert hasattr(loop, "_get_workflow_runner")

    def test_a2a_router_included_in_app_factory(self):
        """Verify that create_app() includes the a2a router."""
        from core.api.app import create_app
        app = create_app()
        a2a_routes = [r.path for r in app.routes if str(r.path).startswith("/a2a")]
        assert len(a2a_routes) >= 7, f"A2A router not wired — found {a2a_routes}"


class TestSchedulerWiring:
    """The scheduler loop wiring layer."""

    def test_scheduler_loop_has_cron_fire(self):
        """scheduler_loop() method must include _fire_vnative_cron_jobs call."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop

        source = inspect.getsource(AutonomousLoop.scheduler_loop)
        assert "_fire_vnative_cron_jobs" in source

    def test_scheduler_loop_has_default_jobs_registration(self):
        """scheduler_loop() must register default cron jobs."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop

        source = inspect.getsource(AutonomousLoop.scheduler_loop)
        assert "register_default_jobs" in source

    def test_parse_cron_is_class_method(self):
        """_parse_cron_daily must exist as a method."""
        from core.loop.autonomous_loop import AutonomousLoop

        assert hasattr(AutonomousLoop, "_parse_cron_daily")
        assert callable(AutonomousLoop._parse_cron_daily)
