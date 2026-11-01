"""Skill execution sandbox — runs VECTOR skills via VectorSandbox with gateway oversight.

Each skill is classified by the PermissionGateway before execution.
Skills run through VectorSandbox, which uses an isolated container when
available and otherwise falls back to a subprocess. Safe here because this
runner always executes VECTOR's own fixed verification script
(_build_skill_verification_code), never caller-supplied skill content.

Usage:
    from core.sandbox.skill_sandbox import SkillSandboxRunner, SkillSandboxResult
    runner = SkillSandboxRunner()
    result = await runner.execute_skill(skill_entry)
"""
from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
from pathlib import Path


from loguru import logger
from core.sandbox.vector_sandbox import VectorSandbox, SandboxResult, get_sandbox
from core.loop.permission_gateway import PermissionGateway

__all__ = [
    "SkillSandboxResult",
    "SkillSandboxRunner",
]

# Map skill category → gateway action_type
# All skill categories resolve to a classified action the gateway already knows.
_CATEGORY_ACTION_MAP: dict[str, str] = {
    "security": "analyze_code",   # GREEN — read/analyse only
    "general":  "read_code",      # GREEN — read/analyse only
    "execution": "run_tests",     # YELLOW — runs code, notifies owner
    "coding":   "code_task",      # YELLOW
    "research": "search_web",     # GREEN
    "ops":      "run_tests",      # YELLOW
}
_DEFAULT_ACTION = "execute_code"  # RED — fallback for unknown categories


@dataclass
class SkillSandboxResult:
    skill_id: str
    permission_level: str          # GREEN / YELLOW / RED / FORBIDDEN / UNKNOWN
    approved: bool                 # True if gateway allows execution (not RED/FORBIDDEN)
    sandbox_result: SandboxResult | None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.approved and self.sandbox_result is not None and self.sandbox_result.success


class SkillSandboxRunner:
    """Classifies and executes skills via VectorSandbox under gateway oversight."""

    def __init__(
        self,
        gateway: PermissionGateway | None = None,
        sandbox: VectorSandbox | None = None,
    ) -> None:
        self._gateway = gateway or PermissionGateway()
        self._sandbox = sandbox or get_sandbox()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_skill(self, category: str) -> tuple[str, str]:
        """Return (action_type, gateway_level) for a skill category."""
        action_type = _CATEGORY_ACTION_MAP.get(category, _DEFAULT_ACTION)
        level = self._gateway._classify(action_type)
        return action_type, level

    async def execute_skill(self, skill_entry: dict) -> SkillSandboxResult:
        """Run a skill entry from the skills manifest inside VectorSandbox.

        The skill code is a minimal Python script that:
        1. Receives host-read SKILL.md data
        2. Extracts name, description, triggers
        3. Returns a JSON summary

        This validates the sandbox pipeline end-to-end without requiring
        LLM API keys or network access.
        """
        skill_id = skill_entry.get("skill_id", "unknown")
        category = skill_entry.get("category", "general")
        skill_md_path = skill_entry.get("skill_md_path", "")

        action_type, level = self.classify_skill(category)
        logger.info(
            "[VECTOR][skill_sandbox] skill={} category={} action={} level={}",
            skill_id, category, action_type, level,
        )

        if level == "FORBIDDEN":
            return SkillSandboxResult(skill_id, "FORBIDDEN", False, None, "Action permanently forbidden")

        # RED actions require human approval — block in sandbox context.
        # Callers needing RED execution must go through the full gateway.execute() flow.
        if level == "RED":
            logger.warning(
                "[VECTOR][skill_sandbox] RED skill blocked — use gateway.execute() for full approval flow: {}",
                skill_id,
            )
            return SkillSandboxResult(skill_id, "RED", False, None, "RED action requires owner approval")

        approved = level in ("GREEN", "YELLOW")

        # Resolve and read the trusted manifest file on the host. An isolated
        # container cannot and should not resolve arbitrary host paths.
        _project_root = Path(__file__).parent.parent.parent
        abs_md_path = str(_project_root / skill_md_path) if skill_md_path else ""
        md_path = Path(abs_md_path) if abs_md_path else None
        md_exists = md_path is not None and md_path.exists()
        md_content = (
            md_path.read_text(encoding="utf-8", errors="replace")
            if md_exists
            else ""
        )
        md_size = md_path.stat().st_size if md_exists else 0

        # Build the sandboxed script — uses only stdlib, no network, no LLM
        safe_code = _build_skill_verification_code(
            skill_id,
            category,
            md_exists,
            md_size,
            md_content,
        )

        sandbox_result = await self._sandbox.run_code_safe(safe_code, timeout=15.0)

        logger.info(
            "[VECTOR][skill_sandbox] skill={} level={} sandbox_ok={} elapsed={:.2f}s",
            skill_id, level, sandbox_result.success, sandbox_result.elapsed_secs,
        )
        return SkillSandboxResult(skill_id, level, approved, sandbox_result)

    async def execute_batch(self, skill_entries: list[dict]) -> list[SkillSandboxResult]:
        """Execute multiple skills concurrently."""
        return list(await asyncio.gather(*(self.execute_skill(e) for e in skill_entries)))


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_skill_verification_code(
    skill_id: str,
    category: str,
    md_exists: bool,
    md_size: int,
    md_content: str,
) -> str:
    """Return Python source that verifies a skill manifest entry inside the sandbox."""
    encoded_content = json.dumps(md_content)
    return f"""\
import json, sys

skill_id = {json.dumps(skill_id)}
category = {json.dumps(category)}
md_exists = {md_exists!r}
md_size = {md_size!r}
text = json.loads({json.dumps(encoded_content)})

result = {{
    "skill_id": skill_id,
    "category": category,
    "md_exists": md_exists,
    "md_size": md_size,
    "status": "verified",
}}

if md_exists:
    # Extract first trigger line as smoke test
    triggers = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("-")]
    result["trigger_count"] = len(triggers)
    result["name_line"] = next(
        (ln.strip() for ln in text.splitlines() if ln.strip().startswith("#")), ""
    )

print(json.dumps(result))
"""


if __name__ == "__main__":
    import asyncio, json as _json

    async def _smoke():
        runner = SkillSandboxRunner()
        entries = [
            {
                "skill_id": "sherlock",
                "category": "security",
                "skill_md_path": "vectorcode/src/skills/optional/security/sherlock/SKILL.md",
            },
            {
                "skill_id": "dogfood",
                "category": "general",
                "skill_md_path": "vectorcode/src/skills/dogfood/SKILL.md",
            },
            {
                "skill_id": "systematic-debugging",
                "category": "execution",
                "skill_md_path": "vectorcode/src/skills/software-development/systematic-debugging/SKILL.md",
            },
        ]
        for entry in entries:
            r = await runner.execute_skill(entry)
            print(f"{r.skill_id}: level={r.permission_level} approved={r.approved} ok={r.succeeded}")
            if r.sandbox_result and r.sandbox_result.stdout:
                print("  out:", r.sandbox_result.stdout.strip()[:120])

    asyncio.run(_smoke())
    print("skill_sandbox.py OK")
