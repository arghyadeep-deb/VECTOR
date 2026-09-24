"""Agent HP is defined as 0-1000 everywhere (AgentBase clamps every award/deduction to that range), but
CodingSwarm started at 1500 and OpsSwarm at 1200, so the HUD showed HP values above the documented ceiling."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_HP = 1000


def test_no_district_agent_hard_codes_an_initial_hp_above_the_cap():
    offenders = []
    for path in (ROOT / "districts").rglob("*.py"):
        if "vector_finagent" in path.parts or "alpha_zoo" in path.parts:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            m = re.match(r"\s*self\.health_points\s*=\s*(\d+)\b", line)
            if m and int(m.group(1)) > MAX_HP:
                offenders.append(f"{path.relative_to(ROOT)}:{n} = {m.group(1)}")
    assert offenders == []


def test_agentbase_clamps_awards_to_the_cap():
    from core.city.agent_base import AgentBase

    class _A(AgentBase):
        async def run(self, task):
            return {}

    a = _A(agent_id="hp-cap-probe", name="probe", district="qa")
    a.health_points = 990
    a.award_points(500, "test")
    assert a.health_points <= MAX_HP


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
