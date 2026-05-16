"""
Obra Code Reviewer — second-opinion code reviewer with independent perspective.
Loaded from: vectorcode/agents/vector-obra-code-reviewer.md
District: coding
"""
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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

    async def run(self, task: dict) -> dict:
        try:
            result = await super().run(task)
            if result.get("status") == "ok":
                self.award_points(25, "obra_review_done")
            return result
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
