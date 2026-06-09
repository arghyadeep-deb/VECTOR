from __future__ import annotations

from fastapi.testclient import TestClient


def test_world_snapshot_builder_has_core_sections() -> None:
    from core.runtime.world_model import build_world_snapshot

    snapshot = build_world_snapshot(open_panels=["features", "corepanel"]).to_dict()

    assert snapshot["status"] in {"ok", "attention", "unready"}
    for key in (
        "runtime",
        "readiness",
        "agents",
        "memory",
        "safety",
        "sensing",
        "voice",
        "tasks",
        "frontend",
    ):
        assert key in snapshot

    assert snapshot["frontend"]["open_panels"] == ["features", "corepanel"]
    assert snapshot["readiness"]["required_failed"] == 0


def test_world_snapshot_endpoint_returns_shared_state() -> None:
    from core.api.app import create_app

    client = TestClient(create_app(), client=("127.0.0.1", 50000))
    response = client.get("/world/snapshot?panels=features,pccontrol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["frontend"]["open_panels"] == ["features", "pccontrol"]
    assert "uptime_seconds" in payload["runtime"]
    assert "pending_count" in payload["safety"]
