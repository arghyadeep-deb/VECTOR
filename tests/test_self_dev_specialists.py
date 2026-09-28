"""Regression coverage for the isolated self_dev district."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.city.agent_base import AgentBase
from core.city.governor import DISTRICT_TASK_MAP
from core.config import PermissionConfig
from districts.self_dev.self_dev_specialists import SPECIALIST_CLASSES


EXPECTED_AGENTS = {
    "agent_creator": (
        "districts.self_dev.self_dev_specialists.AgentCreator",
        {"agent_creation_brief", "agent_definition_check"},
    ),
    "plugin_validator": (
        "districts.self_dev.self_dev_specialists.PluginValidator",
        {"plugin_validation_brief", "plugin_manifest_check"},
    ),
    "skill_reviewer": (
        "districts.self_dev.self_dev_specialists.SkillReviewer",
        {"skill_review_brief", "skill_structure_check"},
    ),
    "skill_analyzer": (
        "districts.self_dev.self_dev_specialists.SkillAnalyzer",
        {"skill_analysis_brief", "skill_analysis_check"},
    ),
    "skill_comparator": (
        "districts.self_dev.self_dev_specialists.SkillComparator",
        {"skill_comparison_brief", "skill_comparison_check"},
    ),
    "skill_grader": (
        "districts.self_dev.self_dev_specialists.SkillGrader",
        {"skill_grading_brief", "skill_grade_check"},
    ),
    "conversation_analyzer": (
        "districts.self_dev.self_dev_specialists.ConversationAnalyzer",
        {"hook_conversation_brief", "hook_candidate_check"},
    ),
}
EXPECTED_CAPABILITIES = set().union(*(entry[1] for entry in EXPECTED_AGENTS.values()))


SKILL_DOCUMENT = """---
name: safe-tooling-review
description: Review supplied tooling artifacts deterministically.
---
# Safe Tooling Review

## When to use
Use this skill when a caller supplies a tooling artifact.

## Steps
1. Parse the supplied artifact.
2. Run deterministic checks.
3. Report missing evidence without claiming verification.

## Resources
Read references/schema.md when validating the schema.

