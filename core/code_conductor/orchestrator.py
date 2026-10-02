"""
VECTOR Code Conductor — Multi-Agent Coding Orchestrator
Python port of codebuff/agents/base2/base2.ts

Coordinates specialized coding sub-agents in phases:
  Phase 1 (parallel): file_picker + code_searcher
  Phase 2 (sequential): context_builder → planner → editor
  Phase 3: reviewer

Uses VECTOR's existing ContextEngine and provider_client for LLM calls.

Usage:
    orch = CodingOrchestrator(cwd="/path/to/project")
    result = asyncio.run(orch.run("Add input validation to all FastAPI endpoints"))
    logger.info(result["summary"])

"""
from __future__ import annotations

__all__ = [
    "CodingOrchestrator",
    "EditRecord",
    "OrchestratorResult",
]


import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config import CONFIG
from core.code_conductor.code_map import CodeMap
from core.code_conductor.str_replace import read_files, str_replace, write_file
from loguru import logger

_SYSTEM_PROMPT = """You are VECTOR's coding orchestrator. You coordinate specialized agents to implement coding changes.

When given a coding instruction:
1. Identify which files are relevant
2. Plan specific changes (be surgical — change only what's needed)
3. Execute str_replace edits (find exact string → replace)
4. Review the changes for correctness

Always output:
PLAN:
<bullet points of specific changes>

EDITS:
<one edit per file, using str_replace format>

DONE:
<summary of what was changed>"""


@dataclass
class EditRecord:
    file: str
    old_str: str
    new_str: str
    status: str = "pending"
    diff: str = ""


@dataclass
class OrchestratorResult:
    instruction: str
    status: str                          # ok | partial | error
    plan: str = ""
    edits: list[EditRecord] = field(default_factory=list)
    summary: str = ""
    files_used: list[str] = field(default_factory=list)
    error: str = ""


