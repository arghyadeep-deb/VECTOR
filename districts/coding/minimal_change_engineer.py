"""
MinimalChangeEngineer — Enforces minimum-viable diffs.

Reads files, identifies the smallest change that satisfies the requirement,
flags scope creep, refuses to expand beyond task scope.
"""

import asyncio
import re
import ast
import datetime
from pathlib import Path
from districts.coding.path_security import is_path_within

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

# Same confinement pattern as code_reviewer.py's/architect_bot.py's/
# bug_hunter.py's/code_explorer.py's fixes this cycle:
# analyze_change_scope() reads any caller-supplied path with no
# confinement at all, directly Governor-dispatchable via run()'s
# task_type == "analyze".
_ROOT = Path(__file__).resolve().parents[2]

# Keywords that indicate a change has grown beyond the original task scope
_SCOPE_EXPANSION_SIGNALS = [
    "refactor", "restructure", "clean up", "improve", "optimize",
    "rewrite", "overhaul", "revamp", "modernize", "reorganize",
    "add feature", "new feature", "extend", "enhance", "upgrade",
]

# Lines-changed thresholds for scope risk scoring
_SCOPE_RISK_THRESHOLDS = {
    "low":    (0,   30),
    "medium": (30,  80),
    "high":   (80, 200),
    "critical": (200, float("inf")),
}

def _count_lines(source: str) -> int:
    return len([ln for ln in source.splitlines() if ln.strip()])

def _classify_scope_risk(n_lines: int) -> str:
    for label, (lo, hi) in _SCOPE_RISK_THRESHOLDS.items():
        if lo <= n_lines < hi:
            return label
    return "critical"

