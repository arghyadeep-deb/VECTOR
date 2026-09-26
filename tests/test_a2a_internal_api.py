"""/a2a/internal/*: the HTTP window onto the governed bus."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.city.a2a_bus as bus_mod
import core.city.agent_registry as registry_mod
from core.api.routers import a2a as a2a_router
from core.city.a2a_bus import A2ABus
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry


class Echo(AgentBase):
    async def run(self, task):
        return {"status": "ok", "agent": self.name, "echo": task.get("params")}


@pytest.fixture
def client(isolated_vector_db):
    original = registry_mod._registry_singleton
    reg = AgentRegistry()
    registry_mod._registry_singleton = reg
    old_bus, bus_mod._BUS = bus_mod._BUS, A2ABus(registry=reg)
    for name, district, caps in (("Alpha", "da", ["search"]), ("Beta", "db", [])):
        a = Echo(agent_id=f"id-{name}", name=name, district=district)
        a.capabilities = caps
        reg.register(a)
    app = FastAPI()
    app.include_router(a2a_router.router)
    yield TestClient(app)
    registry_mod._registry_singleton = original
    bus_mod._BUS = old_bus


def test_directory_lists_agents_by_district(client):
    body = client.get("/a2a/internal/directory").json()
    assert body["district_count"] == 2 and body["agent_count"] == 2
    assert body["districts"]["da"][0]["name"] == "Alpha"


def test_ping_and_ask_and_audit(client):
    ping = client.post("/a2a/internal/ask", json={"task_type": "ping", "to": "Beta"}).json()
    assert ping["ok"] and ping["result"]["name"] == "Beta"
    ask = client.post("/a2a/internal/ask", json={"task_type": "respond", "params": {"q": 1}, "to": "Alpha", "sender": "Beta"}).json()
    assert ask["delivered"] and ask["result"]["agent"] == "Alpha" and ask["responder"] == "Alpha"
    recent = client.get("/a2a/internal/recent?limit=5").json()
    assert [m["task_type"] for m in recent["messages"]][:2] == ["respond", "ping"]
    assert recent["messages"][0]["from"] == "Beta" and recent["stats"]["delivered"] >= 2
    convo = client.get(f"/a2a/internal/conversation/{ask['correlation_id']}").json()
    assert len(convo["messages"]) == 1


def test_red_requests_are_refused_over_http_too(client):
    r = client.post("/a2a/internal/ask", json={"task_type": "delete_files", "to": "Alpha"}).json()
    assert r["status"] == "requires_approval" and not r["delivered"]


def test_unknown_target_is_a_clean_unavailable(client):
    r = client.post("/a2a/internal/ask", json={"task_type": "respond", "to": "Ghost"}).json()
    assert r["status"] == "unavailable" and r["refused"]


def test_ping_all_endpoint(client):
    body = client.get("/a2a/internal/ping-all").json()
    assert body["agents"] == 2 and body["answered"] == 2 and body["failed"] == []


def test_work_board_and_agent_experience_endpoints(client):
    board = client.get("/a2a/internal/work-board").json()
    assert board["agents"] == 2 and "gym_enabled" in board and board["drills"]
    agent = client.get("/a2a/internal/agent/Alpha").json()
    assert agent["found"] and agent["stats"]["level"] == 0 and agent["playbook"] == []
    assert client.get("/a2a/internal/agent/Nobody").json() == {"found": False, "name": "Nobody"}
