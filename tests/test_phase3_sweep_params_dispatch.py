"""Regression test for 3 real bugs found by the Phase 3 full-repo mechanical
sweep (2026-09-30) -- the same params-vs-task dispatch AST scan from the
31-file params-bug hunt this session, re-run across the WHOLE repo instead of
just districts/core. Only 6 new candidates surfaced repo-wide (2 already-known
false positives: core/loop/workflow_runner.py, core/swarm/generic_swarm.py;
1 handed to Codex's half: vectorcode/src/tools/mcp_tool.py); these 3 were the
genuine true positives in Claude's assigned territory.

Same bug shape as every other fix in this series: real governor dispatch is
{"type": ..., "params": {...}}, and each of these agents' run() read its
arguments straight off `task` instead of `task["params"]`, so a real dispatch
always fell back to hardcoded defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.communications.email_intelligence import EmailIntelligence
from districts.design.image_prompt_engineer import ImagePromptEngineer
from districts.design.ux_researcher import UXResearcher


@pytest.mark.asyncio
async def test_email_intelligence_reads_limit_from_nested_params():
    agent = EmailIntelligence()
    captured = {}

    def fake_fetch(max_results):
        captured["limit"] = max_results
        return []

    agent.fetch_recent_threads = fake_fetch
    await agent.run({"type": "brief", "params": {"limit": 3}})
    assert captured == {"limit": 3}


@pytest.mark.asyncio
async def test_email_intelligence_flat_legacy_shape_still_works():
    agent = EmailIntelligence()
    captured = {}

    def fake_fetch(max_results):
        captured["limit"] = max_results
        return []

    agent.fetch_recent_threads = fake_fetch
    await agent.run({"type": "brief", "limit": 7})
    assert captured == {"limit": 7}


@pytest.mark.asyncio
async def test_image_prompt_engineer_reads_count_from_nested_params():
    agent = ImagePromptEngineer()
    result = await agent.run({"type": "variations", "params": {"subject": "a red fox", "count": 2}})
    assert result["status"] == "ok"
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_ux_researcher_reads_name_from_nested_params():
    agent = UXResearcher()
    result = await agent.run({"type": "persona", "params": {"name": "Priya", "role": "Data Scientist"}})
    assert result["status"] == "ok"
    assert result["persona"]["name"] == "Priya"
    assert result["persona"]["role"] == "Data Scientist"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