class MinimalChangeEngineer(AgentBase):
    """Enforces minimum-viable diffs — smallest change that satisfies the task."""

    def __init__(self):
        super().__init__(
            agent_id="minimal_change_001",
            name="MinimalChangeEngineer",
            district="coding",
        )
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["analyze", "scope_check", "diff_prompt", "status"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][minimal_change_engineer] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def analyze_change_scope(self, file_path: str, task: str) -> dict:
        """Read a file and task description, return minimal-change analysis.

        Returns:
            {
                file: str,
                total_lines: int,
                min_lines_changed: int,
                scope_risk: "low" | "medium" | "high" | "critical",
                suggestion: str,
                task_keywords_matched: list[str],
                timestamp: str,
            }
        Never raises.
        """
        try:
            fpath = Path(file_path).resolve()
            if not is_path_within(fpath, _ROOT) or fpath.suffix != ".py":
                logger.error(f"[VECTOR][minimal_change_engineer] Path outside repo or not .py: {file_path}")
                return {
                    "file": file_path,
                    "total_lines": 0,
                    "min_lines_changed": 0,
                    "scope_risk": "unknown",
                    "suggestion": "Path outside repo or not a .py file — cannot analyze",
                    "task_keywords_matched": [],
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            if not fpath.exists():
                logger.error(f"[VECTOR][minimal_change_engineer] File not found: {file_path}")
                return {
                    "file": file_path,
                    "total_lines": 0,
                    "min_lines_changed": 0,
                    "scope_risk": "unknown",
                    "suggestion": "File not found — cannot analyze",
                    "task_keywords_matched": [],
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }

            source = fpath.read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            total_lines = _count_lines(source)

            # Estimate which functions / classes are relevant to the task
            task_lower = task.lower()
            task_words = set(re.findall(r"\w+", task_lower))

            # Attempt AST parse to identify top-level symbols
            relevant_symbols: list[str] = []
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbol_words = set(re.findall(r"[a-z]+", node.name.lower()))
                        if symbol_words & task_words:
                            relevant_symbols.append(node.name)
            except SyntaxError:
                pass  # still usable, just no AST symbol matching

            # Estimate minimum lines changed: target only relevant symbols
            if relevant_symbols:
                # Conservative: 5-20 lines per relevant symbol
                min_lines_changed = max(5, len(relevant_symbols) * 10)
            else:
                # No specific symbol match → estimate ~10% of file or 10 lines
                min_lines_changed = max(10, total_lines // 10)

            scope_risk = _classify_scope_risk(min_lines_changed)

            # Generate a human-readable suggestion
            if relevant_symbols:
                target_str = ", ".join(f"`{s}`" for s in relevant_symbols[:5])
                suggestion = (
                    f"Focus changes on: {target_str}. "
                    f"Estimated {min_lines_changed} lines. Do not touch unrelated code."
                )
            else:
                suggestion = (
                    f"No specific symbol matched task keywords. "
                    f"Make surgical changes near task-related lines only (~{min_lines_changed} lines max). "
                    f"If file is large ({total_lines} lines), consider targeting via line search first."
                )

            # Match explicit scope-expansion signals in task description
            task_keywords_matched = [
                sig for sig in _SCOPE_EXPANSION_SIGNALS if sig in task_lower
            ]
            if task_keywords_matched:
                scope_risk = "high"
                suggestion = (
                    f"WARNING: task contains scope-expansion language: {task_keywords_matched}. "
                    f"Confirm this is intentional. Original: {suggestion}"
                )

            result = {
                "file": file_path,
                "total_lines": total_lines,
                "min_lines_changed": min_lines_changed,
                "scope_risk": scope_risk,
                "suggestion": suggestion,
                "relevant_symbols": relevant_symbols,
                "task_keywords_matched": task_keywords_matched,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            self._get_memory().store(
                event_type="analyze_change_scope",
                content=f"file={file_path} task={task[:80]} scope_risk={scope_risk}",
                tags=["minimal_change", "scope_analysis", scope_risk],
                source="minimal_change_engineer",
            )

            if scope_risk in ("low", "medium"):
                self.award_points(10, "low_scope_risk_analysis")
            else:
                self.deduct_points(5, f"scope_risk_{scope_risk}")

            logger.info(
                f"[VECTOR][minimal_change_engineer] analyze_change_scope: "
                f"file={Path(file_path).name} risk={scope_risk} "
                f"min_lines={min_lines_changed}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][minimal_change_engineer] analyze_change_scope error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "file": file_path,
                "total_lines": 0,
                "min_lines_changed": 0,
                "scope_risk": "unknown",
                "suggestion": f"Error during analysis: {e}",
                "task_keywords_matched": [],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

    def detect_scope_creep(
        self, original_task: str, proposed_changes: list[str]
    ) -> dict:
        """Check whether proposed changes exceed what was asked.

        Args:
            original_task: The original one-sentence requirement.
            proposed_changes: List of change descriptions (e.g. git diff summaries).

        Returns:
            {
                verdict: "clean" | "warning" | "rejected",
                creep_items: list[str],
                clean_items: list[str],
                explanation: str,
                score: int,   # 0-100, 100 = no creep
            }
        Never raises.
        """
        try:
            task_lower = original_task.lower()
            task_words = set(re.findall(r"\w{4,}", task_lower))  # meaningful words only

            creep_items: list[str] = []
            clean_items: list[str] = []

            for change in proposed_changes:
                change_lower = change.lower()
                change_words = set(re.findall(r"\w{4,}", change_lower))

                # A change is "clean" if it shares significant vocabulary with the task
                overlap = len(task_words & change_words)
                has_expansion = any(sig in change_lower for sig in _SCOPE_EXPANSION_SIGNALS)

                # Heuristic: overlap < 2 words AND contains expansion signals → likely creep
                if overlap < 2 and has_expansion:
                    creep_items.append(change)
                elif overlap < 1 and len(change_words) > 5:
                    creep_items.append(change)
                else:
                    clean_items.append(change)

            n_total = len(proposed_changes)
            n_creep = len(creep_items)
            score = max(0, 100 - int((n_creep / max(n_total, 1)) * 100))

            if n_creep == 0:
                verdict = "clean"
                explanation = "All proposed changes are within task scope."
            elif score >= 60:
                verdict = "warning"
                explanation = (
                    f"{n_creep}/{n_total} changes may exceed scope. "
                    f"Review creep_items before proceeding."
                )
            else:
                verdict = "rejected"
                explanation = (
                    f"{n_creep}/{n_total} changes are out of scope. "
                    f"Revert creep_items and limit to original task."
                )

            result = {
                "verdict": verdict,
                "creep_items": creep_items,
                "clean_items": clean_items,
                "explanation": explanation,
                "score": score,
            }

            self._get_memory().store(
                event_type="detect_scope_creep",
                content=f"verdict={verdict} score={score} creep={n_creep}/{n_total}",
                tags=["scope_creep", verdict],
                source="minimal_change_engineer",
            )

            if verdict == "clean":
                self.award_points(20, "no_scope_creep")
            elif verdict == "warning":
                self.award_points(5, "scope_creep_warning")
            else:
                self.deduct_points(20, "scope_creep_rejected")

            logger.info(
                f"[VECTOR][minimal_change_engineer] detect_scope_creep: "
                f"verdict={verdict} score={score}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][minimal_change_engineer] detect_scope_creep error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "verdict": "error",
                "creep_items": [],
                "clean_items": [],
                "explanation": str(e),
                "score": 0,
            }

    def generate_minimal_diff_prompt(self, task: str, current_code: str) -> str:
        """Generate a prompt for Ollama to produce the smallest possible change.

        Returns a ready-to-send system+user prompt string. Never raises.
        """
        try:
            max_code_chars = 6000
            truncated = current_code[:max_code_chars]
            if len(current_code) > max_code_chars:
                truncated += "\n\n# [...truncated for brevity...]"

            prompt = (
                "You are MinimalChangeEngineer. Your job is to produce the SMALLEST possible "
                "code change that satisfies the task. Rules:\n"
                "1. Change ONLY what is necessary to satisfy the task.\n"
                "2. Do NOT refactor unrelated code.\n"
                "3. Do NOT add new features beyond what is asked.\n"
                "4. Do NOT rename variables, add docstrings, or change formatting unless asked.\n"
                "5. Return ONLY the changed lines as a unified diff (--- / +++ format).\n"
                "6. If the task is already satisfied, return 'NO CHANGE NEEDED'.\n\n"
                f"TASK: {task}\n\n"
                f"CURRENT CODE:\n```python\n{truncated}\n```\n\n"
                "Produce the minimal unified diff now:"
            )

            logger.info(
                f"[VECTOR][minimal_change_engineer] generate_minimal_diff_prompt: "
                f"task={task[:60]} code_chars={len(current_code)}"
            )
            return prompt

        except Exception as e:
            logger.error(f"[VECTOR][minimal_change_engineer] generate_minimal_diff_prompt error: {e}")
            return f"# Error generating prompt: {e}\n# Task: {task}"

    # ------------------------------------------------------------------
    # run() — multi-task dispatcher
    # ------------------------------------------------------------------

    async def answer_question(self, query: str) -> str:
        """Answer a free-text question directly, grounded in
        MinimalChangeEngineer's role. Used by run() when a real chat query
        is present but no analyze/scope_check/diff_prompt was explicitly
        requested — 2026-07-29 sweep, same bug class as #1/#14/#15/#21/#33
        (content-free capabilities-stub instead of the real question)."""
        try:
            sys_prompt = (
                "You are MinimalChangeEngineer, VECTOR's minimum-viable-diff "
                "enforcer. You analyze how small a code change can be, detect "
                "scope creep in proposed changes, and generate minimal-diff "
                "prompts. Answer the user's question directly and concisely."
            )
            # RULE 1: session_hydration_prompt() before every LLM call.
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt({"query": query})
            answer = chat(
                model=self._model,
                messages=[{"role": "system", "content": f"{hydration}\n\n{sys_prompt}"}, {"role": "user", "content": query}],
                timeout=30.0,
            )
            self.award_points(10, "minimal_change_qa_answered")
            return answer or "I don't have enough information to answer that right now."
        except Exception as e:
            logger.error(f"[VECTOR][minimal_change_engineer] answer_question error: {e}")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        """Dispatch task types: analyze | scope_check | diff_prompt | status."""
        try:
            task_type = task.get("type", "")
            p = task.get("params", {}) if isinstance(task.get("params"), dict) else {}
            query = (
                p.get("query") or p.get("content") or task.get("query")
                or task.get("prompt") or ""
            )
            known_types = ("analyze", "scope_check", "diff_prompt", "status")
            if task_type not in known_types and query.strip():
                answer = await self.answer_question(query)
                return {"status": "ok", "response": answer, "agent": self.name}

            if not task_type:
                task_type = "status"

            if task_type == "analyze":
                file_path = task.get("file", task.get("file_path", ""))
                task_desc = task.get("task", task.get("description", ""))
                if not file_path:
                    return {"status": "error", "error": "Missing 'file' parameter"}
                result = self.analyze_change_scope(file_path, task_desc)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "scope_check":
                original = task.get("original_task", task.get("task", ""))
                proposed = task.get("proposed_changes", task.get("changes", []))
                if not isinstance(proposed, list):
                    proposed = [str(proposed)]
                result = self.detect_scope_creep(original, proposed)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "diff_prompt":
                task_desc = task.get("task", task.get("description", ""))
                code = task.get("code", task.get("current_code", ""))
                if not task_desc or not code:
                    return {"status": "error", "error": "Missing 'task' or 'code' parameter"}
                prompt = self.generate_minimal_diff_prompt(task_desc, code)
                # Optionally call Ollama for actual diff if model available
                llm_diff = ""
                if task.get("call_llm", False):
                    from core.prompt_library import get_library as _gl
                    from core.loop.context_engine import ContextEngine
                    _sys = _gl().get_for_agent("minimal_change_engineer") or ""
                    # RULE 1: session_hydration_prompt() before every LLM call.
                    hydration = ContextEngine().session_hydration_prompt({"query": task_desc})
                    _sys = f"{hydration}\n\n{_sys}" if _sys else hydration
                    messages = [{"role": "system", "content": _sys}, {"role": "user", "content": prompt}]
                    llm_diff = chat(model=self._model, messages=messages, timeout=30.0)
                self.award_points(30, "task_done")
                return {
                    "status": "ok",
                    "prompt": prompt,
                    "llm_diff": llm_diff,
                }

            else:
                # Default: status
                return {
                    "status": "ok",
                    "agent": self.name,
                    "district": self.district,
                    "hp": self.health_points,
                    "model": self._model,
                    "capabilities": ["analyze", "scope_check", "diff_prompt"],
                }

        except Exception as e:
            logger.error(f"[VECTOR][minimal_change_engineer] run error: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = MinimalChangeEngineer()

        # 1. analyze_change_scope on this file itself
        this_file = str(Path(__file__).resolve())
        result = await agent.run({
            "type": "analyze",
            "file": this_file,
            "task": "fix the detect_scope_creep method to handle empty list correctly",
        })
        assert result["status"] == "ok", f"analyze failed: {result}"
        assert "scope_risk" in result, "missing scope_risk"
        print(f"[OK] analyze: scope_risk={result['scope_risk']} min_lines={result.get('min_lines_changed')}")

        # 2. scope_check — clean case
        result2 = await agent.run({
            "type": "scope_check",
            "original_task": "fix the login function to validate email format",
            "proposed_changes": [
                "validate email format in login()",
                "add regex check for @-sign in email field",
            ],
        })
        assert result2["status"] == "ok", f"scope_check failed: {result2}"
        assert result2["verdict"] in ("clean", "warning", "rejected")
        print(f"[OK] scope_check: verdict={result2['verdict']} score={result2['score']}")

        # 3. scope_check — creep case
        result3 = await agent.run({
            "type": "scope_check",
            "original_task": "fix the login bug",
            "proposed_changes": [
                "refactor entire authentication module",
                "restructure database layer",
                "overhaul error handling across codebase",
            ],
        })
        assert result3["status"] == "ok"
        assert result3["verdict"] in ("warning", "rejected"), "should detect scope creep"
        print(f"[OK] scope_check (creep): verdict={result3['verdict']}")

        # 4. diff_prompt (no LLM call — just prompt generation)
        result4 = await agent.run({
            "type": "diff_prompt",
            "task": "add type annotation to the return value of get_user()",
            "code": "def get_user(user_id):\n    return db.query(user_id)\n",
        })
        assert result4["status"] == "ok"
        assert "prompt" in result4
        assert len(result4["prompt"]) > 50
        print(f"[OK] diff_prompt: prompt_len={len(result4['prompt'])}")

        # 5. status
        result5 = await agent.run({"type": "status"})
        assert result5["status"] == "ok"
        print(f"[OK] run: status={result5['status']}")
        print("minimal_change_engineer.py OK")

    asyncio.run(_smoke())
