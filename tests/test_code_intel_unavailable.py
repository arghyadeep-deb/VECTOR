"""Code intelligence when its Node backend is not built (2026-09-24 finding).

The endpoints returned HTTP 200 carrying an error dict, and every call docked 30 HP from CodeIntelAgent, so an
agent could be killed by infrastructure that was never installed. Unavailable is now a 503 and costs nothing.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from districts.coding import code_intel_agent as cia


@pytest.fixture()
def unbuilt(monkeypatch, tmp_path):
    monkeypatch.setattr(cia, "_DIST", tmp_path / "dist" / "index.js")  # does not exist


def test_mcp_call_marks_missing_build_as_unavailable(unbuilt):
    r = cia._mcp_call("vc_search", {"query": "x"})
    assert r["unavailable"] is True and "not built" in r["error"]


def test_unavailable_costs_the_agent_no_hp(unbuilt):
    agent = cia.CodeIntelAgent()
    before = agent.health_points
    out = asyncio.run(agent.run({"type": "vc_search", "params": {"query": "governor"}}))
    assert out["status"] == "unavailable"
    assert agent.health_points == before


def test_endpoints_answer_503_not_200(unbuilt):
    from core.api.routers import code_intel

    code_intel._intel_agent = None
    app = FastAPI()
    app.include_router(code_intel.router)
    r = TestClient(app).post("/code-intel/search", json={"query": "governor"})
    assert r.status_code == 503, r.text
    assert "not built" in r.json()["detail"]


def test_genuine_errors_still_cost_hp(monkeypatch):
    monkeypatch.setattr(cia, "_mcp_call", lambda *a, **k: {"error": "boom"})
    agent = cia.CodeIntelAgent()
    before = agent.health_points
    out = asyncio.run(agent.run({"type": "vc_search", "params": {"query": "x"}}))
    assert out["status"] == "error" and agent.health_points < before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
