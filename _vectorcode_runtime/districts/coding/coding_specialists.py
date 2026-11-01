"""Evidence-gated Coding specialists created by the self-development program.

Every check in this module recomputes a result from caller-supplied artifacts.
The agents never treat prose or a model's opinion as verification, and they do
not mutate repositories, services, devices, or external platforms.
"""

from __future__ import annotations

import ast
import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase

Check = dict[str, Any]
Analyzer = Callable[[dict[str, Any]], list[Check]]


@dataclass(frozen=True)
class SpecialistProfile:
    """Bounded contract for one independently verifiable coding persona."""

    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str
    analyzer: str


def _parsed(source: object) -> ast.AST | None:
    if not isinstance(source, str) or not source.strip():
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _check_agent_sdk_ts(evidence: dict[str, Any]) -> list[Check]:
    package = evidence.get("package_json")
    tsconfig = evidence.get("tsconfig")
    files = evidence.get("source_files")
    if not isinstance(package, dict) or not isinstance(tsconfig, dict) or not isinstance(files, dict):
        return []
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    source = "\n".join(str(value) for value in files.values())
    compiler = tsconfig.get("compilerOptions", {})
    return [
        {
            "check": "agent_sdk_dependency_declared",
            "passed": "@openai/agents" in dependencies,
        },
        {"check": "typescript_strict_mode", "passed": compiler.get("strict") is True},
        {"check": "agent_constructed_in_source", "passed": bool(re.search(r"\bnew\s+Agent\s*\(", source))},
        {"check": "agent_exported", "passed": bool(re.search(r"\bexport\b", source))},
    ]


def _check_business_rules(evidence: dict[str, Any]) -> list[Check]:
    tree = _parsed(evidence.get("source_code"))
    if tree is None:
        return []
    conditions = [node for node in ast.walk(tree) if isinstance(node, (ast.If, ast.Match, ast.Compare))]
    functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return [
        {"check": "source_parses", "passed": True},
        {"check": "executable_rules_found", "passed": bool(conditions), "actual": len(conditions)},
        {"check": "rule_owners_found", "passed": bool(functions), "functions": sorted(functions)},
    ]


def _check_legacy_code(evidence: dict[str, Any]) -> list[Check]:
    tree = _parsed(evidence.get("source_code"))
    if tree is None:
        return []
    bare_except = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.type is None]
    wildcard_imports = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]
    return [
        {"check": "legacy_source_parses", "passed": True},
        {"check": "no_bare_except", "passed": not bare_except, "lines": bare_except},
        {"check": "no_wildcard_import", "passed": not wildcard_imports, "lines": wildcard_imports},
    ]


def _check_scaffold(evidence: dict[str, Any]) -> list[Check]:
    files = evidence.get("file_tree")
    spec = evidence.get("scaffold_spec")
    if not isinstance(files, dict) or not isinstance(spec, dict):
        return []
    required = spec.get("required_files")
    if not isinstance(required, list):
        return []
    missing = sorted(str(path) for path in required if path not in files)
    empty = sorted(str(path) for path in required if path in files and not str(files[path]).strip())
    return [
        {"check": "required_files_present", "passed": not missing, "missing": missing},
        {"check": "required_files_non_empty", "passed": not empty, "empty": empty},
    ]


