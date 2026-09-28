"""Regression coverage for the self-development Coding specialist package."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.declarative_manifest import ManifestLoader
from core.city.governor import DISTRICT_TASK_MAP
from core.config import CONFIG
from districts.coding.coding_specialists import SPECIALIST_CLASSES

COMPLETE_EVIDENCE = {
    "AgentSDKVerifierTS": {
        "package_json": {"dependencies": {"@openai/agents": "1.0.0"}},
        "tsconfig": {"compilerOptions": {"strict": True}},
        "source_files": {
            "agent.ts": "import { Agent } from '@openai/agents';\nexport const agent = new Agent({ name: 'demo' });"
        },
    },
    "BusinessRulesExtractor": {
        "source_code": (
            "def price(total: float) -> float:\n    if total > 100:\n        return total * 0.9\n    return total\n"
        ),
        "domain_context": "Orders above 100 receive a discount.",
    },
    "LegacyAnalyst": {
        "source_code": (
            "def normalize(value):\n"
            "    try:\n"
            "        return value.strip()\n"
            "    except AttributeError:\n"
            "        return value\n"
        ),
        "runtime_constraints": ["python>=3.12"],
    },
    "Scaffolder": {
        "file_tree": {
            "src/app.py": "def main():\n    return True\n",
            "tests/test_app.py": "def test_main():\n    assert True\n",
        },
        "scaffold_spec": {"required_files": ["src/app.py", "tests/test_app.py"]},
    },
    "UpliftMigrator": {
        "before_source": "def total(xs):\n    return sum([x for x in xs])\n",
        "after_source": "def total(xs: list[int]) -> int:\n    return sum(xs)\n",
        "migration_goal": "Add typing and remove the redundant list allocation.",
    },
    "VersionDeltaAnalyst": {
        "baseline_contract": {"parse": "(text: str) -> dict"},
        "current_contract": {"parse": "(text: str) -> dict", "validate": "(data: dict) -> bool"},
        "release_notes": "Adds validate without removing parse.",
    },
    "AIDataRemediationEngineer": {
        "records": [{"id": "a", "label": "ok"}, {"id": "b", "label": "review"}],
        "remediation_rules": {"required_fields": ["id", "label"], "unique_by": "id", "non_null": ["label"]},
    },
    "AutonomousOptimizationArchitect": {
        "baseline_metrics": {"latency_ms": 120.0, "success_rate": 0.90},
        "candidate_metrics": {"latency_ms": 90.0, "success_rate": 0.95},
        "objectives": {
            "latency_ms": {"direction": "decrease", "min_improvement": 10.0},
            "success_rate": {"direction": "increase", "min_improvement": 0.01},
        },
    },
    "CMSDeveloper": {
        "content_model": {"fields": [{"name": "title", "type": "string"}, {"name": "slug", "type": "string"}]},
        "route_definitions": [{"path": "/posts/{slug}", "method": "GET", "content_type": "post"}],
    },
    "MobileAppBuilder": {
        "project_files": {
            "android/app/src/main/AndroidManifest.xml": "<manifest/>",
            "src/App.tsx": "export default function App() { return null; }",
        },
        "target_platforms": ["android"],
    },
    "CommentAnalyzer": {
        "comments": [
            {
                "file": "src/app.py",
                "line": 7,
                "severity": "important",
                "body": "Handle the empty input before indexing.",
            }
        ],
        "change_context": "Input validation update.",
    },
    "TypeDesignAnalyzer": {
        "source_code": "def parse(text: str) -> dict[str, str]:\n    return {'value': text}\n",
        "public_api": ["parse"],
    },
    "MCPBuilder": {
        "server_manifest": {
            "name": "demo",
            "tools": [
                {
                    "name": "lookup",
                    "description": "Look up a value",
                    "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
                }
            ],
        },
        "transport": "stdio",
    },
    "TerminalIntegrationSpecialist": {
        "commands": [
            {"name": "status", "argv": ["git", "status", "--short"], "timeout_seconds": 10, "success_exit_codes": [0]}
        ],
        "shell_constraints": {"allow_shell": False},
    },
}


def test_brief_and_check_require_real_evidence_before_awarding_hp() -> None:
    for agent_cls in SPECIALIST_CLASSES:
        agent = agent_cls()
        brief = asyncio.run(agent.run({"type": agent.profile.primary_action, "evidence": {}}))
        check = asyncio.run(agent.run({"type": agent.profile.audit_action, "evidence": {}}))

        assert brief["report"]["status"] == "needs_human"
        assert brief["report"]["missing_evidence"]
        assert check["verification"]["verified"] is False
        assert agent.health_points == 500


def test_complete_evidence_is_ready_and_deterministically_verified() -> None:
    for agent_cls in SPECIALIST_CLASSES:
        evidence = COMPLETE_EVIDENCE[agent_cls.__name__]

        brief_agent = agent_cls()
        brief = asyncio.run(brief_agent.run({"type": brief_agent.profile.primary_action, "evidence": evidence}))
        assert brief["report"]["status"] == "ready"
        assert brief_agent.health_points > 500

        check_agent = agent_cls()
        check = asyncio.run(check_agent.run({"type": check_agent.profile.audit_action, "evidence": evidence}))
        verification = check["verification"]
        assert verification["verified"] is True
        assert verification["verified_by"] == "deterministic_recomputation"
        assert verification["passed"] is True
        assert verification["checks"]
        assert check_agent.health_points > 500

    failed_check_agent = SPECIALIST_CLASSES[0]()
    failing_evidence = dict(COMPLETE_EVIDENCE[failed_check_agent.__class__.__name__])
    failing_evidence["tsconfig"] = {"compilerOptions": {"strict": False}}
    failed_check = asyncio.run(
        failed_check_agent.run({"type": failed_check_agent.profile.audit_action, "evidence": failing_evidence})
    )
    assert failed_check["verification"]["verified"] is True
    assert failed_check["verification"]["passed"] is False
    assert failed_check_agent.health_points == 500


def test_manifest_tiers_and_exact_routes_match_class_capabilities() -> None:
    manifest = ManifestLoader().load()
    entries = {entry["class"]: entry for entry in manifest}
    specialist_entries = []

    for agent_cls in SPECIALIST_CLASSES:
        agent = agent_cls()
        class_path = f"{agent_cls.__module__}.{agent_cls.__name__}"
        entry = entries[class_path]
        specialist_entries.append(entry)

        assert entry["district"] == "coding"
        assert entry["capabilities"] == agent.capabilities
        for capability in agent.capabilities:
            assert capability in CONFIG["permission"]["green"]
            assert capability not in CONFIG["permission"]["yellow"]
            assert capability not in CONFIG["permission"]["red"]
            assert DISTRICT_TASK_MAP[capability] == "coding"

    instances = ManifestLoader().instantiate_all(specialist_entries)
    assert {type(instance) for instance in instances} == set(SPECIALIST_CLASSES)


if __name__ == "__main__":
    test_brief_and_check_require_real_evidence_before_awarding_hp()
    test_complete_evidence_is_ready_and_deterministically_verified()
    test_manifest_tiers_and_exact_routes_match_class_capabilities()
    print("coding specialist tests OK")
