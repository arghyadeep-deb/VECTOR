"""Regression test for a real bug found during the 2026-06-21 manifest-gap
audit: districts/qa/doc_generator.py and districts/qa/technical_writer.py
each hardcode `district="documentation"` in their own __init__ (a real,
separate bonus district per the project's phase_status.md history — "VECTOR
documents itself" — that never got its own districts/documentation/
folder). core/api/routers/documentation.py's 4 routes (api_reference,
generate_docs, generate_changelog, weekly_summary) dispatch via
governor.dispatch() with no explicit "district" key, relying on
route_task()'s keyword match against DISTRICT_TASK_MAP — which had ZERO
"documentation" entries, so those 4 task types fell through to the LLM
classifier, whose candidate list (`set(DISTRICT_TASK_MAP.values())`) didn't
even include "documentation" as an option. Registering the two agents in
the manifest under any OTHER district key (e.g. "qa", where their files
physically live) would have been silently inert too, since
AgentRegistry.get_by_district() filters on the agent INSTANCE's real
.district attribute, not the manifest YAML's nesting key.

Fixed both ends: config/agent_manifest.yaml now has a `documentation:`
section (matching the agents' real self-declared district) and
core/city/governor.py's DISTRICT_TASK_MAP has the 4 missing keys.
"""
import asyncio

from core.city.governor import Governor
from core.city.declarative_manifest import ManifestLoader
from core.city.agent_registry import get_registry


def test_documentation_task_types_route_to_documentation_district():
    gov = Governor()
    for task_type in ["api_reference", "generate_docs", "generate_changelog", "weekly_summary"]:
        assert gov.route_task(task_type) == "documentation", (
            f"route_task({task_type!r}) should resolve to 'documentation', "
            f"got {gov.route_task(task_type)!r}"
        )


def test_doc_generator_and_technical_writer_reachable_via_manifest():
    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        agents = [a for a in loader.load() if a["district"] == "documentation"]
        assert len(agents) == 2
        registered = loader.register_all(agents, reg)
        assert registered == 2

        doc_agents = reg.get_by_district("documentation")
        names = {a.name for a in doc_agents}
        assert "DocGenerator" in names
        assert "TechnicalWriter" in names

        called = {}
        for a in doc_agents:
            orig_run = a.run

            async def _fake_run(task, _name=a.name):
                called["agent"] = _name
                return {"status": "ok"}

            a.run = _fake_run

        result = asyncio.run(Governor().dispatch({"type": "weekly_summary", "params": {}}))
        assert called.get("agent") in names, f"dispatch did not reach a documentation agent: {result}"
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)


if __name__ == "__main__":
    test_documentation_task_types_route_to_documentation_district()
    test_doc_generator_and_technical_writer_reachable_via_manifest()
    print("[OK] test_documentation_district_routing")
