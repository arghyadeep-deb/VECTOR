"""
Test Engineer — TDD specialist, test strategy, coverage analysis, test writing.
Loaded from: vectorcode/agents/vector-test-engineer.md
District: qa
"""
import asyncio

from loguru import logger
from core.city.prompt_agent import PromptAgent


class TestEngineer(PromptAgent):
    """
    Test-driven development specialist. Writes tests for existing code,
    designs test strategies, improves coverage. Different from test_results_analyzer
    (which reads results) — this WRITES tests.
    Powered by vector-test-engineer.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-test-engineer.md", "test_engineer_001", "qa")
        self.capabilities = [
            "generate", "coverage_gaps", "test_write", "test_strategy",
        ]

    async def generate_tests(self, code: str, filepath: str = "", framework: str = "pytest") -> str:
        """Generate test cases for a given code snippet."""
        query = (
            f"Write {framework} tests for this code. Cover: happy path, edge cases, "
            f"error cases, boundary values. Each test must be independent and fast.\n\n"
            f"{'File: ' + filepath if filepath else ''}\n"
            f"```python\n{code[:3000]}\n```\n\n"
            f"Return ONLY the test code, no explanation."
        )
        return await self.ask(query, timeout=45.0)

    async def analyze_test_coverage_gaps(self, source_code: str, existing_tests: str) -> str:
        """Find what's NOT tested in the existing test suite."""
        query = (
            f"Analyze test coverage gaps. What code paths, edge cases, and error conditions "
            f"are NOT covered by the existing tests?\n\n"
            f"Source code:\n```python\n{source_code[:2000]}\n```\n\n"
            f"Existing tests:\n```python\n{existing_tests[:2000]}\n```\n\n"
            f"List: untested function, missing scenario, suggested test name, priority (P0/P1/P2)"
        )
        return await self.ask(query, timeout=40.0)

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
            if task_type == "generate":
                tests = await self.generate_tests(
                    task.get("code", ""), task.get("filepath", ""), task.get("framework", "pytest")
                )
                self.award_points(30, "tests_generated")
                return {"status": "ok", "tests": tests}
            elif task_type == "coverage_gaps":
                gaps = await self.analyze_test_coverage_gaps(
                    task.get("source", ""), task.get("tests", "")
                )
                self.award_points(25, "coverage_gaps_analyzed")
                return {"status": "ok", "gaps": gaps}
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][test_engineer] {}", e)
            self.deduct_points(30, "test_generation_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = TestEngineer()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        print("test_engineer.py OK")
    asyncio.run(_smoke())