class CodingOrchestrator:
    """
    Multi-agent coding pipeline. Coordinates file picking, planning, editing, and review.
    Each phase uses VECTOR's inference stack (Ollama → Gemini → GPT-4o fallback).
    """

    def __init__(
        self,
        cwd: str | None = None,
        model: str | None = None,
        max_files: int = 20,
    ) -> None:
        self._cwd   = cwd or os.getcwd()
        self._model = model or CONFIG.get("models", {}).get("coder", "vector-coder")
        self._max_files = max_files
        self._code_map: CodeMap | None = None

    async def run(self, instruction: str) -> dict:
        """
        Execute a multi-agent coding task.
        Returns {status, plan, edits, summary, files_used, error}.
        """
        logger.info("[VECTOR][orchestrator] instruction={!r:.80}", instruction)
        result = OrchestratorResult(instruction=instruction, status="ok")

        try:
            # Phase 1: Build code map + pick relevant files (parallel)
            code_map, relevant_files = await asyncio.gather(
                self._build_code_map(),
                self._pick_files(instruction),
            )
            self._code_map = code_map
            result.files_used = relevant_files
            logger.info("[VECTOR][orchestrator] picked {} files", len(relevant_files))

            # Phase 2: Read files + plan changes
            file_context = read_files(relevant_files, cwd=self._cwd, max_chars_per_file=20_000)
            context_str = self._format_context(file_context, code_map)
            plan = await self._plan_changes(instruction, context_str)
            result.plan = plan

            # Phase 3: Execute edits
            edits = await self._execute_edits(instruction, plan, context_str)
            result.edits = edits

            # Phase 4: Summarize
            ok_count = sum(1 for e in edits if e.status == "ok")
            result.summary = (
                f"Applied {ok_count}/{len(edits)} edits across {len(relevant_files)} files. "
                + (f"Plan: {plan[:100]}" if plan else "")
            )
            # 0 == 0 used to make "no edits produced" report status "ok" (and the agent then paid +50 HP for it).
            if not edits:
                result.status = "error"
                result.error = "the plan produced no edits, so nothing was changed"
            elif ok_count == 0:
                result.status = "error"
                result.error = f"none of the {len(edits)} proposed edits could be applied"
            else:
                result.status = "ok" if ok_count == len(edits) else "partial"

        except Exception as e:
            logger.error("[VECTOR][orchestrator] error: {}", e)
            result.status = "error"
            result.error = str(e)

        return {
            "status": result.status,
            "instruction": result.instruction,
            "plan": result.plan,
            "edits": [{"file": e.file, "status": e.status, "diff": e.diff[:200]} for e in result.edits],
            "summary": result.summary,
            "files_used": result.files_used,
            "error": result.error,
            # The pipeline advertises plan -> edit -> review but never runs a review or any tests. Say so explicitly so
            # no caller (plan verification, HP, learning) mistakes "edits applied" for "change verified".
            "verification": {
                "tests_run": False,
                "review_run": False,
                "note": "edits were applied as proposed; no tests or review were run, so correctness is unverified",
            },
        }

    # ── Phase 1: Code map + file picker ──────────────────────────────────────

    async def _build_code_map(self) -> CodeMap:
        loop = asyncio.get_event_loop()
        cm = CodeMap(root=self._cwd)
        await loop.run_in_executor(None, cm.build)
        return cm

    async def _pick_files(self, instruction: str) -> list[str]:
        """Ask LLM which files are relevant, cross-check with code map."""
        try:
            # Quick regex scan for mentioned file paths in instruction
            import re
            mentioned = re.findall(r"[\w./]+\.py", instruction)

            # Scan the codebase for relevant file names
            relevant: list[str] = []
            for dirpath, _, filenames in os.walk(self._cwd):
                if any(skip in dirpath for skip in ["node_modules", ".git", "__pycache__", ".venv"]):
                    continue
                for fname in filenames:
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, self._cwd)
                    # Include if mentioned or matches keywords from instruction
                    if any(m in rel for m in mentioned):
                        relevant.append(rel)
                    elif self._file_seems_relevant(rel, instruction):
                        relevant.append(rel)
                    if len(relevant) >= self._max_files:
                        break

            return relevant[:self._max_files] if relevant else self._fallback_files()

        except Exception as e:
            logger.debug("[VECTOR][orchestrator] file picker error: {} — using fallback", e)
            return self._fallback_files()

    def _file_seems_relevant(self, rel_path: str, instruction: str) -> bool:
        """Heuristic: does the instruction mention keywords in this file path?"""
        keywords = [w.lower() for w in instruction.split() if len(w) > 4]
        rel_lower = rel_path.lower()
        return any(kw in rel_lower for kw in keywords)

    def _fallback_files(self) -> list[str]:
        """Return main Python files if file picker fails."""
        files = []
        for p in Path(self._cwd).rglob("*.py"):
            rel = os.path.relpath(str(p), self._cwd)
            if not any(skip in rel for skip in ["__pycache__", ".venv", "node_modules"]):
                files.append(rel)
            if len(files) >= 5:
                break
        return files

    # ── Phase 2: Planning ─────────────────────────────────────────────────────

    async def _plan_changes(self, instruction: str, context: str) -> str:
        """Ask LLM to plan specific edits."""
        prompt = (
            f"Instruction: {instruction}\n\n"
            f"Code context:\n{context[:4000]}\n\n"
            "Plan the specific changes needed. Be surgical and minimal. "
            "List each file to change and what exact string to replace."
        )
        return await self._llm(prompt, system=_SYSTEM_PROMPT)

    # ── Phase 3: Edit execution ───────────────────────────────────────────────

    async def _execute_edits(
        self, instruction: str, plan: str, context: str
    ) -> list[EditRecord]:
        """Parse LLM plan into str_replace calls and execute them."""
        # Ask LLM to produce str_replace commands
        prompt = (
            f"Instruction: {instruction}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Context:\n{context[:3000]}\n\n"
            "Produce str_replace commands. Format each as:\n"
            "FILE: path/to/file.py\n"
            "OLD: exact string to find\n"
            "NEW: replacement string\n"
            "---\n"
            "Be precise with whitespace and indentation."
        )
        response = await self._llm(prompt)

        edits = self._parse_edit_response(response)
        executed: list[EditRecord] = []

        for edit in edits:
            r = str_replace(edit.file, edit.old_str, edit.new_str, cwd=self._cwd)
            edit.status = "ok" if r.get("status") == "ok" else "error"
            edit.diff = r.get("diff", r.get("message", ""))[:500]
            if edit.status == "error":
                logger.warning("[VECTOR][orchestrator] edit failed {}: {}", edit.file, r.get("message"))
            executed.append(edit)

        return executed

    def _parse_edit_response(self, response: str) -> list[EditRecord]:
        """Parse LLM's str_replace command blocks."""
        import re
        edits: list[EditRecord] = []

        # Pattern: FILE: ... OLD: ... NEW: ... ---
        blocks = re.split(r"^---+$", response, flags=re.MULTILINE)
        for block in blocks:
            file_m = re.search(r"^FILE:\s*(.+)$", block, re.MULTILINE)
            old_m  = re.search(r"^OLD:\s*\n(.*?)(?=^NEW:|\Z)", block, re.MULTILINE | re.DOTALL)
            new_m  = re.search(r"^NEW:\s*\n(.*?)$", block, re.MULTILINE | re.DOTALL)

            if file_m and old_m:
                edits.append(EditRecord(
                    file=file_m.group(1).strip(),
                    old_str=old_m.group(1).rstrip(),
                    new_str=new_m.group(1).rstrip() if new_m else "",
                ))

        return edits

    # ── LLM call ─────────────────────────────────────────────────────────────

    async def _llm(self, prompt: str, system: str | None = None) -> str:
        try:
            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine
            # RULE 1: session_hydration_prompt() before every LLM call -- this
            # drives real file edits via str_replace/write_file, same gap
            # already fixed in multiple districts/coding files this cycle.
            hydration = ContextEngine().session_hydration_prompt({"query": prompt})
            messages = [{"role": "system", "content": hydration}]
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            return chat(model=self._model, messages=messages, timeout=60.0) or ""
        except Exception as e:
            logger.debug("[VECTOR][orchestrator] LLM call failed: {}", e)
            return ""

    # ── Context formatting ────────────────────────────────────────────────────

    def _format_context(self, file_context: dict, code_map: CodeMap) -> str:
        parts = [f"Code map:\n{code_map.summary(max_chars=2000)}\n"]
        for f in file_context.get("files", [])[:10]:
            parts.append(f"\n=== {f['path']} ===\n{f['content'][:3000]}")
        return "\n".join(parts)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        orch = CodingOrchestrator()
        assert orch._cwd is not None
        assert orch._max_files == 20

        # File picker test
        files = await orch._pick_files("edit config.py to add new setting")
        print(f"OK orchestrator.py — CodingOrchestrator init")
        print(f"  model={orch._model}")
        print(f"  file picker found {len(files)} relevant files")

    asyncio.run(_smoke())
