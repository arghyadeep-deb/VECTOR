"""Regression coverage for the self-development Design specialist package."""

from __future__ import annotations

import asyncio

from core.city.declarative_manifest import ManifestLoader
from core.config import CONFIG
from core.city.governor import DISTRICT_TASK_MAP
from districts.design.design_specialists import SPECIALIST_CLASSES


def test_every_design_specialist_builds_an_evidence_report() -> None:
    """Each persona must produce a real, traceable result without an LLM claim."""
    for agent_cls in SPECIALIST_CLASSES:
        agent = agent_cls()
        result = asyncio.run(agent.run({"type": agent.capabilities[0], "evidence": {}}))

        assert result["status"] == "ok"
        assert result["report"]["status"] == "needs_human"
        assert result["report"]["missing_evidence"]
        assert agent.health_points > 500


def test_specialists_are_manifest_registered_and_green_routed() -> None:
    """The manifest, policy vocabulary, and governor agree on every task type."""
    manifest = ManifestLoader().load()
    entries = {entry["class"]: entry for entry in manifest}
    specialist_entries = []

    for agent_cls in SPECIALIST_CLASSES:
        agent = agent_cls()
        class_path = f"{agent_cls.__module__}.{agent_cls.__name__}"
        entry = entries[class_path]
        specialist_entries.append(entry)

        assert entry["district"] == "design"
        assert entry["capabilities"] == agent.capabilities
        for capability in agent.capabilities:
            assert capability in CONFIG["permission"]["green"]
            assert DISTRICT_TASK_MAP[capability] == "design"

    instances = ManifestLoader().instantiate_all(specialist_entries)
    assert {type(instance) for instance in instances} == set(SPECIALIST_CLASSES)


if __name__ == "__main__":
    test_every_design_specialist_builds_an_evidence_report()
    test_specialists_are_manifest_registered_and_green_routed()
    print("design specialist tests OK")