## Verification
Confirm every required check passed before reporting success.
"""


COMPLETE_EVIDENCE = {
    "AgentCreator": {
        "agent_spec": {
            "name": "ToolingInspector",
            "agent_id": "tooling_inspector_001",
            "district": "self_dev",
            "capabilities": ["tooling_brief", "tooling_check"],
        },
        "source_code": (
            "from core.city.agent_base import AgentBase\n"
            "class ToolingInspector(AgentBase):\n"
            "    def __init__(self):\n"
            "        super().__init__('tooling_inspector_001', 'ToolingInspector', 'self_dev')\n"
            "        self.capabilities = ['tooling_brief', 'tooling_check']\n"
            "    async def run(self, task):\n"
            "        return {'status': 'ok'}\n"
        ),
    },
    "PluginValidator": {
        "plugin_json": {
            "name": "tooling-inspector",
            "version": "1.0.0",
            "description": "Inspect VECTOR tooling artifacts.",
            "entrypoint": "server.py",
            "permissions": ["read_tooling"],
        },
        "package_files": [".codex-plugin/plugin.json", "server.py", "README.md"],
    },
    "SkillReviewer": {
        "skill_document": SKILL_DOCUMENT,
        "required_sections": ["When to use", "Steps", "Verification"],
    },
    "SkillAnalyzer": {
        "skill_document": SKILL_DOCUMENT,
        "expected_resources": ["references/schema.md"],
    },
    "SkillComparator": {
        "baseline_skill": "# Review\n## Steps\n1. Parse the artifact.\n",
        "candidate_skill": (
            "# Review\n## Steps\n1. Parse the artifact.\n2. Run deterministic checks.\n"
            "## Verification\nConfirm checks passed.\n"
        ),
        "expectations": {
            "required_additions": ["Run deterministic checks", "## Verification"],
            "required_removals": [],
        },
    },
    "SkillGrader": {
        "candidate_text": "The skill parses supplied data, reports missing evidence, and runs deterministic checks.",
        "criteria": [
            {"name": "evidence", "weight": 2, "required_terms": ["supplied data", "missing evidence"]},
            {"name": "verification", "weight": 1, "required_terms": ["deterministic checks"]},
        ],
        "passing_score": 100,
    },
    "ConversationAnalyzer": {
        "transcript": [
            {"event": "user_message", "content": "Please remember to run pytest before saying done."},
            {"event": "tool_result", "content": "pytest: 7 passed"},
        ],
        "hook_rules": [
            {"name": "verification-reminder", "event": "user_message", "pattern": r"run pytest"},
            {"name": "test-evidence", "event": "tool_result", "pattern": r"\d+ passed"},
        ],
        "expected_events": ["user_message", "tool_result"],
    },
}


def _run(agent: AgentBase, task_type: str, evidence: dict) -> dict:
    return asyncio.run(agent.run({"type": task_type, "evidence": evidence}))


def test_manifest_registers_exact_self_dev_agents() -> None:
    manifest = yaml.safe_load((ROOT / "config" / "agent_manifest.yaml").read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in manifest["districts"]["self_dev"]}

    assert set(entries) == set(EXPECTED_AGENTS)
    for name, (class_path, capabilities) in EXPECTED_AGENTS.items():
        assert entries[name]["class"] == class_path
        assert set(entries[name]["capabilities"]) == capabilities

    instances = [agent_class() for agent_class in SPECIALIST_CLASSES]
    assert all(isinstance(agent, AgentBase) for agent in instances)
    assert all(agent.district == "self_dev" for agent in instances)
    assert {capability for agent in instances for capability in agent.capabilities} == EXPECTED_CAPABILITIES


def test_every_capability_is_green_only_and_routes_only_to_self_dev() -> None:
    permissions = PermissionConfig()
    green, yellow, red = set(permissions.green), set(permissions.yellow), set(permissions.red)

    assert EXPECTED_CAPABILITIES <= green
    assert EXPECTED_CAPABILITIES.isdisjoint(yellow)
    assert EXPECTED_CAPABILITIES.isdisjoint(red)
    assert {capability: DISTRICT_TASK_MAP.get(capability) for capability in EXPECTED_CAPABILITIES} == {
        capability: "self_dev" for capability in EXPECTED_CAPABILITIES
    }


@pytest.mark.parametrize("agent_class", SPECIALIST_CLASSES)
def test_missing_evidence_needs_human_and_never_awards_hp(agent_class) -> None:
    agent = agent_class()
    starting_hp = agent.health_points

    brief = _run(agent, agent.profile.primary_action, {})
    check = _run(agent, agent.profile.audit_action, {})

    assert brief["status"] == "needs_human"
    assert brief["report"]["status"] == "needs_human"
    assert brief["report"]["missing_evidence"]
    assert check["status"] == "needs_human"
    assert check["verification"]["verified"] is False
    assert check["verification"]["passed"] is False
    assert agent.health_points == starting_hp


@pytest.mark.parametrize("agent_class", SPECIALIST_CLASSES)
def test_complete_evidence_is_ready_and_verified_with_real_hp(agent_class) -> None:
    evidence = COMPLETE_EVIDENCE[agent_class.__name__]

    brief_agent = agent_class()
    brief = _run(brief_agent, brief_agent.profile.primary_action, evidence)
    assert brief["status"] == "ok"
    assert brief["report"]["status"] == "ready"
    assert brief_agent.health_points > 500

    check_agent = agent_class()
    check = _run(check_agent, check_agent.profile.audit_action, evidence)
    assert check["status"] == "ok"
    assert check["verification"]["verified"] is True
    assert check["verification"]["passed"] is True
    assert check["verification"]["verified_by"] == "deterministic_recomputation"
    assert check["verification"]["checks"]
    assert check_agent.health_points > 500


def test_failed_deterministic_check_does_not_award_hp() -> None:
    agent = next(agent_class for agent_class in SPECIALIST_CLASSES if agent_class.__name__ == "PluginValidator")()
    evidence = COMPLETE_EVIDENCE["PluginValidator"] | {
        "plugin_json": COMPLETE_EVIDENCE["PluginValidator"]["plugin_json"] | {"entrypoint": "missing.py"}
    }

    result = _run(agent, agent.profile.audit_action, evidence)

    assert result["verification"]["verified"] is True
    assert result["verification"]["passed"] is False
    assert agent.health_points == 500


def test_self_dev_source_enforces_no_direct_product_code_or_filesystem_write_boundary() -> None:
    source_path = ROOT / "districts" / "self_dev" / "self_dev_specialists.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    write_calls: list[str] = []
    write_methods = {
        "open", "write", "writelines", "write_text", "write_bytes", "touch", "mkdir",
        "unlink", "rename", "replace", "rmdir", "remove", "removedirs", "makedirs",
        "copy", "copy2", "copyfile", "move", "rmtree",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.add(module)
            imported_modules.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in write_methods:
                write_calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in write_methods:
                write_calls.append(node.func.attr)

    assert not any(module == "districts.coding" or module.startswith("districts.coding.") for module in imported_modules)
    assert not any(module == "core.city.governor" or module.startswith("core.city.governor.") for module in imported_modules)
    assert write_calls == []


def test_unsupported_task_is_rejected_without_hp() -> None:
    agent = SPECIALIST_CLASSES[0]()
    response = _run(agent, "coding_direct_write", {})
    assert response["status"] == "error"
    assert agent.health_points == 500


def test_unsafe_hook_regex_is_rejected_without_hp() -> None:
    agent = next(agent_class for agent_class in SPECIALIST_CLASSES if agent_class.__name__ == "ConversationAnalyzer")()
    evidence = COMPLETE_EVIDENCE["ConversationAnalyzer"] | {
        "hook_rules": [{"name": "unsafe", "event": "user_message", "pattern": r"(.+)+$"}]
    }

    result = _run(agent, agent.profile.audit_action, evidence)

    checks = {check["check"]: check for check in result["verification"]["checks"]}
    assert checks["hook_patterns_compile"]["passed"] is False
    assert result["verification"]["passed"] is False
    assert agent.health_points == 500


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
