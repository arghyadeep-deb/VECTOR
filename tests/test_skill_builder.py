"""Focused tests for SkillBuilder (districts/personal_growth/skill_builder.py)
and the PatternLearner.stable_patterns() accessor it consumes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.city.agent_base import AgentBase
from core.city.declarative_manifest import ManifestLoader
from core.city.governor import DISTRICT_TASK_MAP
from core.config import CONFIG
from districts.personal_growth.skill_builder import SkillBuilder, collect_stable_patterns
from vectorcode.src.reasoning_bank import PatternLearner


STABLE_PATTERN = {
    "task_type": "restart_stalled_worker",
    "strategy": "Check the queue depth, then send SIGTERM, then relaunch the worker process.",
    "usage_count": 5,
    "quality_score": 0.8,
    "stable": True,
}


def test_manifest_tier_and_route_are_exact():
    definitions = ManifestLoader().load()
    personal_growth = {e["name"]: e for e in definitions if e["district"] == "personal_growth"}
    assert "skill_builder" in personal_growth

    entry = personal_growth["skill_builder"]
    assert entry["class"].endswith(".SkillBuilder")

    instance = SkillBuilder()
    assert entry["capabilities"] == instance.capabilities
    for action in instance.capabilities:
        assert DISTRICT_TASK_MAP[action] == "personal_growth"
        assert action in CONFIG["permission"]["green"]
        assert action not in CONFIG["permission"]["yellow"]
        assert action not in CONFIG["permission"]["red"]

    instances = ManifestLoader().instantiate_all([entry])
    assert {type(i) for i in instances} == {SkillBuilder}


@pytest.mark.asyncio
async def test_brief_reports_missing_and_present_evidence(tmp_path):
    agent = SkillBuilder(skills_dir=tmp_path)
    assert isinstance(agent, AgentBase)

    missing = await agent.run({"type": agent.profile.brief_action, "evidence": {}})
    assert missing["report"]["status"] == "needs_human"
    assert missing["report"]["missing_evidence"] == ["patterns"]

    ready = await agent.run(
        {"type": agent.profile.brief_action, "evidence": {"patterns": [STABLE_PATTERN]}}
    )
    assert ready["report"]["status"] == "ready"
    assert ready["report"]["present_evidence"] == ["patterns"]


@pytest.mark.asyncio
async def test_build_writes_a_real_skill_md_for_a_stable_pattern(tmp_path):
    agent = SkillBuilder(skills_dir=tmp_path)
    start_hp = agent.health_points

    result = await agent.run(
        {"type": agent.profile.check_action, "evidence": {"patterns": [STABLE_PATTERN]}}
    )
    report = result["report"]
    assert report["status"] == "passed"
    assert report["built"] == [
        {
            "task_type": "restart_stalled_worker",
            "slug": "restart-stalled-worker",
            "path": str(tmp_path / "restart-stalled-worker" / "SKILL.md"),
            "usage_count": 5,
            "quality_score": 0.8,
        }
    ]
    assert report["skipped"] == []
    assert agent.health_points > start_hp

    skill_path = tmp_path / "restart-stalled-worker" / "SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "name: restart-stalled-worker" in content
    assert "usage_count: 5" in content
    assert "quality_score: 0.8000" in content
    assert "Check the queue depth, then send SIGTERM, then relaunch" in content


@pytest.mark.asyncio
async def test_build_skips_patterns_that_are_not_yet_eligible(tmp_path):
    agent = SkillBuilder(skills_dir=tmp_path)

    not_stable = {**STABLE_PATTERN, "stable": False}
    too_few_uses = {**STABLE_PATTERN, "usage_count": 1}
    low_quality = {**STABLE_PATTERN, "quality_score": 0.1}
    short_strategy = {**STABLE_PATTERN, "strategy": "too short"}
    malformed = {"strategy": "no task_type here"}

    result = await agent.run(
        {
            "type": agent.profile.check_action,
            "evidence": {
                "patterns": [not_stable, too_few_uses, low_quality, short_strategy, malformed]
            },
        }
    )
    report = result["report"]
    assert report["status"] == "needs_human"
    assert report["built"] == []
    assert len(report["skipped"]) == 5

    reasons_joined = " ".join(
        " ".join(item["reasons"]) for item in report["skipped"]
    )
    assert "not marked stable" in reasons_joined
    assert "usage_count 1 < required 3" in reasons_joined
    assert "quality_score 0.1 < required 0.5" in reasons_joined
    assert "strategy text too short" in reasons_joined
    assert "missing task_type" in reasons_joined

    assert not any(tmp_path.iterdir())  # nothing was written


@pytest.mark.asyncio
async def test_build_is_idempotent_and_respects_caller_supplied_thresholds(tmp_path):
    agent = SkillBuilder(skills_dir=tmp_path)
    lenient = {**STABLE_PATTERN, "usage_count": 3, "quality_score": 0.5}

    strict = await agent.run(
        {
            "type": agent.profile.check_action,
            "evidence": {"patterns": [lenient], "min_usages": 4, "min_quality": 0.5},
        }
    )
    assert strict["report"]["status"] == "needs_human"
    assert strict["report"]["built"] == []

    ok = await agent.run(
        {
            "type": agent.profile.check_action,
            "evidence": {"patterns": [lenient], "min_usages": 3, "min_quality": 0.5},
        }
    )
    assert ok["report"]["status"] == "passed"
    assert len(ok["report"]["built"]) == 1


def test_collect_stable_patterns_reads_real_patternlearner_data(tmp_path, monkeypatch):
    patterns_path = tmp_path / "patterns.json"
    learner = PatternLearner(path=patterns_path, auto_load=False)
    for _ in range(3):
        learner.extract(
            task="deploy the api worker",
            reasoning="Build the docker image, push it, then roll the deployment out.",
            outcome="Deployed successfully with zero downtime.",
            reward=0.85,
        )
    learner.save()

    # collect_stable_patterns() constructs PatternLearner() with defaults
    # (reading ~/.vector/patterns.json); patch the default path so this test
    # reads the real, freshly-written file above instead of the owner's own.
    import vectorcode.src.reasoning_bank as reasoning_bank_module

    monkeypatch.setattr(reasoning_bank_module, "_DEFAULT_PATTERNS_PATH", patterns_path)

    patterns = collect_stable_patterns()
    assert patterns
    assert patterns[0]["stable"] is True
    assert patterns[0]["usage_count"] >= 3
    assert "strategy" in patterns[0] and "task_type" in patterns[0]


def test_no_dangerous_primitives_in_skill_builder():
    module_path = Path(__file__).parents[1] / "districts" / "personal_growth" / "skill_builder.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not ({"subprocess", "runpy", "socket"} & imported_roots)

    banned_calls = {"eval", "exec", "compile", "system", "popen"}
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert not (banned_calls & called)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
