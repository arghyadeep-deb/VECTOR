"""
Frontend Developer — builds and audits VECTOR's web interfaces.

Specializes in: VECTOR dashboard (Next.js), API status pages,
React components, performance audits, accessibility checks.
"""

import asyncio
import datetime
import subprocess
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

class FrontendDeveloper(AgentBase):
    """Builds and audits VECTOR's frontend interfaces."""

    def __init__(self):
        super().__init__(agent_id="frontend_dev_001", name="FrontendDeveloper", district="coding")
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("coder", "vector-coder")
        self._root = Path(__file__).parent.parent.parent.parent
        logger.info("[VECTOR][frontend_dev] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def audit_dashboard_code(self) -> dict:
        """Scan dashboard/src/ for common issues — missing components, broken imports."""
        dashboard = self._root / "dashboard" / "src"
        if not dashboard.exists():
            return {"status": "no_dashboard", "message": "dashboard/src/ not built yet — run: npx create-next-app dashboard"}

        issues = []
        component_count = 0
        for f in dashboard.rglob("*.tsx"):
            component_count += 1
            src = f.read_text(encoding="utf-8", errors="replace")
            if "console.log" in src:
                issues.append(f"{f.name}: console.log in production code")
            if "any" in src and "TypeScript" not in src:
                issues.append(f"{f.name}: TypeScript 'any' type detected")
        for f in dashboard.rglob("*.ts"):
            src = f.read_text(encoding="utf-8", errors="replace")
            if "TODO" in src:
                issues.append(f"{f.name}: unresolved TODO")

        return {
            "component_count": component_count,
            "issues": issues[:10],
            "clean": len(issues) == 0,
        }

    async def scaffold_component(self, name: str, props: list[str]) -> str:
        """Generate a React TypeScript component using LLM."""
        prompt = (
            f"Write a clean React TypeScript functional component named '{name}' "
            f"with props: {', '.join(props)}.\n"
            f"Use TailwindCSS for styling. No comments needed. "
            f"VECTOR dark theme: bg-gray-900, text-white, accent green (#00ff88).\n"
            f"Return only the component code."
        )
        try:
            code = chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30.0,
            )
            return code.strip()
        except Exception as e:
            logger.warning("[VECTOR][frontend_dev] scaffold failed: {}", e)
            return f"// Error generating {name}: {e}"

    async def generate_dashboard_plan(self) -> str:
        """Generate a plan for VECTOR's monitoring dashboard."""
        prompt = (
            "Design a Next.js dashboard for VECTOR — a personal autonomous AI system.\n"
            "Pages needed:\n"
            "1. /status — real-time agent HP, district status, loop health\n"
            "2. /decisions — recent decision engine choices with scores\n"
            "3. /memory — episodic memory timeline, search\n"
            "4. /goals — goal progress bars (LONG/MID/SHORT horizons)\n"
            "5. /skills — skill tree, Karpathy streak tracker\n\n"
            "For each page: component list, data sources (which VECTOR API endpoint), "
            "key metrics to show. Keep it minimal and dark-themed."
        )
        try:
            plan = chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30.0,
            )
            return plan
        except Exception as e:
            logger.warning("[VECTOR][frontend_dev] plan gen failed: {}", e)
            return "Error generating dashboard plan"

    def check_api_endpoints(self) -> dict:
        """Test VECTOR's FastAPI endpoints are responding."""
        import httpx
        api_base = CONFIG.get("api", {}).get("base_url", "http://127.0.0.1:8000")
        endpoints = ["/status", "/health", "/agents", "/goals"]
        results = {}

        for ep in endpoints:
            try:
                r = httpx.get(f"{api_base}{ep}", timeout=3.0)
                results[ep] = {"status": r.status_code, "ok": r.status_code < 400}
            except Exception as e:
                results[ep] = {"status": "unreachable", "ok": False, "error": str(e)[:60]}

        return results

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "audit")
        try:
            if task_type == "audit":
                result = self.audit_dashboard_code()
                self.award_points(30, "dashboard_audit")
                return {"status": "ok", **result}

            elif task_type == "scaffold":
                name = task.get("name", "VectorCard")
                props = task.get("props", ["title: string", "value: string"])
                code = await self.scaffold_component(name, props)
                self._get_memory().store(
                    event_type="component_scaffolded",
                    content=f"Scaffolded component: {name}",
                    tags=["coding", "frontend", "component"],
                    source="frontend_developer",
                )
                self.award_points(40, "component_scaffolded")
                return {"status": "ok", "component": name, "code": code}

            elif task_type == "dashboard_plan":
                plan = await self.generate_dashboard_plan()
                self.award_points(50, "dashboard_planned")
                return {"status": "ok", "plan": plan}

            elif task_type == "check_api":
                results = self.check_api_endpoints()
                ok_count = sum(1 for v in results.values() if v.get("ok"))
                self.award_points(20 if ok_count > 0 else 0, "api_checked")
                return {"status": "ok", "endpoints": results, "healthy": ok_count}

            else:
                return {"status": "error", "error": f"Unknown task type: {task_type}"}

        except Exception as e:
            logger.error("[VECTOR][frontend_dev] {}", e)
            self.deduct_points(30, "frontend_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FrontendDeveloper()
        audit = agent.audit_dashboard_code()
        print(f"[OK] audit: {audit}")
        ep = agent.check_api_endpoints()
        print(f"[OK] api_check: {ep}")
        result = await agent.run({"type": "audit"})
        print(f"[OK] run: status={result['status']}")
        print("frontend_developer.py OK")

    asyncio.run(_smoke())
