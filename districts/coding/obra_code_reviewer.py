"""
Obra Code Reviewer — second-opinion code reviewer with independent perspective.
Loaded from: vectorcode/agents/vector-obra-code-reviewer.md
District: coding
"""
import asyncio

from loguru import logger
from core.city.prompt_agent import PromptAgent


class ObraCodeReviewer(PromptAgent):
    """
    Independent second-opinion code reviewer. Different review style from AddyCodeReviewer —
    focuses on what a fresh pair of eyes would catch. Good for catching blind spots.
    Powered by vector-obra-code-reviewer.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-obra-code-reviewer.md", "obra_code_reviewer_001", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["review", "code_review"]

    async def run(self, task: dict) -> dict:
        # 2026-09-23 fix (fake-HP audit, second round): super().run(task) is
        # PromptAgent.run(), which already calls self.award_points(20,
        # f"{self.name}_task_done") on the exact same real success this
        # awarded another +25 for -- a genuine double-count on one real
        # ask() call, not a stub. Confirmed via grep this is the only
        # district agent with this specific pattern (super().run() result
        # re-awarded here); removed the duplicate award, kept the real one
        # PromptAgent.run() already gives.
        try:
            return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][obra_reviewer] {}", e)
            self.deduct_points(30, "obra_review_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = ObraCodeReviewer()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        print("obra_code_reviewer.py OK")
    asyncio.run(_smoke())
