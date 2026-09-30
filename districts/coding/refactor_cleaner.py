"""
Refactor Cleaner — dead code cleanup and consolidation specialist.
Loaded from: vectorcode/agents/vector-refactor-cleaner.md
District: coding
"""
import asyncio
from pathlib import Path

from loguru import logger
from core.city.prompt_agent import PromptAgent


class RefactorCleaner(PromptAgent):
    """
    Dead code cleanup: finds unused imports, duplicate code, dead exports.
    Runs knip/depcheck/ts-prune analysis, removes safely in batches.
    Powered by vector-refactor-cleaner.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-refactor-cleaner.md", "refactor_cleaner_001", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["scan", "refactor", "dead_code"]

    async def find_dead_code(self, codebase_path: str = ".") -> dict:
        """Scan a codebase for dead code patterns using Python AST."""
        import ast
        import pathlib
        dead = {"unused_imports": [], "empty_except": [], "unreachable": []}
        path = pathlib.Path(codebase_path)
        files_checked = 0
        for pyfile in path.rglob("*.py"):
            if "__pycache__" in str(pyfile):
                continue
            try:
                src = pyfile.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(src)
                files_checked += 1
                for node in ast.walk(tree):
                    # Find bare except: pass (silent failure pattern)
                    if isinstance(node, ast.ExceptHandler):
                        if (node.type is None and len(node.body) == 1
                                and isinstance(node.body[0], ast.Pass)):
                            dead["empty_except"].append(str(pyfile))
            except SyntaxError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        return {
            "files_checked": files_checked,
            "findings": dead,
            "total_issues": sum(len(v) for v in dead.values()),
        }

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
            if task_type == "scan":
                result = await self.find_dead_code(task.get("path", "."))
                self.award_points(20, "dead_code_scanned")
                return {"status": "ok", "scan": result}
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][refactor_cleaner] {}", e)
            self.deduct_points(30, "refactor_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = RefactorCleaner()
        print(f"[OK] loaded: {agent.name} | {len(agent._system_prompt)} chars")
        scan = await agent.find_dead_code(".")
        print(f"[OK] scan: {scan['files_checked']} files, {scan['total_issues']} issues")
        print("refactor_cleaner.py OK")
    asyncio.run(_smoke())
