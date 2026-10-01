"""Deterministic specialists for VECTOR-owned agent, plugin, skill, and hook tooling.

The agents in this module consume caller-supplied data and return in-memory findings. They do
not edit tooling or product files. A future request for a coding-district action must use the
governed A2A interface inherited from :class:`AgentBase`; this module has no direct product-code
or Governor dependency.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import difflib
import json
import re
from typing import Any, Callable

from loguru import logger

from core.city.agent_base import AgentBase


Check = dict[str, Any]
Analyzer = Callable[[dict[str, Any]], list[Check]]
MAX_ARTIFACT_CHARS = 100_000
MAX_COLLECTION_ITEMS = 1_000
MAX_HOOK_ITEMS = 200
MAX_HOOK_CONTENT_CHARS = 4_000
MAX_HOOK_PATTERN_CHARS = 256


@dataclass(frozen=True)
class SpecialistProfile:
    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str
    analyzer: str


def _check(name: str, passed: bool, **details: Any) -> Check:
    return {"check": name, "passed": bool(passed), **details}


def _is_confined_relative(path: Any) -> bool:
    """True only for a relative path with no parent traversal, drive, or absolute root."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return False
    parts = re.split(r"[\\/]", path)
    if path[0] in "/\\" or re.match(r"^[A-Za-z]:", path):
        return False
    return ".." not in parts


def _parse_skill_document(document: Any) -> tuple[dict[str, str], list[str], str] | None:
    if not isinstance(document, str) or not document.strip().startswith("---"):
        return None
    parts = document.strip().split("---", 2)
    if len(parts) != 3:
        return None
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip():
            metadata[key.strip()] = value.strip()
    body = parts[2].strip()
    sections = [match.strip() for match in re.findall(r"^##\s+(.+?)\s*$", body, re.MULTILINE)]
    return metadata, sections, body


def _agent_definition_checks(evidence: dict[str, Any]) -> list[Check]:
    spec = evidence.get("agent_spec")
    source = evidence.get("source_code")
    if not isinstance(spec, dict) or not isinstance(source, str) or not source.strip():
        return []
    if len(source) > MAX_ARTIFACT_CHARS:
        return [_check("source_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [_check("python_source_parses", False, error=str(exc))]

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    agent_classes = [
        node
        for node in classes
        if any(
            (isinstance(base, ast.Name) and base.id == "AgentBase")
            or (isinstance(base, ast.Attribute) and base.attr == "AgentBase")
            for base in node.bases
        )
    ]
    run_methods = [
        child
        for node in agent_classes
        for child in node.body
        if isinstance(child, ast.AsyncFunctionDef) and child.name == "run"
    ]
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
    exec_names = {"system", "popen", "run", "call", "check_call", "check_output", "Popen", "exec", "eval",
                  "compile", "__import__", "import_module", "execv", "execve", "spawn", "spawnl", "startfile"}
    exec_calls = sorted({
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in exec_names)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in exec_names - {"run"})
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess")
        )
    })
    forbidden_imports = sorted(
        module
        for module in imported_modules
        if module == "core.city.governor"
        or module.startswith("core.city.governor.")
        or module == "districts.coding"
        or module.startswith("districts.coding.")
    )
    capabilities = spec.get("capabilities")
    required_strings = ("name", "agent_id", "district")
    return [
        _check("python_source_parses", True),
        _check(
            "required_agent_metadata",
            all(isinstance(spec.get(field), str) and spec[field].strip() for field in required_strings),
        ),
        _check("self_dev_district", spec.get("district") == "self_dev", actual=spec.get("district")),
        _check(
            "capabilities_are_unique",
            isinstance(capabilities, list)
            and bool(capabilities)
            and all(isinstance(item, str) and item.strip() for item in capabilities)
            and len(capabilities) == len(set(capabilities)),
        ),
        _check("agentbase_subclass_present", len(agent_classes) == 1),
        _check("async_run_present", len(run_methods) == 1),
        _check("no_direct_product_code_import", not forbidden_imports, forbidden_imports=forbidden_imports),
        _check("no_filesystem_write_primitive", not write_calls, write_calls=write_calls),
        _check("no_process_or_dynamic_exec_primitive", not exec_calls, exec_calls=exec_calls),
    ]


