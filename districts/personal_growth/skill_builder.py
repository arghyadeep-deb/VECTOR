"""SkillBuilder — turns VECTOR's own repeated task patterns into real,
Claude-Code-compatible SKILL.md files.

Consumes stable Pattern records from vectorcode.src.reasoning_bank.PatternLearner
(already live in core/loop/decision_engine.py, tracking real task repetition
across every reasoning chain VECTOR stores) -- no new pattern-tracking system
is built here. A pattern only becomes a skill once it has already crossed
PatternLearner's own "stable" threshold (repeated >= min_usages_for_stable
times with a real reward above quality_threshold, see reasoning_bank.py's
PatternConfig) -- this agent never judges eligibility with an LLM, only
deterministic threshold checks re-applied to the caller-supplied evidence.

Skills are written to VECTOR's own directory (data/vector_skills/), never
into Claude's own .claude/skills/ -- an explicit owner choice: this is
VECTOR's own accumulated procedural knowledge, in the same SKILL.md format,
readable by anyone (including Claude, on request) but not auto-discovered
by Claude Code's own skill menu.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return slug[:60] or "unnamed-pattern"


@dataclass(frozen=True)
class SkillBuildProfile:
    """Bounded contract, matching the evidence-gated pattern used across
    the self-dev program: brief reports evidence presence honestly, check
    performs the real, deterministic work."""

    name: str
    agent_id: str
    brief_action: str
    check_action: str
    required_fields: tuple[str, ...]
    deliverable: str


class SkillBuilder(AgentBase):
    """Deterministically converts caller-supplied stable-pattern records
    into real SKILL.md files in VECTOR's own skills directory."""

    profile = SkillBuildProfile(
        "SkillBuilder",
        "skill_builder_001",
        "learned_pattern_brief",
        "learned_pattern_build",
        ("patterns",),
        "SKILL.md files built from VECTOR's own stable, repeated-task patterns",
    )

    def __init__(
        self,
        generation: int = 1,
        ghost: dict[str, Any] | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="personal_growth",
            generation=generation,
        )
        self.capabilities = [self.profile.brief_action, self.profile.check_action]
        if skills_dir is not None:
            self._skills_dir = skills_dir
        else:
            from core.runtime_paths import data_path
            self._skills_dir = data_path("vector_skills")
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][skill_builder] initialized — skills_dir={}", self._skills_dir)

    # ── evidence-gated brief ────────────────────────────────────────────────

    def _evidence_state(self, evidence: Any) -> tuple[dict[str, Any], list[str], list[str]]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [f for f in self.profile.required_fields if _has_value(supplied.get(f))]
        missing = [f for f in self.profile.required_fields if f not in present]
        return supplied, present, missing

    def build_brief(self, evidence: Any) -> dict[str, Any]:
        _, present, missing = self._evidence_state(evidence)
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.required_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "deterministic": True,
            "read_only": False,
        }

    # ── deterministic eligibility + rendering ───────────────────────────────

    @staticmethod
    def _is_eligible(
        pattern: dict[str, Any], min_usages: int, min_quality: float
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not pattern.get("stable"):
            reasons.append("pattern is not marked stable")
        usage_count = pattern.get("usage_count", 0)
        if usage_count < min_usages:
            reasons.append(f"usage_count {usage_count} < required {min_usages}")
        quality_score = pattern.get("quality_score", 0.0)
        if quality_score < min_quality:
            reasons.append(f"quality_score {quality_score} < required {min_quality}")
        strategy = str(pattern.get("strategy", "")).strip()
        if len(strategy) < 20:
            reasons.append("strategy text too short (< 20 chars) to be a real skill body")
        return (not reasons), reasons

    @staticmethod
    def _render_skill_markdown(pattern: dict[str, Any], slug: str) -> str:
        task_type = str(pattern.get("task_type", "unknown"))
        usage_count = int(pattern.get("usage_count", 0))
        quality_score = float(pattern.get("quality_score", 0.0))
        strategy = str(pattern.get("strategy", "")).strip()

        description = (
            f"Auto-built from {usage_count} real repeated observations of "
            f"'{task_type}' tasks (quality {quality_score:.2f}). {strategy}"
        ).replace("\n", " ").strip()
        if len(description) > 400:
            description = description[:397].rstrip() + "..."
        # YAML frontmatter values must not contain unescaped colons/quotes
        # that would break parsing; keep this deterministic and simple by
        # stripping characters that would need real YAML escaping.
        description = description.replace('"', "'")

        title = task_type.replace("_", " ").replace("-", " ").strip().title() or "Untitled Pattern"
        built_at = datetime.now(UTC).isoformat()

        frontmatter = (
            "---\n"
            f"name: {slug}\n"
            f'description: "{description}"\n'
            "metadata:\n"
            "  source: vector-pattern-learner\n"
            f"  task_type: {task_type}\n"
            f"  usage_count: {usage_count}\n"
            f"  quality_score: {quality_score:.4f}\n"
            f"  built_at: {built_at}\n"
            "---\n"
        )
        body = (
            f"\n# {title}\n\n"
            f"Auto-built by VECTOR's SkillBuilder from {usage_count} real repeated "
            f"observations of this task type (pattern quality score {quality_score:.2f}). "
            f"This is VECTOR's own accumulated strategy from its ReasoningBank / "
            f"PatternLearner, not an LLM guess -- review before trusting it blindly on "
            f"a task materially different from what it was built from.\n\n"
            f"## Strategy\n\n{strategy}\n"
        )
        return frontmatter + body

    def build_from_patterns(
        self,
        patterns: list[Any],
        min_usages: int = 3,
        min_quality: float = 0.5,
    ) -> dict[str, Any]:
        """Real, deterministic work: write one SKILL.md per eligible
        caller-supplied pattern. Returns which were built vs. skipped and why."""
        built: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for pattern in patterns:
            if not isinstance(pattern, dict) or not _has_value(pattern.get("task_type")):
                skipped.append({"pattern": pattern, "reasons": ["malformed pattern: missing task_type"]})
                continue

            task_type = str(pattern["task_type"])
            slug = _slugify(task_type)
            eligible, reasons = self._is_eligible(pattern, min_usages, min_quality)
            if not eligible:
                skipped.append({"task_type": task_type, "slug": slug, "reasons": reasons})
                continue

            skill_dir = self._skills_dir / slug
            skill_path = skill_dir / "SKILL.md"
            markdown = self._render_skill_markdown(pattern, slug)
            try:
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(markdown, encoding="utf-8")
            except OSError as e:
                skipped.append({"task_type": task_type, "slug": slug, "reasons": [f"write failed: {e}"]})
                continue

            built.append({
                "task_type": task_type,
                "slug": slug,
                "path": str(skill_path),
                "usage_count": pattern.get("usage_count"),
                "quality_score": pattern.get("quality_score"),
            })

        return {"built": built, "skipped": skipped, "skills_dir": str(self._skills_dir)}

    # ── AgentBase run() dispatch ─────────────────────────────────────────────

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.brief_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }

        # 2026-09-30 (Phase 3 codebase audit finding): same bug class as
        # districts/agency/agency_specialists.py (same commit series) -- the
        # real governor dispatch shape nests evidence under task["params"],
        # but this method only ever read task.get("evidence") directly,
        # already fixed once, later, in districts/marketing/
        # marketing_specialists.py but never backported here. Same fix.
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        raw_evidence = task.get("evidence") or params.get("evidence")
        try:
            evidence, _, missing = self._evidence_state(raw_evidence)
            if task_type == self.profile.brief_action or missing:
                report = self.build_brief(evidence)
            else:
                patterns = evidence.get("patterns")
                if not isinstance(patterns, list) or not patterns:
                    report = {**self.build_brief(evidence), "status": "needs_human"}
                else:
                    min_usages = int(evidence.get("min_usages", 3))
                    min_quality = float(evidence.get("min_quality", 0.5))
                    result = self.build_from_patterns(patterns, min_usages, min_quality)
                    report = {
                        **result,
                        "persona": self.name,
                        "deliverable": self.profile.deliverable,
                        "status": "passed" if result["built"] else "needs_human",
                        "missing_evidence": [],
                        "deterministic": True,
                        "read_only": False,
                    }
            if report.get("status") in {"ready", "passed"}:
                built_count = len(report.get("built", [])) if "built" in report else 1
                self.award_points(10 * max(built_count, 1), f"{task_type}_completed")
            return {"status": "ok", "report": report}
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("[VECTOR][skill_builder] rejected evidence: {}", exc)
            return {
                "status": "ok",
                "report": {**self.build_brief(raw_evidence), "status": "needs_human", "validation_error": str(exc)},
            }
        except Exception as exc:
            logger.error("[VECTOR][skill_builder] failed: {}", exc)
            self.deduct_points(30, "skill_builder_task_failed")
            return {"status": "error", "error": str(exc)}


