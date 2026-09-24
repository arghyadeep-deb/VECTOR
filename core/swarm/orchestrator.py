"""
SwarmOrchestrator — central dispatch for VECTOR's multi-agent swarm.

Routes tasks to the best district/swarm, decomposes specs into parallel
sub-tasks, and collects results. Supports synchronous dispatch and
async parallel execution across all available agent pools.

Usage:
    from core.swarm.orchestrator import get_orchestrator
    orchestrator = get_orchestrator()
    result = await orchestrator.dispatch("backend", {"query": "Design auth system"})
    results = await orchestrator.execute_spec("specs-03-personality-engine/SPEC.md")
"""
from __future__ import annotations

__all__ = [
    "get_orchestrator",
    "SwarmOrchestrator",
]


import asyncio
import json
import re
from pathlib import Path
from typing import Any


from loguru import logger
from core.config import CONFIG

# ── District → Swarm class mapping ────────────────────────────────────────
DISTRICT_SWARMS: dict[str, str] = {
    "ops": "districts.ops.agent:OpsSwarm",
    "coding": "districts.coding.agent:CodingSwarm",
    "qa": "districts.qa.agent:QASwarm",
    "research": "districts.research.agent:ResearchSwarm",
    "finance": "districts.finance.agent:FinanceSwarm",
}

# Districts using GenericSwarm auto-discovery (no custom agent.py needed)
GENERIC_DISTRICTS: list[str] = [
    "security", "governance", "marketing",
 "design",
 "communications",
    "data_analytics", "startups", "skills", "content",
    "languages", "learning", "news_trends", "intelligence",
    "pattern_detective", "personal_growth", "privacy",
    "reflection", "relationships", "memory_curator",
    "health", "projects", "time_calendar", "calls",
    "agency", "investment", "interview_prep", "karpathy_lab",
]

# ── Cross-district routing — task type → best district ────────────────────
TASK_TO_DISTRICT: dict[str, str] = {
    # ── Engineering (broad architecture, AI, data, infra) ────────────────────

    # ── Coding (specialized .md + Python agents for hands-on code work) ──────
    "code_review": "coding",
    "refactor": "coding",
    "bug_hunt": "coding",
    "bug": "coding",
    "frontend_dev": "coding",
    "frontend": "coding",
    "database": "coding",
    "mlops": "coding",
    "conductor": "coding",
    "code_intel": "coding",
    "gui_automation": "coding",
    "onboarding": "coding",
    "minimal_change": "coding",
    "code_explore": "coding",
    "performance_opt": "coding",
    "performance": "coding",
    "git": "coding",
    "test_writing": "coding",

    # ── Testing (QA, verification, benchmarking) ─────────────────────────────
    "qa": "qa",
    "unit_test": "qa",
    "integration_test": "qa",
    "e2e_test": "qa",
    "regression": "qa",
    "benchmark": "qa",
    "perf_test": "qa",
    "evidence": "qa",
    "model_qa": "qa",
    "silent_failure": "qa",
    "tool_eval": "qa",
    "workflow_audit": "qa",

    # ── Ops (incident, deploy, monitor) ──────────────────────────────────────
    "incident": "ops",
    "monitoring": "ops",
    "deploy": "ops",
    "backup": "ops",
    "restart": "ops",
    "post_mortem": "ops",
    "classify_error": "ops",

    # ── Research (deep research, news, web, papers, social mining) ───────────
    "research": "research",
    "deep_research": "research",
    "paper": "research",
    "reddit": "research",
    "web_scout": "research",
    "stealth": "research",
    "cli_adapter": "research",

    # ── Finance (expenses, budget, tax, UPI, FP&A) ──────────────────────────
    "expense": "finance",
    "budget": "finance",
    "tax": "finance",
    "upi": "finance",
    "fpa": "finance",
    "llm_cost": "finance",
    "financial_analysis": "finance",
    "investment_research": "finance",
    "bookkeeping": "finance",

    # ── Product (strategy, sprint, feedback) ─────────────────────────────────

    # ── Security (audit, threat detection, privacy) ──────────────────────────
    "security_audit": "security",
    "threat_detection": "security",
    "malware": "security",
    "data_redact": "security",
    "node_guard": "security",

    # ── Governance (council, policy, compliance) ─────────────────────────────
    "governance": "governance",
    "council": "governance",
    "policy": "governance",
    "compliance": "governance",
    "llm_council": "governance",

    # ── Marketing (SEO, social, content, ads) ────────────────────────────────
    "seo": "marketing",
    "social_media": "marketing",
    "content_marketing": "marketing",
    "ads": "marketing",
    "growth": "marketing",
    "brand": "marketing",

    # ── Sales (outreach, pipeline, proposals) ────────────────────────────────

    # ── Design (UI/UX, visual, spatial) ──────────────────────────────────────
    "ui": "design",
    "ux": "design",
    "visual_design": "design",

    # ── Support (responder, analytics, legal) ────────────────────────────────

    # ── Miscellaneous districts ──────────────────────────────────────────────
    "communications": "communications",
    "startup": "startups",
    "skills": "skills",
    "content_creation": "content",
    "languages": "languages",
    "learning": "learning",
    "news": "news_trends",
    "intel": "intelligence",
    "patterns": "pattern_detective",
    "personal_growth": "personal_growth",
    "privacy": "privacy",
    "reflection": "reflection",
    "relationships": "relationships",
    "memory": "memory_curator",
    "health": "health",
    "projects": "projects",
    "calendar": "time_calendar",
    "calls": "calls",
    "agency": "agency",
    "investment": "investment",
    "interview_prep": "interview_prep",
    "karpathy": "karpathy_lab",
}