def _plugin_manifest_checks(evidence: dict[str, Any]) -> list[Check]:
    manifest = evidence.get("plugin_json")
    files = evidence.get("package_files")
    if isinstance(manifest, str):
        if len(manifest) > MAX_ARTIFACT_CHARS:
            return [_check("manifest_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
        try:
            manifest = json.loads(manifest)
        except json.JSONDecodeError as exc:
            return [_check("plugin_json_parses", False, error=str(exc))]
    if not isinstance(manifest, dict) or not isinstance(files, list):
        return []
    if len(files) > MAX_COLLECTION_ITEMS:
        return [_check("package_file_count_within_limit", False, limit=MAX_COLLECTION_ITEMS)]

    entrypoint = manifest.get("entrypoint")
    permissions = manifest.get("permissions")
    required_strings = ("name", "version", "description", "entrypoint")
    return [
        _check("plugin_json_parses", True),
        _check(
            "required_manifest_fields",
            all(isinstance(manifest.get(field), str) and manifest[field].strip() for field in required_strings),
        ),
        _check("plugin_name_is_slug", bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(manifest.get("name", ""))))),
        _check("version_is_semver", bool(re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))))),
        _check("manifest_file_present", ".codex-plugin/plugin.json" in files),
        _check("entrypoint_present", isinstance(entrypoint, str) and entrypoint in files, entrypoint=entrypoint),
        _check("entrypoint_is_confined", _is_confined_relative(entrypoint), entrypoint=entrypoint),
        _check(
            "permissions_are_explicit_and_unique",
            isinstance(permissions, list)
            and all(isinstance(item, str) and item.strip() for item in permissions)
            and len(permissions) == len(set(permissions)),
        ),
    ]


