"""A2A is available in EVERY district: bootstrap the real manifest and ping every agent over the governed bus.

This is the check behind "agent-to-agent communication must exist across all of VECTOR": if a district is added to the manifest and
its agents cannot be reached over the bus, this fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import core.city.a2a_bus as bus_mod
import core.city.agent_registry as registry_mod
from core.city.a2a_bus import A2ABus
from core.city.agent_registry import AgentRegistry
from core.city.declarative_manifest import ManifestLoader


@pytest.fixture(scope="module")
def city():
    import asyncio
    from run_vector import bootstrap_agents

    original = registry_mod._registry_singleton
    reg = AgentRegistry()
    registry_mod._registry_singleton = reg
    old_bus, bus_mod._BUS = bus_mod._BUS, A2ABus(registry=reg)
    try:
        bootstrap_agents()
        report = asyncio.run(bus_mod._BUS.ping_all())
        yield {"reg": reg, "bus": bus_mod._BUS, "report": report, "manifest": ManifestLoader().load()}
    finally:
        registry_mod._registry_singleton = original
        bus_mod._BUS = old_bus


def test_every_agent_in_every_district_answers_a_ping_over_the_bus(city):
    r = city["report"]
    assert r["agents"] >= 100, "the bootstrapped city should be the full manifest, not a stub"
    assert r["failed"] == [], r["failed"][:5]
    assert r["answered"] == r["agents"] == city["reg"].total()


def test_every_manifest_district_is_reachable_and_declares_capabilities(city):
    manifest_districts = {e["district"] for e in city["manifest"] if e.get("district")}
    reached = set(city["report"]["districts"])
    assert manifest_districts <= reached, f"manifest districts with no agent on the bus: {sorted(manifest_districts - reached)}"
    assert city["report"]["districts_unreachable"] == []
    assert city["report"]["districts_without_capabilities"] == [], "every district must advertise at least one capability to peers"


def test_the_directory_matches_the_registry(city):
    directory = city["bus"].directory()
    assert sum(len(v) for v in directory.values()) == city["reg"].total()
    assert all(a["capabilities"] is not None and a["id"] for v in directory.values() for a in v)
