"""
Addy Code Reviewer — Arghyadeep's personal VECTOR-aware senior code reviewer.
Loaded from: vectorcode/agents/vector-addy-code-reviewer.md
District: coding
"""
import asyncio
from pathlib import Path

from loguru import logger
from core.city.prompt_agent import PromptAgent


class AddyCodeReviewer(PromptAgent):
    """
    Senior code reviewer across 5 dimensions: correctness, readability,
    architecture, security, performance. VECTOR-aware — knows VECTOR's rules,
    HP system, RULE 1-12 compliance checks.
    Powered by vector-addy-code-reviewer.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-addy-code-reviewer.md", "addy_code_reviewer_001", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["review_diff", "review_file"]

    async def review_diff(self, diff: str, context: str = "") -> dict:
        """Review a git diff and return structured feedback."""
        query = (
            f"Review this code diff across all five dimensions "
            f"(correctness, readability, architecture, security, performance):\n\n"
            f"```diff\n{diff[:4000]}\n```\n\n"
            f"Format findings as:\n"
            f"**[DIMENSION] [SEVERITY]**: Issue description\n"
            f"Line: <line number if visible>\n"
            f"Fix: <specific fix>\n\n"
            f"End with a VERDICT: APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION"
        )
        response = await self.ask(query, context=context, timeout=45.0)
        verdict = "NEEDS_DISCUSSION"
        if "APPROVE" in response.upper():
            verdict = "APPROVE"
        elif "REQUEST_CHANGES" in response.upper():
            verdict = "REQUEST_CHANGES"
        return {"verdict": verdict, "review": response, "diff_chars": len(diff)}

    async def review_file(self, filepath: str) -> dict:
        """Review a single file for code quality."""
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {"status": "error", "error": str(e)}
        query = (
            f"Review this file for code quality issues. Focus on:\n"
            f"- VECTOR rules compliance (HP wired, loguru not print, etc.)\n"
            f"- Silent failures (bare except, swallowed errors)\n"
            f"- Architecture issues (coupling, missing abstractions)\n\n"
            f"File: {filepath}\n```python\n{content[:3000]}\n```"
        )
        response = await self.ask(query, timeout=45.0)
        return {"status": "ok", "review": response, "file": filepath}

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "ask")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "review_diff":
                result = await self.review_diff(task.get("diff", ""), task.get("context", ""))
                verdict = result["verdict"]
                self.award_points(30 if verdict == "APPROVE" else 20, f"review_{verdict.lower()}")
                return {"status": "ok", **result}
            elif task_type == "review_file":
                result = await self.review_file(task.get("filepath", ""))
                self.award_points(25, "file_reviewed")
                return result
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][addy_reviewer] {}", e)
            self.deduct_points(30, "review_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = AddyCodeReviewer()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        result = await agent.review_file(__file__)
        print(f"[OK] review_file: status={result['status']}")
        print("addy_code_reviewer.py OK")
    asyncio.run(_smoke())