def _check_uplift(evidence: dict[str, Any]) -> list[Check]:
    before = evidence.get("before_source")
    after = evidence.get("after_source")
    before_tree = _parsed(before)
    after_tree = _parsed(after)
    if before_tree is None or after_tree is None:
        return []
    diff = list(difflib.unified_diff(str(before).splitlines(), str(after).splitlines(), lineterm=""))
    before_defs = {
        node.name
        for node in ast.walk(before_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    after_defs = {
        node.name
        for node in ast.walk(after_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    return [
        {"check": "before_and_after_parse", "passed": True},
        {"check": "migration_changes_source", "passed": bool(diff), "diff_lines": len(diff)},
        {
            "check": "public_definitions_preserved",
            "passed": before_defs <= after_defs,
            "removed": sorted(before_defs - after_defs),
        },
    ]


def _check_version_delta(evidence: dict[str, Any]) -> list[Check]:
    baseline = evidence.get("baseline_contract")
    current = evidence.get("current_contract")
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        return []
    removed = sorted(set(baseline) - set(current))
    added = sorted(set(current) - set(baseline))
    changed = sorted(name for name in set(baseline) & set(current) if baseline[name] != current[name])
    return [
        {"check": "contract_delta_computed", "passed": True, "added": added, "removed": removed, "changed": changed},
        {"check": "no_removed_contracts", "passed": not removed, "removed": removed},
        {"check": "existing_signatures_stable", "passed": not changed, "changed": changed},
    ]


def _check_data_remediation(evidence: dict[str, Any]) -> list[Check]:
    records = evidence.get("records")
    rules = evidence.get("remediation_rules")
    if not isinstance(records, list) or not records or not isinstance(rules, dict):
        return []
    required = [str(field) for field in rules.get("required_fields", [])]
    non_null = [str(field) for field in rules.get("non_null", [])]
    unique_by = rules.get("unique_by")
    missing = [
        index
        for index, row in enumerate(records)
        if not isinstance(row, dict) or any(field not in row for field in required)
    ]
    nulls = [
        index
        for index, row in enumerate(records)
        if isinstance(row, dict) and any(row.get(field) is None for field in non_null)
    ]
    values = [row.get(unique_by) for row in records if isinstance(row, dict)] if isinstance(unique_by, str) else []
    duplicates = sorted({str(value) for value in values if values.count(value) > 1})
    return [
        {"check": "required_fields_present", "passed": not missing, "record_indexes": missing},
        {"check": "non_null_constraints", "passed": not nulls, "record_indexes": nulls},
        {"check": "unique_key_constraint", "passed": not duplicates, "duplicates": duplicates},
    ]


def _check_optimization(evidence: dict[str, Any]) -> list[Check]:
    baseline = evidence.get("baseline_metrics")
    candidate = evidence.get("candidate_metrics")
    objectives = evidence.get("objectives")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict) or not isinstance(objectives, dict):
        return []
    checks: list[Check] = []
    for metric, objective in objectives.items():
        if metric not in baseline or metric not in candidate or not isinstance(objective, dict):
            checks.append({"check": f"{metric}_measured", "passed": False})
            continue
        old = float(baseline[metric])
        new = float(candidate[metric])
        direction = objective.get("direction")
        if direction not in {"increase", "decrease"}:
            checks.append({"check": f"{metric}_direction_valid", "passed": False, "actual": direction})
            continue
        improvement = old - new if direction == "decrease" else new - old
        required = float(objective.get("min_improvement", 0.0))
        checks.append(
            {
                "check": f"{metric}_objective",
                "passed": improvement >= required,
                "actual": improvement,
                "required": required,
            }
        )
    return checks


def _check_cms(evidence: dict[str, Any]) -> list[Check]:
    model = evidence.get("content_model")
    routes = evidence.get("route_definitions")
    if not isinstance(model, dict) or not isinstance(routes, list):
        return []
    fields = model.get("fields")
    if not isinstance(fields, list):
        return []
    field_names = [field.get("name") for field in fields if isinstance(field, dict)]
    route_keys = [(route.get("method"), route.get("path")) for route in routes if isinstance(route, dict)]
    return [
        {
            "check": "content_fields_well_formed",
            "passed": len(field_names) == len(fields)
            and bool(field_names)
            and all(field_names)
            and all(field.get("type") for field in fields if isinstance(field, dict)),
        },
        {"check": "content_fields_unique", "passed": len(field_names) == len(set(field_names))},
        {
            "check": "routes_well_formed",
            "passed": bool(route_keys) and all(method and path for method, path in route_keys),
        },
        {"check": "routes_unique", "passed": len(route_keys) == len(set(route_keys))},
    ]


def _check_mobile_project(evidence: dict[str, Any]) -> list[Check]:
    files = evidence.get("project_files")
    platforms = evidence.get("target_platforms")
    if not isinstance(files, dict) or not isinstance(platforms, list):
        return []
    lowered = {str(path).lower() for path in files}
    checks: list[Check] = [
        {
            "check": "application_source_present",
            "passed": any(path.endswith(("app.tsx", "app.kt", "app.swift")) for path in lowered),
        }
    ]
    if "android" in {str(platform).lower() for platform in platforms}:
        checks.append(
            {
                "check": "android_manifest_present",
                "passed": any(path.endswith("androidmanifest.xml") for path in lowered),
            }
        )
    if "ios" in {str(platform).lower() for platform in platforms}:
        checks.append(
            {"check": "ios_info_plist_present", "passed": any(path.endswith("info.plist") for path in lowered)}
        )
    return checks


def _check_comments(evidence: dict[str, Any]) -> list[Check]:
    comments = evidence.get("comments")
    if not isinstance(comments, list) or not comments:
        return []
    valid_severities = {"critical", "important", "suggestion", "nit"}
    structured = [item for item in comments if isinstance(item, dict)]
    return [
        {
            "check": "comments_have_locations",
            "passed": len(structured) == len(comments)
            and all(item.get("file") and isinstance(item.get("line"), int) and item["line"] > 0 for item in structured),
        },
        {
            "check": "comments_are_prioritized",
            "passed": all(str(item.get("severity", "")).lower() in valid_severities for item in structured),
        },
        {
            "check": "comments_are_actionable",
            "passed": all(len(str(item.get("body", "")).strip()) >= 12 for item in structured),
        },
    ]


def _check_type_design(evidence: dict[str, Any]) -> list[Check]:
    tree = _parsed(evidence.get("source_code"))
    public_api = evidence.get("public_api")
    if tree is None or not isinstance(public_api, list):
        return []
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(str(name) for name in public_api if name not in functions)
    untyped = []
    for name in public_api:
        node = functions.get(name)
        if node is not None and (node.returns is None or any(arg.annotation is None for arg in node.args.args)):
            untyped.append(str(name))
    return [
        {"check": "public_api_symbols_exist", "passed": not missing, "missing": missing},
        {"check": "public_api_fully_annotated", "passed": not untyped, "untyped": sorted(untyped)},
    ]


def _check_mcp_manifest(evidence: dict[str, Any]) -> list[Check]:
    manifest = evidence.get("server_manifest")
    if not isinstance(manifest, dict):
        return []
    tools = manifest.get("tools")
    if not isinstance(tools, list) or not tools:
        return []
    structured = [tool for tool in tools if isinstance(tool, dict)]
    names = [tool.get("name") for tool in structured]
    schemas = [tool.get("inputSchema") for tool in structured]
    required_properties_match = all(
        isinstance(schema, dict)
        and set(schema.get("required", [])) <= set(schema.get("properties", {}))
        for schema in schemas
    )
    return [
        {"check": "server_named", "passed": bool(manifest.get("name"))},
        {
            "check": "tool_names_unique",
            "passed": len(names) == len(tools) and all(names) and len(names) == len(set(names)),
        },
        {
            "check": "tool_descriptions_present",
            "passed": len(structured) == len(tools) and all(tool.get("description") for tool in structured),
        },
        {
            "check": "input_schemas_are_objects",
            "passed": all(isinstance(schema, dict) and schema.get("type") == "object" for schema in schemas),
        },
        {"check": "required_schema_properties_exist", "passed": required_properties_match},
    ]


def _check_terminal_contract(evidence: dict[str, Any]) -> list[Check]:
    commands = evidence.get("commands")
    constraints = evidence.get("shell_constraints")
    if not isinstance(commands, list) or not commands or not isinstance(constraints, dict):
        return []
    structured = [command for command in commands if isinstance(command, dict)]
    names = [command.get("name") for command in structured]
    return [
        {
            "check": "command_names_unique",
            "passed": len(names) == len(commands) and all(names) and len(names) == len(set(names)),
        },
        {
            "check": "argv_is_tokenized",
            "passed": all(
                isinstance(command.get("argv"), list)
                and all(isinstance(token, str) and token for token in command["argv"])
                for command in structured
            ),
        },
        {
            "check": "timeouts_are_bounded",
            "passed": all(
                isinstance(command.get("timeout_seconds"), (int, float)) and 0 < command["timeout_seconds"] <= 300
                for command in structured
            ),
        },
        {
            "check": "success_exit_codes_declared",
            "passed": all(
                isinstance(command.get("success_exit_codes"), list) and 0 in command["success_exit_codes"]
                for command in structured
            ),
        },
        {"check": "shell_execution_disabled", "passed": constraints.get("allow_shell") is False},
    ]


ANALYZERS: dict[str, Analyzer] = {
    "agent_sdk_ts": _check_agent_sdk_ts,
    "business_rules": _check_business_rules,
    "legacy_code": _check_legacy_code,
    "scaffold": _check_scaffold,
    "uplift": _check_uplift,
    "version_delta": _check_version_delta,
    "data_remediation": _check_data_remediation,
    "optimization": _check_optimization,
    "cms": _check_cms,
    "mobile": _check_mobile_project,
    "comments": _check_comments,
    "type_design": _check_type_design,
    "mcp": _check_mcp_manifest,
    "terminal": _check_terminal_contract,
}


class CodingSpecialist(AgentBase):
    """Base class for read-only, evidence-checked Coding personas."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(self.profile.agent_id, self.profile.name, "coding", generation)
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][coding_specialists] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.evidence_fields if supplied.get(field)]
        missing = [field for field in self.profile.evidence_fields if not supplied.get(field)]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        checks = ANALYZERS[self.profile.analyzer](supplied)
        return {
            "verified": bool(checks),
            "verified_by": "deterministic_recomputation" if checks else "none",
            "passed": all(check["passed"] for check in checks) if checks else None,
            "checks": checks,
            "note": "" if checks else "No checkable evidence was supplied; no verification claim was made.",
        }

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}'",
                "supported_tasks": self.capabilities,
            }
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        evidence = task.get("evidence") or params.get("evidence")
        try:
            report = self.build_evidence_report(evidence)
            response: dict[str, Any] = {"status": "ok", "report": report}
            if task_type == self.profile.audit_action:
                response["verification"] = self.run_checks(evidence)
            verification = response.get("verification", {})
            if task_type == self.profile.audit_action:
                earned = verification.get("verified") is True and verification.get("passed") is True
            else:
                earned = report["status"] == "ready"
            if earned:
                self.award_points(20, f"{task_type}_verified")
            return response
        except Exception as exc:
            logger.error("[VECTOR][coding_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "coding_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


def _p(
    name: str, slug: str, primary: str, audit: str, evidence: tuple[str, ...], deliverable: str, analyzer: str
) -> SpecialistProfile:
    return SpecialistProfile(name, f"{slug}_001", primary, audit, evidence, deliverable, analyzer)


class AgentSDKVerifierTS(CodingSpecialist):
    profile = _p(
        "AgentSDKVerifierTS",
        "agent_sdk_verifier_ts",
        "agent_sdk_ts_brief",
        "agent_sdk_ts_check",
        ("package_json", "tsconfig", "source_files"),
        "TypeScript agent SDK verification brief",
        "agent_sdk_ts",
    )


class BusinessRulesExtractor(CodingSpecialist):
    profile = _p(
        "BusinessRulesExtractor",
        "business_rules_extractor",
        "business_rules_brief",
        "business_rules_check",
        ("source_code", "domain_context"),
        "business-rule extraction brief",
        "business_rules",
    )


class LegacyAnalyst(CodingSpecialist):
    profile = _p(
        "LegacyAnalyst",
        "legacy_analyst",
        "legacy_analysis_brief",
        "legacy_analysis_check",
        ("source_code", "runtime_constraints"),
        "legacy code analysis brief",
        "legacy_code",
    )


class Scaffolder(CodingSpecialist):
    profile = _p(
        "Scaffolder",
        "scaffolder",
        "scaffold_brief",
        "scaffold_structure_check",
        ("file_tree", "scaffold_spec"),
        "project scaffold brief",
        "scaffold",
    )


class UpliftMigrator(CodingSpecialist):
    profile = _p(
        "UpliftMigrator",
        "uplift_migrator",
        "uplift_migration_brief",
        "uplift_migration_check",
        ("before_source", "after_source", "migration_goal"),
        "code uplift migration brief",
        "uplift",
    )


class VersionDeltaAnalyst(CodingSpecialist):
    profile = _p(
        "VersionDeltaAnalyst",
        "version_delta_analyst",
        "version_delta_brief",
        "version_delta_check",
        ("baseline_contract", "current_contract", "release_notes"),
        "version contract delta brief",
        "version_delta",
    )


class AIDataRemediationEngineer(CodingSpecialist):
    profile = _p(
        "AIDataRemediationEngineer",
        "ai_data_remediation_engineer",
        "ai_data_remediation_brief",
        "ai_data_remediation_check",
        ("records", "remediation_rules"),
        "AI dataset remediation brief",
        "data_remediation",
    )


class AutonomousOptimizationArchitect(CodingSpecialist):
    profile = _p(
        "AutonomousOptimizationArchitect",
        "autonomous_optimization_architect",
        "autonomous_optimization_brief",
        "autonomous_optimization_check",
        ("baseline_metrics", "candidate_metrics", "objectives"),
        "measured optimization brief",
        "optimization",
    )


class CMSDeveloper(CodingSpecialist):
    profile = _p(
        "CMSDeveloper",
        "cms_developer",
        "cms_implementation_brief",
        "cms_structure_check",
        ("content_model", "route_definitions"),
        "CMS implementation brief",
        "cms",
    )


class MobileAppBuilder(CodingSpecialist):
    profile = _p(
        "MobileAppBuilder",
        "mobile_app_builder",
        "mobile_app_brief",
        "mobile_project_check",
        ("project_files", "target_platforms"),
        "mobile application structure brief",
        "mobile",
    )


class CommentAnalyzer(CodingSpecialist):
    profile = _p(
        "CommentAnalyzer",
        "comment_analyzer",
        "review_comment_brief",
        "review_comment_check",
        ("comments", "change_context"),
        "code-review comment analysis brief",
        "comments",
    )


class TypeDesignAnalyzer(CodingSpecialist):
    profile = _p(
        "TypeDesignAnalyzer",
        "type_design_analyzer",
        "type_design_brief",
        "type_design_check",
        ("source_code", "public_api"),
        "public API type-design brief",
        "type_design",
    )


class MCPBuilder(CodingSpecialist):
    profile = _p(
        "MCPBuilder",
        "mcp_builder",
        "mcp_server_brief",
        "mcp_manifest_check",
        ("server_manifest", "transport"),
        "MCP server contract brief",
        "mcp",
    )


class TerminalIntegrationSpecialist(CodingSpecialist):
    profile = _p(
        "TerminalIntegrationSpecialist",
        "terminal_integration_specialist",
        "terminal_integration_brief",
        "terminal_contract_check",
        ("commands", "shell_constraints"),
        "terminal integration contract brief",
        "terminal",
    )


SPECIALIST_CLASSES: tuple[type[CodingSpecialist], ...] = (
    AgentSDKVerifierTS,
    BusinessRulesExtractor,
    LegacyAnalyst,
    Scaffolder,
    UpliftMigrator,
    VersionDeltaAnalyst,
    AIDataRemediationEngineer,
    AutonomousOptimizationArchitect,
    CMSDeveloper,
    MobileAppBuilder,
    CommentAnalyzer,
    TypeDesignAnalyzer,
    MCPBuilder,
    TerminalIntegrationSpecialist,
)


if __name__ == "__main__":
    import asyncio

    async def _smoke() -> None:
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            brief = await specialist.run({"type": specialist.profile.primary_action, "evidence": {}})
            check = await specialist.run({"type": specialist.profile.audit_action, "evidence": {}})
            assert brief["report"]["status"] == "needs_human"
            assert check["verification"]["verified"] is False
            assert specialist.health_points == 500
        logger.info("[VECTOR][coding_specialists] smoke check passed")

    asyncio.run(_smoke())
