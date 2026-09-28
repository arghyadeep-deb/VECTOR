"""Evidence-checked memory_curator specialists (SELF_DEV_P8_MEMORY_FINANCE_OPS).

Two selected personas from `.claude/agents/` (not found in this worktree; scope inferred from
persona name + the memory_curator domain, same disclosed limitation as SELF_DEV_P5_MARKETING):

* ``identity-graph-operator`` -> ``IdentityGraphOperator`` -- deduplicates supplied entity
  records by normalized match-field overlap. Real set/dict computation, no LLM.
* ``lsp-index-engineer`` -> ``LSPIndexEngineer`` -- indexes symbols in supplied Python source via
  the stdlib ``ast`` module and diffs against an optional expected-symbol list. Real static
  parsing, no LLM.

Both follow the same brief/check contract as the approved design/marketing specialist packages:
``<x>_brief`` reports evidence completeness, ``<x>_check`` is the verification action and never
asks a model whether the work is good -- it recomputes something from the supplied data. Neither
agent calls an LLM, so RULE 1 (session hydration before every LLM call) does not apply to either.
"""

from __future__ import annotations

import ast
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase


@dataclass(frozen=True)
class SpecialistProfile:
    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str


class MemoryCuratorSpecialist(AgentBase):
    """Base class: evidence-completeness brief + deterministic recomputation check."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="memory_curator",
            generation=generation,
        )
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][memory_curator_specialists] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [f for f in self.profile.evidence_fields if supplied.get(f)]
        missing = [f for f in self.profile.evidence_fields if not supplied.get(f)]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        raise NotImplementedError

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        evidence = task.get("evidence") or params.get("evidence")
        try:
            report = self.build_evidence_report(evidence)
            response: dict[str, Any] = {"status": "ok", "report": report}
            if task_type == self.profile.audit_action:
                response["verification"] = self.run_checks(evidence)
            verification = response.get("verification")
            if verification is None:
                earned = report["status"] == "ready"
            else:
                # A failed check is not completed work: HP only for a verified, non-failing check.
                earned = bool(verification.get("verified")) and verification.get("passed") is not False
            if earned:
                self.award_points(20, f"{task_type}_completed")
            return response
        except Exception as exc:
            logger.error("[VECTOR][memory_curator_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "memory_curator_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


def _normalize(value: Any) -> str:
    return str(value).strip().lower()


class IdentityGraphOperator(MemoryCuratorSpecialist):
    """Dedup candidate detection over caller-supplied identity records.

    Groups records by the normalized value of every field named in
    ``match_fields`` (all must match for a pair to cluster); records that
    share a cluster with >1 member are reported as duplicate candidates.
    Pure set/dict computation over the exact rows supplied -- nothing is
    fetched, inferred, or asked of a model.
    """

    profile = SpecialistProfile(
        "IdentityGraphOperator", "identity_graph_operator_001",
        "identity_graph_brief", "identity_dedup_check",
        ("entity_records", "match_fields"),
        "identity-graph deduplication brief",
    )

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        records = supplied.get("entity_records")
        match_fields = supplied.get("match_fields")
        if not isinstance(records, list) or not isinstance(match_fields, list) or not match_fields:
            return {"verified": False, "verified_by": "none", "clusters": [],
                    "note": "entity_records (list) and match_fields (non-empty list) both required"}

        clusters: dict[tuple[str, ...], list[Any]] = defaultdict(list)
        skipped = 0
        for row in records:
            if not isinstance(row, dict):
                skipped += 1
                continue
            # Review finding (verified real by Claude, 2026-09-29): row.get(f, "") only falls back to
            # "" when the key is absent -- a field explicitly present with value None stays None, and
            # _normalize(None) == str(None).strip().lower() == "none", a non-empty string. Two records
            # each missing the same field via an explicit null (not absence) both got key part "none"
            # and clustered together as a false-positive duplicate instead of being skipped as
            # incomplete evidence. Treat an explicit None the same as a missing field.
            raw_values = [row.get(f) for f in match_fields]
            if any(v is None for v in raw_values):
                skipped += 1
                continue
            key = tuple(_normalize(v) for v in raw_values)
            if any(not part for part in key):
                skipped += 1
                continue
            clusters[key].append(row.get("id", row))

        duplicate_clusters = [
            {"match_key": list(key), "record_ids": ids, "count": len(ids)}
            for key, ids in clusters.items() if len(ids) > 1
        ]
        return {
            "verified": True,
            "verified_by": "deterministic_recomputation",
            "records_considered": len(records) - skipped,
            "records_skipped": skipped,
            "duplicate_clusters": duplicate_clusters,
            "duplicate_cluster_count": len(duplicate_clusters),
        }


class LSPIndexEngineer(MemoryCuratorSpecialist):
    """Symbol index + diff over caller-supplied Python source, via ``ast``.

    Parses each supplied source string with ``ast.parse`` (real static
    analysis, not a model guess) and lists every top-level ``def``/``class``
    name. If the caller also supplies ``expected_symbols``, reports which
    are missing from the index and which indexed symbols are extra.
    """

    profile = SpecialistProfile(
        "LSPIndexEngineer", "lsp_index_engineer_001",
        "lsp_index_brief", "lsp_symbol_check",
        ("source_files",),
        "LSP symbol-index brief",
    )

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        files = supplied.get("source_files")
        if not isinstance(files, list) or not files:
            return {"verified": False, "verified_by": "none", "index": [],
                    "note": "source_files (non-empty list of {path, source}) required"}

        index: dict[str, list[str]] = {}
        parse_errors: list[dict[str, str]] = []
        all_symbols: set[str] = set()
        for f in files:
            if not isinstance(f, dict):
                continue
            path = str(f.get("path", "<unknown>"))
            source = str(f.get("source", ""))
            try:
                tree = ast.parse(source)
            except SyntaxError as e:
                parse_errors.append({"path": path, "error": str(e)})
                continue
            symbols = sorted({
                node.name for node in ast.iter_child_nodes(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            })
            index[path] = symbols
            all_symbols.update(symbols)

        expected = supplied.get("expected_symbols")
        missing: list[str] = []
        extra: list[str] = []
        if isinstance(expected, list) and expected:
            expected_set = {str(s) for s in expected}
            missing = sorted(expected_set - all_symbols)
            extra = sorted(all_symbols - expected_set)

        return {
            "verified": True,
            "verified_by": "ast_static_parse",
            "files_indexed": len(index),
            "parse_errors": parse_errors,
            "index": index,
            "missing_symbols": missing,
            "extra_symbols": extra,
            "passed": not missing and not parse_errors,
        }


SPECIALIST_CLASSES: tuple[type[MemoryCuratorSpecialist], ...] = (
    IdentityGraphOperator, LSPIndexEngineer,
)


if __name__ == "__main__":
    import asyncio
    import sys as _sys

    async def _smoke() -> None:
        _sys.stdout.reconfigure(encoding="utf-8")

        for cls in SPECIALIST_CLASSES:
            agent = cls()
            assert agent.health_points == 500
            assert agent.district == "memory_curator"
            brief = await agent.run({"type": agent.profile.primary_action, "evidence": {}})
            assert brief["status"] == "ok" and brief["report"]["missing_evidence"]
            check = await agent.run({"type": agent.profile.audit_action, "evidence": {}})
            assert check["verification"]["verified"] is False

        igo = IdentityGraphOperator()
        dup_result = await igo.run({
            "type": "identity_dedup_check",
            "evidence": {
                "match_fields": ["email"],
                "entity_records": [
                    {"id": "a1", "email": "Same@Example.com"},
                    {"id": "a2", "email": "same@example.com"},
                    {"id": "a3", "email": "different@example.com"},
                ],
            },
        })
        assert dup_result["verification"]["duplicate_cluster_count"] == 1
        assert dup_result["verification"]["duplicate_clusters"][0]["count"] == 2

        lie = LSPIndexEngineer()
        idx_result = await lie.run({
            "type": "lsp_symbol_check",
            "evidence": {
                "source_files": [{"path": "m.py", "source": "def foo():\n    pass\n\nclass Bar:\n    pass\n"}],
                "expected_symbols": ["foo", "baz"],
            },
        })
        v = idx_result["verification"]
        assert v["missing_symbols"] == ["baz"]
        assert v["extra_symbols"] == ["Bar"]
        assert v["passed"] is False

        bad_syntax = await lie.run({
            "type": "lsp_symbol_check",
            "evidence": {"source_files": [{"path": "broken.py", "source": "def (:"}]},
        })
        assert bad_syntax["verification"]["parse_errors"]

        logger.info("[VECTOR][memory_curator_specialists] smoke check passed")
        print("memory_curator_specialists.py OK")

    asyncio.run(_smoke())
