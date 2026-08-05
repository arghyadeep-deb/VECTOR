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


def _patch_fast_ollama_sqlite(monkeypatch) -> None:
    """Keep the ollama/sqlite branches fast + deterministically "ok" so these
    loop-liveness tests are only exercising the loop check, matching the
    pattern the pre-existing tests above already use."""
    import httpx

    from core.api.routers import status as status_module

    class OkClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            class _Resp:
                status_code = 200

                def json(self):
                    return {"models": []}

            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", OkClient)
    monkeypatch.setattr(status_module, "get_memory_stats", lambda: {"episodic_memory": 0})


def test_health_endpoint_loop_running_fresh(monkeypatch, tmp_path) -> None:
    """State 1/3: a fresh heartbeat -> checks["loop"] == "ok", overall status
    stays "ok". Exercised honestly by pointing VECTOR_TEST_DATA_DIR at a temp
    dir and writing a real heartbeat file through loop_state's own
    _write_heartbeat() -- never touches the live process's heartbeat."""
    import time

    from core.api.routers import status as status_module
    from core.loop import loop_state

    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("VECTOR_API_RUN_LOOP", raising=False)
    status_module.health_cache.invalidate("status_health")
    _patch_fast_ollama_sqlite(monkeypatch)

    # Write a fresh heartbeat directly (bypasses the 2s in-process throttle).
    loop_state._hb_last_write = 0.0
    loop_state._write_heartbeat(tick_count=42, running=True, start_time="2026-08-05T00:00:00+00:00")

    response = asyncio.run(status_module.health_endpoint())

    assert response.checks["loop"] == "ok", response.checks
    assert response.status == "ok", response.model_dump()
    assert response.loop_detail is not None
    assert response.loop_detail["tick_count"] == 42
    assert response.loop_detail["age_sec"] is not None and response.loop_detail["age_sec"] < 5
    assert response.loop_detail["run_loop_opt_out"] is False

    status_module.health_cache.invalidate("status_health")


def test_health_endpoint_loop_stale_flips_status_degraded(monkeypatch, tmp_path) -> None:
    """State 2/3: a heartbeat that WAS fresh and has since gone stale ->
    checks["loop"] == "stale" and overall status flips to "degraded". This is
    the exact live-observed failure from KNOWN_ISSUES.md #0: heartbeat frozen
    at tick_count=1921 for 894s while /health kept answering ok."""
    import json
    import time

    from core.api.routers import status as status_module
    from core.loop import loop_state

    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("VECTOR_API_RUN_LOOP", raising=False)
    status_module.health_cache.invalidate("status_health")
    _patch_fast_ollama_sqlite(monkeypatch)

    # Write a heartbeat whose ts is older than _HEARTBEAT_MAX_AGE_SEC --
    # simulates exactly the live incident (frozen tick_count, old mtime).
    hb_path = loop_state._heartbeat_path()
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    stale_ts = time.time() - (loop_state._HEARTBEAT_MAX_AGE_SEC + 884)  # 894s old, matching the live incident
    hb_path.write_text(json.dumps({
        "tick_count": 1921,
        "running": True,
        "start_time": "2026-08-05T00:00:00+00:00",
        "pid": 16648,
        "ts": stale_ts,
    }), encoding="utf-8")

    response = asyncio.run(status_module.health_endpoint())

    assert response.checks["loop"] == "stale", response.checks
    assert response.status == "degraded", (
        "a stale loop heartbeat MUST flip overall status away from 'ok' -- "
        "that is the entire point of KNOWN_ISSUES.md #0's fix"
    )
    assert response.loop_detail["tick_count"] == 1921
    assert response.loop_detail["pid"] == 16648
    assert response.loop_detail["age_sec"] >= loop_state._HEARTBEAT_MAX_AGE_SEC

    status_module.health_cache.invalidate("status_health")


def test_health_endpoint_loop_not_started_does_not_flip_status(monkeypatch, tmp_path) -> None:
    """State 3/3a: no heartbeat file at all (e.g. VECTOR_API_RUN_LOOP=0,
    legitimate API-only deployment, or a loop still cold-booting) ->
    checks["loop"] == "not_started" and overall status stays "ok". Must NOT
    report unhealthy just for having no brain."""
    from core.api.routers import status as status_module

    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path))  # empty dir -- no heartbeat file
    monkeypatch.setenv("VECTOR_API_RUN_LOOP", "0")
    status_module.health_cache.invalidate("status_health")
    _patch_fast_ollama_sqlite(monkeypatch)

    response = asyncio.run(status_module.health_endpoint())

    assert response.checks["loop"] == "not_started", response.checks
    assert response.status == "ok", (
        "an explicit VECTOR_API_RUN_LOOP=0 API-only deployment must not be "
        f"reported unhealthy for having no brain: {response.model_dump()}"
    )
    assert response.loop_detail["run_loop_opt_out"] is True
    assert response.loop_detail["age_sec"] is None
    assert response.loop_detail["pid"] is None

    status_module.health_cache.invalidate("status_health")


def test_health_endpoint_loop_not_started_cold_boot_case(monkeypatch, tmp_path) -> None:
    """State 3/3b: same "not_started" outcome for the OTHER legitimate
    reason -- VECTOR_API_RUN_LOOP=1 (brain SHOULD be running) but no
    heartbeat has been written yet because the loop is still cold-booting.
    Must also not flip status, or every normal boot would false-positive."""
    from core.api.routers import status as status_module

    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path))  # empty dir -- no heartbeat file yet
    monkeypatch.setenv("VECTOR_API_RUN_LOOP", "1")
    status_module.health_cache.invalidate("status_health")
    _patch_fast_ollama_sqlite(monkeypatch)

    response = asyncio.run(status_module.health_endpoint())

    assert response.checks["loop"] == "not_started", response.checks
    assert response.status == "ok", response.model_dump()
    assert response.loop_detail["run_loop_opt_out"] is False

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
