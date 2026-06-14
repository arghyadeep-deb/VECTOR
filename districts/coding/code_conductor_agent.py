"""
VECTOR CodeConductorAgent — District 03: coding
Multi-agent AI coding orchestrator.

Uses specialized sub-agents (file picker, code searcher, planner, editor, reviewer)
to implement coding changes more accurately than single-model approaches.

Governor routes: code_conduct, str_replace, code_map, code_accuracy_test

Usage:
    agent = CodeConductorAgent()
    result = asyncio.run(agent.run({
        "params": {"action": "code_conduct",
                   "instruction": "Add input validation to all FastAPI endpoints"}
    }))
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.code_conductor.orchestrator import CodingOrchestrator
from core.code_conductor.code_map import CodeMap
from core.code_conductor.str_replace import str_replace as _str_replace, read_files, write_file
from core.code_conductor.git_eval import GitEvalRunner
from loguru import logger

class CodeConductorAgent(AgentBase):
    """
    VECTOR's multi-agent coding orchestrator.
    Coordinates file picker, planner, editor, reviewer sub-agents.
    Port of codebuff's base2 architecture.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="CodeConductorAgent",
            district="coding",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._cwd = CONFIG.get("coding", {}).get("repo_path", os.getcwd())
        logger.info("[VECTOR][code_conductor] ready gen={} hp={}", generation, self.health_points)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def code_conduct(self, instruction: str, cwd: str | None = None) -> dict:
        """
        Run full multi-agent coding pipeline on an instruction.
        Phase 1: pick files + build code map (parallel)
        Phase 2: plan → edit → review (sequential)
        """
        logger.info("[VECTOR][code_conductor] code_conduct: {!r:.80}", instruction)
        orch = CodingOrchestrator(cwd=cwd or self._cwd)
        result = await orch.run(instruction)

        ok = result.get("status") in ("ok", "partial")
        self._memory.store(
            event_type="code_conduct",
            content=f"CodeConductor: {instruction[:60]} → {result.get('status')} ({len(result.get('edits', []))} edits)",
            tags=["coding", "orchestration", "code_conduct"],
            source="code_conductor_agent",
        )
        if ok:
            self.award_points(50, f"code_conduct: {instruction[:40]}")
        else:
            self.deduct_points(10, f"code_conduct failed: {result.get('error', '')[:40]}")

        return result

    async def do_str_replace(
        self,
        file_path: str,
        old_str: str,
        new_str: str,
        cwd: str | None = None,
    ) -> dict:
        """Surgical exact-string replacement in a file."""
        result = _str_replace(file_path, old_str, new_str, cwd=cwd or self._cwd)
        if result.get("status") == "ok":
            self.award_points(10, f"str_replace: {file_path}")
        return result

    async def build_code_map(self, directory: str | None = None) -> dict:
        """Build AST-based symbol index of the codebase."""
        root = directory or self._cwd
        loop = asyncio.get_event_loop()
        cm = CodeMap(root=root)
        await loop.run_in_executor(None, cm.build)
        total = sum(len(v) for v in cm._index.values())
        summary = cm.summary(max_chars=5000)
        self.award_points(10, f"code_map: {root}")
        return {
            "root": root,
            "files_indexed": len(cm._index),
            "symbols": total,
            "summary": summary,
        }

    async def code_accuracy_test(self, num_commits: int = 5) -> dict:
        """
        Measure coding agent accuracy by reconstructing recent git commits.
        Port of codebuff's git-eval methodology.
        """
        logger.info("[VECTOR][code_conductor] accuracy test: {} commits", num_commits)
        runner = GitEvalRunner(cwd=self._cwd)
        result = await runner.run_suite(num_commits=num_commits)
        logger.info("[VECTOR][code_conductor] accuracy: {:.1%}", result.get("avg_score", 0))
        self._memory.store(
            event_type="code_accuracy_test",
            content=f"Git eval: {num_commits} commits, avg_score={result.get('avg_score', 0):.2f}",
            tags=["coding", "eval", "accuracy"],
            source="code_conductor_agent",
        )
        return result

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "code_conduct")

        if action in ("code_conduct", "conduct", "code"):
            return await self.code_conduct(
                instruction=p.get("instruction", p.get("task", "")),
                cwd=p.get("cwd"),
            )
        elif action == "str_replace":
            return await self.do_str_replace(
                file_path=p.get("file", p.get("path", "")),
                old_str=p.get("old_str", p.get("old", "")),
                new_str=p.get("new_str", p.get("new", "")),
                cwd=p.get("cwd"),
            )
        elif action in ("code_map", "map"):
            return await self.build_code_map(directory=p.get("directory"))
        elif action in ("code_accuracy_test", "eval", "accuracy_test"):
            return await self.code_accuracy_test(
                num_commits=int(p.get("num_commits", 5))
            )
        elif action == "read_files":
            return read_files(
                paths=p.get("paths", []),
                cwd=p.get("cwd", self._cwd),
            )
        elif action == "write_file":
            return write_file(
                file_path=p.get("file", p.get("path", "")),
                content=p.get("content", ""),
                cwd=p.get("cwd", self._cwd),
            )
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][code_conductor] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][code_conductor] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = CodeConductorAgent()
        assert agent.health_points == 500
        assert agent.name == "CodeConductorAgent"
        assert agent.district == "coding"

        # Code map test (no LLM needed)
        result = await agent.run({"params": {"action": "code_map"}})
        assert "symbols" in result
        assert result["files_indexed"] > 0

        # str_replace test
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n")
            tmp = f.name
        r = await agent.run({"params": {
            "action": "str_replace", "file": tmp,
            "old_str": "x = 1", "new_str": "x = 42",
        }})
        assert r["status"] == "ok"
        import os; os.unlink(tmp)

        print(f"OK code_conductor_agent.py HP={agent.health_points}")
        print(f"  code_map: {result['files_indexed']} files, {result['symbols']} symbols")
        print(f"  str_replace: OK")

    asyncio.run(_smoke())
