"""Regression for the 2026-10-07 core/brain audit.

core/loop/autonomous_loop.py's RED-tier gate calls
``red_team.attack_plan({...structured action dict...})`` and then reads
``review.get("verdict", "APPROVED")`` to decide whether to block/modify a
RED-tier action. But RedTeamAgent.attack_plan() never populated a "verdict"
key at all (it only returned plan/vulnerabilities/timestamp), so the gate
silently defaulted to APPROVED on every single call regardless of what the
adversarial review found -- a phantom safety gate. Worse, the real call site
passes a dict, and the old code did ``plan[:50]`` in its log line, which
raises on a dict, so the method failed internally and returned
``{"error": ...}`` (still with no "verdict" key -- APPROVED again).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brain.red_team_agent import RedTeamAgent, _parse_verdict


def test_parse_verdict_extracts_each_known_token():
    assert _parse_verdict("Severity critical. Overall: BLOCKED") == "BLOCKED"
    assert _parse_verdict("Minor issues. Verdict: modify") == "MODIFY"
    assert _parse_verdict("No issues found. APPROVED") == "APPROVED"


def test_parse_verdict_fails_closed_on_ambiguous_text():
    assert _parse_verdict("") == "BLOCKED"
    assert _parse_verdict("the model rambled with no clear conclusion") == "BLOCKED"


def test_attack_plan_accepts_a_structured_dict_plan_like_the_real_caller():
    """core/loop/autonomous_loop.py passes a dict, not a string, as `plan`."""
    agent = RedTeamAgent()
    agent._call = AsyncMock(return_value="Found one critical issue. Verdict: BLOCKED")

    result = asyncio.run(agent.attack_plan({
        "action_type": "launch_app", "params": {"package": "evil.apk"},
        "goal_ids": [], "score": 0.9,
    }))

    assert "error" not in result, f"attack_plan crashed on a dict plan: {result}"
    assert result["verdict"] == "BLOCKED"


def test_attack_plan_returns_the_verdict_key_the_gateway_depends_on():
    agent = RedTeamAgent()
    agent._call = AsyncMock(return_value="Looks safe overall. Verdict: APPROVED")

    result = asyncio.run(agent.attack_plan("deploy new agent", "no alerts"))

    assert "verdict" in result
    assert result["verdict"] == "APPROVED"


if __name__ == "__main__":
    import subprocess

    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
    print("✅ test_core_brain_red_team_verdict OK" if result.returncode == 0 else "❌ FAILED")
