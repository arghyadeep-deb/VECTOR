"""
Developer Advocate — DX engineering, technical tutorials, community building, TTFHW.
Loaded from: vectorcode/agents/vector-specialized-developer-advocate.md
District: coding
"""
import asyncio

from loguru import logger
from core.city.prompt_agent import PromptAgent


class DeveloperAdvocate(PromptAgent):
    """
    Developer experience engineering. Optimizes TTFHW (Time-To-First-Hello-World),
    writes tutorials, creates onboarding docs, builds developer community for
    VECTOR's public-facing work and Arghyadeep's personal brand.
    Powered by vector-specialized-developer-advocate.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-specialized-developer-advocate.md", "developer_advocate_001", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["tutorial", "dx_audit"]

    async def write_tutorial(self, topic: str, target_audience: str = "intermediate developers",
                              format: str = "blog") -> str:
        """Write a technical tutorial for a given topic."""
        query = (
            f"Write a {format}-style tutorial on: '{topic}'\n"
            f"Target audience: {target_audience}\n"
            f"Requirements:\n"
            f"- Working code examples (Python, VECTOR stack)\n"
            f"- Step-by-step with clear progression\n"
            f"- Explain WHY not just WHAT\n"
            f"- Reader should have working code within 10 minutes\n"
            f"- Include common mistakes and how to avoid them\n"
        )
        return await self.ask(query, timeout=60.0)

    async def audit_dx(self, readme_content: str, project_name: str = "VECTOR") -> dict:
        """Audit developer experience for a project."""
        query = (
            f"Audit the developer experience (DX) for {project_name}:\n\n"
            f"README:\n{readme_content[:2000]}\n\n"
            f"Rate 1-10 and give specific fixes for:\n"
            f"- Time-To-First-Hello-World (TTFHW)\n"
            f"- Prerequisites clarity\n"
            f"- Installation friction\n"
            f"- Error message quality\n"
            f"- Documentation completeness\n"
            f"- API/interface intuitiveness\n"
        )
        response = await self.ask(query, timeout=40.0)
        return {"status": "ok", "project": project_name, "dx_audit": response}

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        task = {**task, **(task.get("params") or {})}
        task_type = task.get("type", "ask")
        try:
            if task_type == "tutorial":
                content = await self.write_tutorial(
                    task.get("topic", "Building with VECTOR AI"),
                    task.get("audience", "intermediate developers"),
                    task.get("format", "blog"),
                )
                self.award_points(30, "tutorial_written")
                return {"status": "ok", "tutorial": content}
            elif task_type == "dx_audit":
                result = await self.audit_dx(
                    task.get("readme", ""), task.get("project", "VECTOR")
                )
                self.award_points(25, "dx_audited")
                return result
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][dev_advocate] {}", e)
            self.deduct_points(30, "advocacy_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = DeveloperAdvocate()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        print("developer_advocate.py OK")
    asyncio.run(_smoke())