def _skill_review_checks(evidence: dict[str, Any]) -> list[Check]:
    document = evidence.get("skill_document")
    required = evidence.get("required_sections")
    if isinstance(document, str) and len(document) > MAX_ARTIFACT_CHARS:
        return [_check("skill_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
    parsed = _parse_skill_document(document)
    if parsed is None or not isinstance(required, list) or not required:
        return []
    if len(required) > MAX_COLLECTION_ITEMS:
        return [_check("required_section_count_within_limit", False, limit=MAX_COLLECTION_ITEMS)]
    metadata, sections, body = parsed
    missing = [section for section in required if section not in sections]
    numbered_steps = re.findall(r"^\s*\d+[.)]\s+\S", body, re.MULTILINE)
    return [
        _check("frontmatter_name_present", bool(metadata.get("name"))),
        _check("frontmatter_description_present", bool(metadata.get("description"))),
        _check("required_sections_present", not missing, missing_sections=missing),
        _check("actionable_numbered_steps_present", bool(numbered_steps), step_count=len(numbered_steps)),
    ]


def _skill_analysis_checks(evidence: dict[str, Any]) -> list[Check]:
    document = evidence.get("skill_document")
    resources = evidence.get("expected_resources")
    if isinstance(document, str) and len(document) > MAX_ARTIFACT_CHARS:
        return [_check("skill_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
    parsed = _parse_skill_document(document)
    if parsed is None or not isinstance(resources, list):
        return []
    if len(resources) > MAX_COLLECTION_ITEMS:
        return [_check("resource_count_within_limit", False, limit=MAX_COLLECTION_ITEMS)]
    metadata, sections, body = parsed
    missing_resources = [resource for resource in resources if resource not in body]
    placeholders = re.findall(r"\b(?:TODO|TBD|FIXME)\b|<[^>]+>", body, re.IGNORECASE)
    return [
        _check("metadata_is_complete", bool(metadata.get("name") and metadata.get("description"))),
        _check("multiple_instruction_sections", len(sections) >= 2, section_count=len(sections)),
        _check("expected_resources_referenced", not missing_resources, missing_resources=missing_resources),
        _check("no_unresolved_placeholders", not placeholders, placeholders=placeholders),
    ]


def _skill_comparison_checks(evidence: dict[str, Any]) -> list[Check]:
    baseline = evidence.get("baseline_skill")
    candidate = evidence.get("candidate_skill")
    expectations = evidence.get("expectations")
    if not isinstance(baseline, str) or not isinstance(candidate, str) or not isinstance(expectations, dict):
        return []
    if len(baseline) > MAX_ARTIFACT_CHARS or len(candidate) > MAX_ARTIFACT_CHARS:
        return [_check("comparison_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
    additions = expectations.get("required_additions", [])
    removals = expectations.get("required_removals", [])
    if not isinstance(additions, list) or not isinstance(removals, list):
        return []
    if len(additions) + len(removals) > MAX_COLLECTION_ITEMS:
        return [_check("expectation_count_within_limit", False, limit=MAX_COLLECTION_ITEMS)]
    missing_additions = [item for item in additions if not isinstance(item, str) or item not in candidate]
    lingering_removals = [item for item in removals if not isinstance(item, str) or item in candidate]
    diff = list(
        difflib.unified_diff(
            baseline.splitlines(), candidate.splitlines(), fromfile="baseline", tofile="candidate", lineterm=""
        )
    )
    explicit = bool(additions or removals) and all(
        isinstance(item, str) and item.strip() for item in [*additions, *removals]
    )
    return [
        _check("expectations_are_explicit", explicit),
        _check("candidate_differs_from_baseline", baseline != candidate, diff_line_count=len(diff)),
        _check("required_additions_present", not missing_additions, missing_additions=missing_additions),
        _check("required_removals_absent", not lingering_removals, lingering_removals=lingering_removals),
    ]


def _skill_grade_checks(evidence: dict[str, Any]) -> list[Check]:
    text = evidence.get("candidate_text")
    criteria = evidence.get("criteria")
    threshold = evidence.get("passing_score")
    if not isinstance(text, str) or not isinstance(criteria, list) or not criteria:
        return []
    if not isinstance(threshold, (int, float)):
        return []
    if len(text) > MAX_ARTIFACT_CHARS:
        return [_check("candidate_size_within_limit", False, limit=MAX_ARTIFACT_CHARS)]
    if len(criteria) > MAX_COLLECTION_ITEMS:
        return [_check("criterion_count_within_limit", False, limit=MAX_COLLECTION_ITEMS)]

    valid = True
    total_weight = 0.0
    earned_weight = 0.0
    results: list[dict[str, Any]] = []
    lowered = text.lower()
    for criterion in criteria:
        if not isinstance(criterion, dict):
            valid = False
            continue
        name = criterion.get("name")
        weight = criterion.get("weight")
        terms = criterion.get("required_terms")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(weight, (int, float))
            or weight <= 0
            or not isinstance(terms, list)
            or not terms
            or not all(isinstance(term, str) and term.strip() for term in terms)
        ):
            valid = False
            continue
        total_weight += float(weight)
        missing = [term for term in terms if term.lower() not in lowered]
        if not missing:
            earned_weight += float(weight)
        results.append({"criterion": name, "passed": not missing, "missing_terms": missing, "weight": weight})
    score = round(100 * earned_weight / total_weight, 2) if total_weight else 0.0
    return [
        _check("criteria_are_explicit", valid and len(results) == len(criteria), criterion_results=results),
        _check("passing_score_is_bounded", 0 <= float(threshold) <= 100, passing_score=threshold),
        _check("weighted_score_meets_threshold", valid and score >= float(threshold), score=score),
    ]


def _hook_candidate_checks(evidence: dict[str, Any]) -> list[Check]:
    transcript = evidence.get("transcript")
    rules = evidence.get("hook_rules")
    expected_events = evidence.get("expected_events")
    if not isinstance(transcript, list) or not isinstance(rules, list) or not isinstance(expected_events, list):
        return []
    if not transcript or not rules:
        return []
    if len(transcript) > MAX_HOOK_ITEMS or len(rules) > MAX_HOOK_ITEMS or len(expected_events) > MAX_HOOK_ITEMS:
        return [_check("hook_input_count_within_limit", False, limit=MAX_HOOK_ITEMS)]

    entries = [
        item
        for item in transcript
        if isinstance(item, dict)
        and isinstance(item.get("event"), str)
        and isinstance(item.get("content"), str)
        and len(item["content"]) <= MAX_HOOK_CONTENT_CHARS
    ]
    names = [rule.get("name") for rule in rules if isinstance(rule, dict)]
    invalid_patterns: list[str] = []
    unmatched_rules: list[str] = []
    rule_events: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            invalid_patterns.append("<non-object>")
            continue
        name = str(rule.get("name", "<unnamed>"))
        event = rule.get("event")
        pattern = rule.get("pattern")
        if not isinstance(event, str) or not isinstance(pattern, str):
            invalid_patterns.append(name)
            continue
        # Hook patterns are untrusted input. Keep matching in a deliberately small,
        # non-grouping subset so nested quantifiers/backreferences cannot cause ReDoS.
        if (
            len(pattern) > MAX_HOOK_PATTERN_CHARS
            or any(token in pattern for token in ("(", ")", "{", "}", "|"))
            or re.search(r"\\[1-9]", pattern)
        ):
            invalid_patterns.append(name)
            continue
        rule_events.add(event)
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            invalid_patterns.append(name)
            continue
        if not any(item["event"] == event and compiled.search(item["content"]) for item in entries):
            unmatched_rules.append(name)
    transcript_events = {item["event"] for item in entries}
    missing_transcript_events = [event for event in expected_events if event not in transcript_events]
    missing_rule_events = [event for event in expected_events if event not in rule_events]
    return [
        _check("transcript_entries_are_structured", len(entries) == len(transcript)),
        _check("hook_names_are_unique", len(names) == len(rules) and all(names) and len(names) == len(set(names))),
        _check("hook_patterns_compile", not invalid_patterns, invalid_rules=invalid_patterns),
        _check("expected_events_are_covered", not missing_transcript_events and not missing_rule_events,
               missing_transcript_events=missing_transcript_events, missing_rule_events=missing_rule_events),
        _check("hook_rules_match_evidence", not unmatched_rules, unmatched_rules=unmatched_rules),
    ]


ANALYZERS: dict[str, Analyzer] = {
    "agent_definition": _agent_definition_checks,
    "plugin_manifest": _plugin_manifest_checks,
    "skill_review": _skill_review_checks,
    "skill_analysis": _skill_analysis_checks,
    "skill_comparison": _skill_comparison_checks,
    "skill_grade": _skill_grade_checks,
    "hook_candidate": _hook_candidate_checks,
}


class SelfDevSpecialist(AgentBase):
    """Shared evidence and HP semantics for read-only self-development checks."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(self.profile.agent_id, self.profile.name, "self_dev", generation)
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][self_dev] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.evidence_fields if supplied.get(field) is not None and supplied.get(field) != ""]
        missing = [field for field in self.profile.evidence_fields if field not in present]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
            "tooling_scope_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        checks = ANALYZERS[self.profile.analyzer](supplied)
        return {
            "verified": bool(checks),
            "verified_by": "deterministic_recomputation" if checks else "none",
            "passed": all(check["passed"] for check in checks) if checks else False,
            "checks": checks,
            "note": "" if checks else "No checkable evidence was supplied; no verification claim was made.",
        }

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
                "tooling_scope_only": True,
            }
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        evidence = task.get("evidence") if "evidence" in task else params.get("evidence")
        try:
            report = self.build_evidence_report(evidence)
            response: dict[str, Any] = {
                "status": "ok" if report["status"] == "ready" else "needs_human",
                "report": report,
                "tooling_scope_only": True,
            }
            if task_type == self.profile.audit_action:
                response["verification"] = self.run_checks(evidence)
                if report["status"] == "ready" and response["verification"]["passed"] is not True:
                    # A failed or unverifiable check must never surface as "ok" to the Governor.
                    response["status"] = "needs_human" if not response["verification"]["verified"] else "failed"
            if task_type == self.profile.primary_action:
                earned = report["status"] == "ready"
            else:
                verification = response["verification"]
                earned = verification["verified"] is True and verification["passed"] is True
            if earned:
                self.award_points(20, f"{task_type}_verified")
            return response
        except Exception as exc:
            logger.error("[VECTOR][self_dev] {} failed: {}", self.name, exc)
            self.deduct_points(30, "self_dev_specialist_task_failed")
            return {"status": "error", "error": str(exc), "tooling_scope_only": True}


def _profile(
    name: str,
    slug: str,
    primary: str,
    audit: str,
    evidence: tuple[str, ...],
    deliverable: str,
    analyzer: str,
) -> SpecialistProfile:
    return SpecialistProfile(name, f"{slug}_001", primary, audit, evidence, deliverable, analyzer)


class AgentCreator(SelfDevSpecialist):
    profile = _profile(
        "AgentCreator", "agent_creator", "agent_creation_brief", "agent_definition_check",
        ("agent_spec", "source_code"), "VECTOR tooling-agent definition brief", "agent_definition",
    )


class PluginValidator(SelfDevSpecialist):
    profile = _profile(
        "PluginValidator", "plugin_validator", "plugin_validation_brief", "plugin_manifest_check",
        ("plugin_json", "package_files"), "plugin manifest validation brief", "plugin_manifest",
    )


class SkillReviewer(SelfDevSpecialist):
    profile = _profile(
        "SkillReviewer", "skill_reviewer", "skill_review_brief", "skill_structure_check",
        ("skill_document", "required_sections"), "skill structure review brief", "skill_review",
    )


class SkillAnalyzer(SelfDevSpecialist):
    profile = _profile(
        "SkillAnalyzer", "skill_analyzer", "skill_analysis_brief", "skill_analysis_check",
        ("skill_document", "expected_resources"), "skill structure analysis brief", "skill_analysis",
    )


class SkillComparator(SelfDevSpecialist):
    profile = _profile(
        "SkillComparator", "skill_comparator", "skill_comparison_brief", "skill_comparison_check",
        ("baseline_skill", "candidate_skill", "expectations"), "skill revision comparison brief", "skill_comparison",
    )


class SkillGrader(SelfDevSpecialist):
    profile = _profile(
        "SkillGrader", "skill_grader", "skill_grading_brief", "skill_grade_check",
        ("candidate_text", "criteria", "passing_score"), "criteria-based skill grade brief", "skill_grade",
    )


class ConversationAnalyzer(SelfDevSpecialist):
    profile = _profile(
        "ConversationAnalyzer", "conversation_analyzer", "hook_conversation_brief", "hook_candidate_check",
        ("transcript", "hook_rules", "expected_events"), "conversation-derived hook coverage brief", "hook_candidate",
    )


SPECIALIST_CLASSES: tuple[type[SelfDevSpecialist], ...] = (
    AgentCreator,
    PluginValidator,
    SkillReviewer,
    SkillAnalyzer,
    SkillComparator,
    SkillGrader,
    ConversationAnalyzer,
)


if __name__ == "__main__":
    import asyncio

    async def _smoke() -> None:
        skill = (
            "---\nname: smoke-skill\ndescription: Deterministic smoke fixture.\n---\n"
            "# Smoke\n## Steps\n1. Check evidence.\n## Verification\nConfirm pass.\n"
        )
        examples = {
            "AgentCreator": {
                "agent_spec": {"name": "Smoke", "agent_id": "smoke_001", "district": "self_dev",
                               "capabilities": ["smoke_check"]},
                "source_code": (
                    "from core.city.agent_base import AgentBase\n"
                    "class Smoke(AgentBase):\n"
                    "    async def run(self, task):\n"
                    "        return {'status': 'ok'}\n"
                ),
            },
            "PluginValidator": {
                "plugin_json": {"name": "smoke-plugin", "version": "1.0.0", "description": "Smoke fixture",
                                "entrypoint": "server.py", "permissions": ["read_tooling"]},
                "package_files": [".codex-plugin/plugin.json", "server.py"],
            },
            "SkillReviewer": {"skill_document": skill, "required_sections": ["Steps", "Verification"]},
            "SkillAnalyzer": {"skill_document": skill, "expected_resources": []},
            "SkillComparator": {
                "baseline_skill": "# Before", "candidate_skill": "# After\nVerified",
                "expectations": {"required_additions": ["Verified"], "required_removals": []},
            },
            "SkillGrader": {
                "candidate_text": "deterministic evidence", "criteria": [
                    {"name": "grounding", "weight": 1, "required_terms": ["deterministic evidence"]}
                ], "passing_score": 100,
            },
            "ConversationAnalyzer": {
                "transcript": [{"event": "user_message", "content": "run tests"}],
                "hook_rules": [{"name": "test-reminder", "event": "user_message", "pattern": "run tests"}],
                "expected_events": ["user_message"],
            },
        }
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            brief = await specialist.run({"type": specialist.profile.primary_action, "evidence": {}})
            check = await specialist.run({"type": specialist.profile.audit_action, "evidence": {}})
            assert brief["status"] == "needs_human"
            assert check["verification"]["verified"] is False
            assert specialist.health_points == 500
            verified = specialist_class()
            result = await verified.run({
                "type": verified.profile.audit_action,
                "evidence": examples[specialist_class.__name__],
            })
            assert result["verification"]["passed"] is True
            assert verified.health_points > 500
        logger.info("[VECTOR][self_dev] smoke check passed for {} specialists", len(SPECIALIST_CLASSES))

    asyncio.run(_smoke())
