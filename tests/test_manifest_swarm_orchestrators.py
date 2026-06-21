"""Task A.2 (plans/governor-wiring-and-ambient-perception.md): coding/,
finance/, and research/ each have a self-loading orchestrator (CodingSwarm,
FinanceSwarm, ResearchSwarm) using the exact same pattern already registered
for ops/ (OpsSwarm) and qa/ (QASwarm) — see districts/<d>/agent.py's
PYTHON_AGENTS list + _load_agents(). None of the three were in
config/agent_manifest.yaml, so governor.dispatch() could never reach the 9
(coding) / 7 (finance) / 8 (research) specialist agents these orchestrators
self-load and internally route to by task-type keyword match — those
specialists only ever showed up in docs/manifest_gap.md as individually
"unregistered", which would have been the wrong fix (mirroring them in one
by one, rather than registering the front door they already have).

These tests prove the real wiring (manifest -> registry -> governor
capability-select -> swarm.run), not just the YAML edit. The swarm's own
internal dispatch (its `run()` actually invoking a sub-agent's real,
possibly LLM-backed pipeline) is the swarm's own concern, already covered
by each agent.py's own `if __name__ == "__main__"` smoke block — this test
monkeypatches `run` on the resolved swarm instance to keep these tests fast
and deterministic while still proving governor reaches the right class.
"""
import asyncio

import pytest

from core.city.declarative_manifest import ManifestLoader
from core.city.agent_registry import get_registry
from core.city.governor import Governor


def _dispatch_reaches_swarm(district: str, swarm_class, task_type: str) -> None:
    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        agents = [a for a in loader.load() if a["district"] == district]
        registered = loader.register_all(agents, reg)
        assert registered >= 1

        district_agents = reg.get_by_district(district)
        swarm_instances = [a for a in district_agents if isinstance(a, swarm_class)]
        assert swarm_instances, (
            f"{swarm_class.__name__} must be manifest-registered under '{district}'"
        )
        swarm = swarm_instances[0]

        called = {}

        async def _fake_run(task):
            called["ran"] = True
            return {"status": "ok"}

        swarm.run = _fake_run

        result = asyncio.run(Governor().dispatch({"type": task_type, "district": district, "params": {}}))
        assert called.get("ran") is True, (
            f"governor.dispatch(type={task_type!r}) did not reach {swarm_class.__name__}: {result}"
        )
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)


def test_coding_swarm_reachable_via_manifest():
    from districts.coding.agent import CodingSwarm
    _dispatch_reaches_swarm("coding", CodingSwarm, "code_conductor")


def test_finance_swarm_reachable_via_manifest():
    from districts.finance.agent import FinanceSwarm
    _dispatch_reaches_swarm("finance", FinanceSwarm, "fpa_analysis")


def test_research_swarm_reachable_via_manifest():
    from districts.research.agent import ResearchSwarm
    _dispatch_reaches_swarm("research", ResearchSwarm, "deep_research")


if __name__ == "__main__":
    test_coding_swarm_reachable_via_manifest()
    test_finance_swarm_reachable_via_manifest()
    test_research_swarm_reachable_via_manifest()
    print("[OK] test_manifest_swarm_orchestrators")
