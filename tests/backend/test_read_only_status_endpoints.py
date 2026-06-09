from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
