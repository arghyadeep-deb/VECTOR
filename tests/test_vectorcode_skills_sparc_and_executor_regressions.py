"""Correctness regressions for SPARC and nested skill execution."""

from __future__ import annotations

import asyncio

from vectorcode.src.skills.builtin.sparc.coordinator import (
    SPARC_STAGES,
    run_sparc_stage,
    sparc_slash_command,
)
from vectorcode.src.skills.executor import SkillExecutor, SkillResult


class FakeAgent:
    def __init__(self):
        self.prompts = []

    async def run_conversation(self, prompt):
        self.prompts.append(prompt)
        return {"text": "ok"}


def test_advertised_sparc_task_syntax_runs_full_pipeline():
    agent = FakeAgent()

    result = sparc_slash_command("build", "a calculator", agent)

    assert len(agent.prompts) == len(SPARC_STAGES)
    assert "Task: build a calculator" in agent.prompts[0]
    assert "## COMPLETION\nok" in result


def test_each_sparc_stage_can_run_without_prior_stage_context():
    for stage in SPARC_STAGES:
        agent = FakeAgent()
        assert asyncio.run(run_sparc_stage(stage, "task", {}, agent)) == "ok"
        assert agent.prompts


def test_malformed_sub_skill_arguments_do_not_silently_become_empty_context():
    executor = SkillExecutor.__new__(SkillExecutor)
    calls = []
    executor._skill_resolver = lambda name, ctx: (
        calls.append((name, ctx)) or SkillResult(skill_name=name)
    )

    result = executor._run_sub_skill("child", "{not-json", {}, "parent", 0)

    assert result.success is False
    assert "Invalid sub-skill arguments JSON" in result.content
    assert calls == []


def test_non_object_sub_skill_arguments_are_rejected():
    executor = SkillExecutor.__new__(SkillExecutor)
    executor._skill_resolver = lambda name, ctx: SkillResult(skill_name=name)

    result = executor._run_sub_skill("child", '["not", "an", "object"]', {}, "parent", 0)

    assert result.success is False
    assert "JSON object" in result.content
