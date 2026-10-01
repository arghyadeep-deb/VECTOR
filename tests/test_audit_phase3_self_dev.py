"""Audit phase 3: self_dev verification must fail closed."""

import asyncio

from districts.self_dev.self_dev_specialists import (
    AgentCreator,
    PluginValidator,
    SkillComparator,
)

SPEC = {"name": "X", "agent_id": "x_001", "district": "self_dev", "capabilities": ["c"]}


def _src(body: str) -> str:
    return (
        "from core.city.agent_base import AgentBase\n"
        f"{body}\n"
        "class X(AgentBase):\n    async def run(self, task):\n        return {}\n"
    )


def _audit(agent, evidence):
    return asyncio.run(agent.run({"type": agent.profile.audit_action, "evidence": evidence}))


def _checks(result):
    return {c["check"]: c for c in result["verification"]["checks"]}


def test_failed_audit_status_is_not_ok():
    evidence = {
        "plugin_json": {"name": "p", "version": "1.0.0", "description": "d",
                        "entrypoint": "missing.py", "permissions": []},
        "package_files": [".codex-plugin/plugin.json"],
    }
    result = _audit(PluginValidator(), evidence)
    assert result["verification"]["passed"] is False
    assert result["status"] != "ok"


def test_agent_with_subprocess_or_eval_is_flagged():
    for body in (
        "import subprocess\nsubprocess.run(['pip', 'install', 'x'])",
        "import os\nos.system('rm -rf x')",
        "eval('1')",
        "exec('x=1')",
    ):
        result = _audit(AgentCreator(), {"agent_spec": SPEC, "source_code": _src(body)})
        assert _checks(result)["no_process_or_dynamic_exec_primitive"]["passed"] is False, body
        assert result["verification"]["passed"] is False


def test_clean_agent_passes_exec_check():
    result = _audit(AgentCreator(), {"agent_spec": SPEC, "source_code": _src("")})
    assert result["verification"]["passed"] is True


def test_plugin_entrypoint_traversal_rejected():
    for ep in ("../../core/loop/permission_gateway.py", "/etc/passwd", "C:/x.py"):
        evidence = {
            "plugin_json": {"name": "p", "version": "1.0.0", "description": "d",
                            "entrypoint": ep, "permissions": []},
            "package_files": [".codex-plugin/plugin.json", ep],
        }
        result = _audit(PluginValidator(), evidence)
        assert _checks(result)["entrypoint_is_confined"]["passed"] is False, ep
        assert result["verification"]["passed"] is False


def test_comparison_without_expectations_does_not_pass():
    for exp in ({}, {"required_additions": [""]}):
        result = _audit(
            SkillComparator(),
            {"baseline_skill": "a", "candidate_skill": "b", "expectations": exp},
        )
        assert result["verification"]["passed"] is False, exp