# ── bridge: real live PatternLearner -> caller-supplied evidence ───────────
# Kept as a module-level function, not a SkillBuilder method: the agent
# itself stays evidence-gated (only ever sees what a caller hands it,
# matching the pattern used throughout this program), while this bridge is
# the orchestration piece a periodic job (e.g. a reflect-time task) can call
# to fetch real patterns and hand them to the agent as evidence.

def collect_stable_patterns(task_type: str | None = None) -> list[dict[str, Any]]:
    """Read real stable patterns from the live PatternLearner (the same
    instance/store core.loop.decision_engine.DecisionEngine uses) and
    return them as plain dicts ready to pass as SkillBuilder evidence."""
    from vectorcode.src.reasoning_bank import PatternLearner

    learner = PatternLearner()
    return [p.to_dict() for p in learner.stable_patterns(task_type=task_type)]


if __name__ == "__main__":
    async def _smoke() -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            agent = SkillBuilder(skills_dir=Path(tmp))

            missing = await agent.run({"type": agent.profile.check_action, "evidence": {}})
            assert missing["report"]["status"] == "needs_human"

            pattern = {
                "task_type": "restart_stalled_worker",
                "strategy": "Check queue depth, send SIGTERM, relaunch the worker process.",
                "usage_count": 5,
                "quality_score": 0.8,
                "stable": True,
            }
            built = await agent.run({
                "type": agent.profile.check_action,
                "evidence": {"patterns": [pattern]},
            })
            assert built["report"]["status"] == "passed"
            assert built["report"]["built"]
            skill_path = Path(built["report"]["built"][0]["path"])
            assert skill_path.exists()
            content = skill_path.read_text(encoding="utf-8")
            assert "restart-stalled-worker" in content
            assert "Check queue depth" in content

        logger.info("[VECTOR][skill_builder] smoke check passed")

    asyncio.run(_smoke())
