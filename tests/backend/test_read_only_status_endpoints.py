from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """These tests assert the documented no-key/localhost auth mode; the owner's
    real .env loads VECTOR_API_KEY into the test process — remove it here."""
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)


READ_ONLY_ENDPOINTS = (
    "/health/status",
    "/patterns/habits",
    "/projects/list",
    "/projects/deadline",
    "/ops/slo-check",
    "/analytics/pipeline-health",
    "/governance/autopilot/status",
    "/voice/status",
    "/skills/map",
    "/relationships/contacts",
    "/calls/contacts",
)


@pytest.fixture()
def local_client() -> TestClient:
    from core.api.app import create_app

    return TestClient(create_app(), client=("127.0.0.1", 50000))


def test_read_only_status_endpoints_do_not_dispatch_governor(monkeypatch, local_client: TestClient) -> None:
    async def fail_dispatch(*_args, **_kwargs):
        raise AssertionError("read-only status/list endpoint dispatched a governor task")

    monkeypatch.setattr("core.city.governor.GovernorCouncil.dispatch", fail_dispatch)
    monkeypatch.setattr("core.city.governor.Governor.dispatch", fail_dispatch)

    for path in READ_ONLY_ENDPOINTS:
        response = local_client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text[:300]}"
        payload = response.json()
        assert payload.get("status") == "ok", f"{path} payload={payload}"


def test_protected_endpoints_allow_localhost_without_api_key(local_client: TestClient) -> None:
    response = local_client.get("/health/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ollama_model_matching_accepts_latest_tags() -> None:
    from core.api.routers.status import _ollama_model_loaded

    loaded = ["vector-focus:latest", "vector-reasoning:latest", "gemma4:31b"]

    assert _ollama_model_loaded("vector-focus", loaded)
    assert _ollama_model_loaded("vector-reasoning", loaded)
    assert _ollama_model_loaded("vector-focus:latest", loaded)
    assert not _ollama_model_loaded("vector-missing", loaded)


def test_health_endpoint_distinguishes_timeout_from_generic_error(monkeypatch) -> None:
    """Regression test for the /health false-negative: an httpx timeout has an
    empty str(e) (e.g. httpx.ReadTimeout()), which used to render as the bare,
    indistinguishable message "error: ". The watchdog (and a human) must be
    able to tell "Ollama timed out" apart from "Ollama is actually down"."""
    import httpx

    from core.api.routers import status as status_module

    status_module.health_cache.invalidate("status_health")

    class TimingOutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            # httpx timeout exceptions render as an empty string via str(e).
            raise httpx.ReadTimeout("")

    monkeypatch.setattr(httpx, "AsyncClient", TimingOutClient)
    # Keep the SQLite branch fast/deterministic — this test is only about the
    # Ollama message, not the DB threading behaviour (covered separately).
    monkeypatch.setattr(status_module, "get_memory_stats", lambda: {"episodic_memory": 0})

    response = asyncio.run(status_module.health_endpoint())

    assert str(response.status) == "degraded"
    ollama_check = response.checks["ollama"]
    assert ollama_check.startswith("error: ")
    assert ollama_check != "error: ", "false negative reproduced: empty str(e) collapsed the message"
    assert "ReadTimeout" in ollama_check, f"exception type must be identifiable, got: {ollama_check!r}"

    status_module.health_cache.invalidate("status_health")


def test_health_endpoint_caches_result_within_ttl(monkeypatch) -> None:
    """/health must be cached (health_cache) so repeated watchdog polling
    doesn't re-run the Ollama probe + SQLite stats query on every hit."""
    from core.api.routers import status as status_module

    status_module.health_cache.invalidate("status_health")

    call_count = {"n": 0}

    class CountingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            call_count["n"] += 1

            class _Resp:
                status_code = 200

                def json(self):
                    return {"models": []}

            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", CountingClient)
    monkeypatch.setattr(status_module, "get_memory_stats", lambda: {"episodic_memory": 0})

    first = asyncio.run(status_module.health_endpoint())
    second = asyncio.run(status_module.health_endpoint())

    assert call_count["n"] == 1, "second call within TTL must be served from health_cache, not re-probe Ollama"
    assert first is second

    status_module.health_cache.invalidate("status_health")


def test_health_endpoint_runs_memory_stats_off_the_event_loop(monkeypatch) -> None:
    """get_memory_stats() must be dispatched via asyncio.to_thread so a slow,
    lock-holding SQLite query cannot block the whole event loop (which would
    also starve the concurrent Ollama probe in the same handler)."""
    from core.api.routers import status as status_module

    status_module.health_cache.invalidate("status_health")

    calls: list[object] = []

    real_to_thread = asyncio.to_thread

    async def spying_to_thread(func, *args, **kwargs):
        calls.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(status_module.asyncio, "to_thread", spying_to_thread)

    def fake_get_memory_stats():
        return {"episodic_memory": 0}

    monkeypatch.setattr(status_module, "get_memory_stats", fake_get_memory_stats)

    import httpx

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise OSError("network unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", FailingClient)

    asyncio.run(status_module.health_endpoint())

    # `calls` holds the CALLABLES handed to asyncio.to_thread, not their names,
    # so compare against the patched function object itself. (The original
    # assertion checked `"get_memory_stats" in calls` — a string against a list
    # of function objects, which can never be true and so would have failed even
    # with a correct implementation.)
    assert fake_get_memory_stats in calls, (
        "get_memory_stats must be dispatched via asyncio.to_thread, not called "
        f"inline on the event loop; to_thread received: {calls}"
    )

    status_module.health_cache.invalidate("status_health")