class SwarmOrchestrator:
    """Central dispatcher — routes tasks to district swarms, executes specs."""

    def __init__(self):
        self._swarms: dict[str, Any] = {}
        self._loaded = False
        logger.info("[SwarmOrchestrator] initialized")

    async def load_all(self) -> int:
        """Lazy-load all district swarms. Returns number loaded."""
        count = 0
        for district, import_path in DISTRICT_SWARMS.items():
            if district in self._swarms:
                continue
            try:
                module_path, class_name = import_path.split(":", 1)
                module = __import__(module_path, fromlist=[class_name])
                cls = getattr(module, class_name)
                instance = cls()
                self._swarms[district] = instance
                count += 1
                logger.debug("[SwarmOrchestrator] loaded swarm: {} ({})", district, class_name)
            except Exception as e:
                logger.debug("[SwarmOrchestrator] skip {}: {}", district, e)

        # Load generic swarms for remaining districts
        from core.swarm.generic_swarm import GenericSwarm
        for district in GENERIC_DISTRICTS:
            if district in self._swarms:
                continue
            try:
                instance = GenericSwarm(district)
                self._swarms[district] = instance
                count += 1
                logger.debug("[SwarmOrchestrator] loaded generic swarm: {}", district)
            except Exception as e:
                logger.debug("[SwarmOrchestrator] skip generic {}: {}", district, e)

        self._loaded = count > 0
        logger.info("[SwarmOrchestrator] {} district swarms loaded", count)
        return count

    def get_swarm(self, district: str) -> Any | None:
        """Get a loaded swarm by district name."""
        return self._swarms.get(district)

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route a task to the best district swarm. Fallback chain if none matches."""
        if not self._loaded:
            await self.load_all()

        district = TASK_TO_DISTRICT.get(task_type)
        if district and district in self._swarms:
            swarm = self._swarms[district]
            try:
                if hasattr(swarm, "dispatch"):
                    return await swarm.dispatch(task_type, params)
                return await swarm.run({"type": task_type, **params})
            except Exception as e:
                logger.warning("[SwarmOrchestrator] {} dispatch failed: {}", district, e)

        # Fallback: try all swarms in order
        for dist, swarm in self._swarms.items():
            try:
                if hasattr(swarm, "dispatch"):
                    return await swarm.dispatch(task_type, params)
                return await swarm.run({"type": task_type, **params})
            except Exception:
                continue

        return {"status": "error", "error": f"No swarm handled task_type='{task_type}'"}

    async def parallel_dispatch(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Dispatch multiple tasks in parallel. Each task: {task_type, params, ...}."""
        if not self._loaded:
            await self.load_all()

        async def _run_one(task: dict) -> dict:
            task_type = task.get("task_type", task.get("type", "default"))
            params = {k: v for k, v in task.items() if k not in ("task_type", "type")}
            result = await self.dispatch(task_type, params)
            return {"task": task, "result": result}

        tasks_coros = [_run_one(t) for t in tasks]
        return await asyncio.gather(*tasks_coros, return_exceptions=True)

    async def execute_spec(self, spec_path: str | Path) -> dict[str, Any]:
        """Parse a SPEC.md and dispatch all implementation tasks in parallel.

        Returns consolidated results dict with per-task status.
        """
        spec_path = Path(spec_path)
        if not spec_path.exists():
            return {"status": "error", "error": f"Spec not found: {spec_path}"}

        tasks = self._parse_spec_tasks(spec_path)
        if not tasks:
            return {"status": "error", "error": "No implementable tasks found in spec"}

        logger.info("[SwarmOrchestrator] executing spec: {} ({} tasks)", spec_path.name, len(tasks))
        results = await self.parallel_dispatch(tasks)
        return {
            "status": "ok",
            "spec": spec_path.name,
            "total_tasks": len(tasks),
            "results": results,
        }

    def _parse_spec_tasks(self, spec_path: Path) -> list[dict[str, Any]]:
        """Extract implementation tasks from a SPEC.md file.

        Parses 'Implementation Steps' section and 'Files to Create/Modify'
        to build concrete tasks for agent dispatch.
        """
        text = spec_path.read_text(encoding="utf-8", errors="replace")
        tasks: list[dict[str, Any]] = []

        # Extract files to create/modify
        file_section = self._extract_section(text, "Files to Create", "Files to Modify")
        if file_section:
            for line in file_section.splitlines():
                line = line.strip()
                if line.startswith("- `") and "`" in line[3:]:
                    file_path = line.split("`")[1]
                    ext = Path(file_path).suffix
                    task_type = {
                        ".py": "backend",
                        ".ts": "frontend",
                        ".tsx": "frontend",
                        ".js": "frontend",
                        ".json": "data",
                        ".yaml": "devops",
                        ".yml": "devops",
                        ".toml": "devops",
                        ".md": "technical_writing",
                    }.get(ext, "backend")
                    tasks.append({
                        "task_type": task_type,
                        "query": f"Create file: {file_path}",
                        "context": f"From spec: {spec_path.name}",
                        "file_path": file_path,
                        "action": "create",
                    })

        # Extract implementation steps
        steps_section = self._extract_section(text, "Implementation Steps", "Success Criteria")
        if steps_section:
            for line in steps_section.splitlines():
                line = line.strip()
                if re.match(r"^\*\*Step\s+\d+", line):
                    tasks.append({
                        "task_type": "backend",
                        "query": line,
                        "context": f"Implementation step from {spec_path.name}",
                        "action": "implement",
                    })

        return tasks

    @staticmethod
    def _extract_section(text: str, start_header: str, end_header: str) -> str:
        """Extract text between two markdown section headers."""
        pattern = rf"(?:^|## )\s*{re.escape(start_header)}.*?\n(.*?)(?:\n## |\Z)"
        import re as _re
        match = _re.search(pattern, text, _re.DOTALL | _re.MULTILINE)
        if match:
            content = match.group(1)
            # Truncate at the next ## section
            end = content.find("\n## ")
            if end != -1:
                content = content[:end]
            return content.strip()
        return ""


_orchestrator_instance: SwarmOrchestrator | None = None


def get_orchestrator() -> SwarmOrchestrator:
    """Global singleton accessor."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = SwarmOrchestrator()
    return _orchestrator_instance


if __name__ == "__main__":
    async def _smoke():
        import sys as _sys
        _sys.stdout.reconfigure(encoding="utf-8")

        orch = get_orchestrator()
        count = await orch.load_all()
        print(f"[SwarmOrchestrator] {count} swarms loaded")

        result = await orch.dispatch("backend", {"query": "Design a database schema"})
        print(f"[SwarmOrchestrator] dispatch: {result.get('status')}")

        parallel_tasks = [
            {"task_type": "backend", "query": "Design auth API"},
            {"task_type": "api_testing", "query": "Test the auth API"},
            {"task_type": "devops", "query": "Write deployment config"},
        ]
        results = await orch.parallel_dispatch(parallel_tasks)
        print(f"[SwarmOrchestrator] parallel: {len(results)} tasks completed")
        for r in results:
            if isinstance(r, dict) and "result" in r:
                print(f"  - {r['task'].get('task_type')}: {r['result'].get('status')}")

        print("SwarmOrchestrator OK")

    asyncio.run(_smoke())
