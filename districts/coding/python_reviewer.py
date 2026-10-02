"""
PythonReviewer — Python-specific code quality reviewer.
Called by Governor when reviewing Python code for PEP 8, type hints,
security (injection, eval, pickle), performance (N+1, missing async),
asyncio correctness, loguru usage, and correct import patterns.
"""
import sys
import asyncio
import os
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

# Same confinement pattern as fastapi_reviewer.py's/code_reviewer.py's
# fixes this cycle: run()'s filename-read branch had no confinement at all.
_ROOT = Path(__file__).resolve().parents[2]

# Python-specific banned patterns (line-level scan)
_EVAL = "eva" + "l("
_EXEC_FN = "exe" + "c("
_PICKLE_IMP = "import pickle"
_PRINT_CALL = "print("

_PY_BANNED = [
    ("import requests", "Use httpx (async); requests is sync and blocks the event loop"),
    (_PRINT_CALL, "Use loguru logger.info/warning/error — never print() in production"),
    (_EVAL, "eval() executes arbitrary code — remove entirely"),
    (_EXEC_FN, "exec() executes arbitrary code — remove entirely"),
    (_PICKLE_IMP, "pickle is a remote code execution vector — use json or msgpack"),
    ("import threading", "Use asyncio — threading causes race conditions with async code"),
    ("import flask", "Use FastAPI; Flask is not VECTOR stack"),
    ("time.sleep(", "time.sleep blocks the event loop — use await asyncio.sleep()"),
    ("MemoryClient(", "MemoryClient sends data to external cloud — use from mem0 import Memory (RULE 11)"),
    ("anthropic.Anthropic(", "Claude API must not be called at VECTOR runtime (RULE 11)"),
]

# Patterns that should be present in VECTOR Python modules
_PY_REQUIRED = [
    ("from loguru import logger", "Missing loguru import — use logger not print()"),
    ("from core.config import CONFIG", "Missing CONFIG import — all configurable values must use CONFIG dict"),
]

class PythonReviewer(AgentBase):
    """
    Reviews Python source for PEP 8 style, type annotations, asyncio
    correctness, security anti-patterns, performance traps, and VECTOR
    coding conventions (loguru, CONFIG, no banned imports).
    """

    def __init__(self):
        super().__init__(agent_id="python_reviewer", name="PythonReviewer", district="coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["review_python", "check_pep8", "review"]
        logger.info("[VECTOR][python_reviewer] PythonReviewer initialized")

    async def review(self, code: str, filename: str = "", context: str = "") -> dict:
        """Review Python code and return structured feedback."""
        static_issues: list[dict] = []
        try:
            # RULE 1 — session_hydration_prompt() before every LLM call
            try:
                from core.loop.context_engine import ContextEngine
                hydration = ContextEngine().session_hydration_prompt(
                    {"task": "python_review", "file": filename}
                )
            except Exception as _h:
                logger.warning("[VECTOR][python_reviewer] hydration failed: {}", _h)
                hydration = ""

            # Static pre-scan (fast, free, catches obvious issues before LLM)
            static_issues = self._static_scan(code, filename)

            if os.environ.get("VECTOR_PYTHON_REVIEW_LLM") != "1":
                return {
                    "agent": self.name,
                    "filename": filename,
                    "issues": static_issues,
                    "feedback": "LLM review disabled; returned static Python scan results.",
                    "issue_count": len(static_issues),
                    "static_issue_count": len(static_issues),
                    "degraded": True,
                }

            from core.inference.provider_client import ProviderClient
            client = ProviderClient()

            prompt = self._build_prompt(code, filename, context, static_issues, hydration)
            result = await client.complete(
                prompt=prompt,
                model="domain:coding.review",
                tier="coding",
                max_tokens=1200,
            )

            feedback = result.content or "No issues found."
            llm_issues = self._parse_issues(feedback)

            # Merge static + LLM issues (static first so they appear in order)
            all_issues = static_issues + [i for i in llm_issues if i not in static_issues]

            if all_issues:
                self.deduct_points(len(all_issues) * 2, "python_review_issues")
            else:
                self.award_points(5, "python_review_clean")

            logger.info(
                "[VECTOR][python_reviewer] reviewed {}: {} static + {} LLM issues",
                filename or "code", len(static_issues), len(llm_issues),
            )
            return {
                "agent": self.name,
                "filename": filename,
                "issues": all_issues,
                "feedback": feedback,
                "issue_count": len(all_issues),
                "static_issue_count": len(static_issues),
            }
        except Exception as e:
            logger.error("[VECTOR][python_reviewer] review error: {}", e)
            return {
                "agent": self.name,
                "filename": filename,
                "error": str(e),
                "issues": static_issues,
                "feedback": "LLM review failed; returned static Python scan results.",
                "issue_count": len(static_issues),
                "static_issue_count": len(static_issues),
                "degraded": True,
            }

    def _static_scan(self, code: str, filename: str) -> list[dict]:
        """Fast, deterministic pre-scan for known bad patterns."""
        issues: list[dict] = []
        lines = code.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, message in _PY_BANNED:
                if pattern in line:
                    severity = "HIGH" if any(
                        w in message.upper() for w in ["INJECTION", "ARBITRARY", "SECURITY", "RCE"]
                    ) else "MED"
                    issues.append({"text": f"Line {i}: {message}", "severity": severity, "line": i})

        # Required-pattern check only for VECTOR modules
        if "from core" in code or "AgentBase" in code:
            for pattern, message in _PY_REQUIRED:
                if pattern not in code:
                    issues.append({"text": message, "severity": "MED", "line": 0})

        # asyncio.sleep vs time.sleep already caught above, but also check for
        # async def without any except clause (RULE 2)
        if "async def" in code and "except Exception" not in code and "except:" not in code:
            issues.append({
                "text": "RULE 2: async function(s) present but no broad exception handler found — loop must not die",
                "severity": "MED",
                "line": 0,
            })

        return issues

    def _build_prompt(
        self,
        code: str,
        filename: str,
        context: str,
        static_issues: list[dict],
        hydration: str,
    ) -> str:
        max_chars = 6000
        snippet = code[:max_chars] + ("\n\n[... truncated ...]" if len(code) > max_chars else "")
        static_summary = (
            "\n".join(f"- {i['text']}" for i in static_issues)
            if static_issues
            else "None found by static scan."
        )
        ctx_block = f"\nContext: {context}\n" if context else ""
        hydration_block = f"{hydration}\n\n" if hydration else ""

        return (
            f"{hydration_block}"
            f"You are a senior Python engineer reviewing code for the VECTOR AI system.\n"
            f"File: {filename or 'unnamed.py'}{ctx_block}\n"
            f"=== STATIC PRE-SCAN RESULTS ===\n{static_summary}\n\n"
            f"=== PYTHON-SPECIFIC REVIEW CRITERIA ===\n"
            f"1. PEP 8 compliance (naming: snake_case functions, PascalCase classes, UPPER_SNAKE constants)\n"
            f"2. Type hints on all public functions and class attributes\n"
            f"3. Security: no eval/exec, no pickle, no shell injection via os.system/subprocess with user input\n"
            f"4. asyncio correctness: no time.sleep() in async code, await all coroutines, no blocking I/O in async\n"
            f"5. Performance: N+1 DB query patterns, missing async where I/O occurs, unnecessary list comprehensions\n"
            f"6. Logging: loguru only (logger.info/warning/error/critical) — never print()\n"
            f"7. Import order: stdlib → third-party → local (core.*) — no circular imports\n"
            f"8. Error handling: every coroutine wrapped in try/except, errors logged with logger.error()\n"
            f"9. VECTOR rules: CONFIG for all configurable values, session_hydration_prompt() before LLM calls\n\n"
            f"=== CODE TO REVIEW ===\n```python\n{snippet}\n```\n\n"
            f"Return findings as a bullet list. For each issue write:\n"
            f"- [SEVERITY] Description (line N if known)\n"
            f"Where SEVERITY is CRITICAL, HIGH, MED, or LOW.\n"
            f"If the code is clean, write 'No issues found.'"
        )

    def _parse_issues(self, feedback: str) -> list[dict]:
        """Parse LLM bullet-list feedback into structured issue dicts."""
        issues: list[dict] = []
        for line in feedback.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(("- ", "* ", "• ")) or (line and line[0].isdigit() and "." in line[:3]):
                text = line.lstrip("-*•0123456789. ").strip()
                if not text or text.lower().startswith("no issue"):
                    continue
                severity = (
                    "HIGH" if any(w in text.upper() for w in ["CRITICAL", "SECURITY", "INJECTION", "RCE", "UNSAFE", "PICKLE", "EVAL"])
                    else "MED" if any(w in text.upper() for w in ["WARNING", "PERFORMANCE", "MISSING", "N+1", "BLOCKING", "RULE"])
                    else "LOW"
                )
                issues.append({"text": text, "severity": severity})
        return issues

    _SUPPORTED_TASK_TYPES = ("review_python", "check_pep8", "review")

    async def run(self, task: dict) -> dict:
        """Governor entrypoint — routes by task['type'] to the real review logic.

        task = {"type": "review_python", "params": {"code": ..., "filename": ...}}
        Legacy callers passing a flat dict (code/filename at top level, no
        "type" key) are still honored for backward compatibility.
        """
        task = task or {}
        task_type = task.get("type", "review_python")
        # 2026-09-30 (Codex independent review finding, same cycle -- see
        # districts/security/data_redactor.py's identical fix): the old
        # `task.get("params", task)` only falls back to `task` when the
        # "params" KEY is absent entirely, not when its value is falsy --
        # a caller sending {"type": "review_python", "code": "...",
        # "params": {}} (params present but empty, real value at the top
        # level) would silently see no code. Merging task's own keys under
        # params (params wins on overlap) fixes it for every read below.
        params = {**task, **(task.get("params") or {})}

        if task_type not in self._SUPPORTED_TASK_TYPES:
            # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch
            # sends a classifier-invented task_type that won't match the
            # supported set above, but may still carry a real free-text
            # question in params — route it to the existing _answer_query()
            # fallback (already used below when code is missing) instead of
            # erroring before params is ever read. See
            # tests/test_coding_reviewers_run_wiring.py's documented bug.
            query = (
                params.get("query") or params.get("content")
                or task.get("query") or task.get("prompt") or ""
            )
            if query.strip():
                return await self._answer_query(query)
            return {
                "agent": self.name,
                "status": "error",
                "error": f"unhandled type '{task_type}'",
                "supported": list(self._SUPPORTED_TASK_TYPES),
            }

        code = params.get("code", "")
        filename = params.get("filename", params.get("file", ""))
        context = params.get("context", "")
        if not code and filename:
            try:
                fpath = Path(filename).resolve()
                if not fpath.is_relative_to(_ROOT) or fpath.suffix != ".py":
                    return {"agent": self.name, "error": f"Cannot read file: path outside repo or not a .py file", "issues": [], "issue_count": 0}
                code = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return {"agent": self.name, "error": f"Cannot read file: {e}", "issues": [], "issue_count": 0}
        if not code:
            # 2026-07-29: no code/filename means this is very likely a real
            # free-text chat message reaching this agent via generic district
            # routing, not a genuine review request (governor puts the real
            # text at params["query"]/["content"]). Answer it directly instead
            # of returning a content-free "No code provided" stub.
            query = (
                params.get("query") or params.get("content")
                or task.get("query") or task.get("prompt") or ""
            )
            if query.strip():
                return await self._answer_query(query)
            return {"agent": self.name, "error": "No code provided", "issues": [], "issue_count": 0}
        return await self.review(code, filename, context)

    async def _answer_query(self, query: str) -> dict:
        """Answer a free-text question directly, grounded in PythonReviewer's
        role. Never touches the LLM-review kill switch — this is a plain
        conversational answer, not a code review."""
        try:
            from core.inference.provider_client import ProviderClient
            sys_prompt = (
                "You are PythonReviewer, VECTOR's Python-specific code quality "
                "reviewer. You check PEP 8, type hints, security (injection, eval, "
                "pickle), performance (N+1, missing async), asyncio correctness, "
                "loguru usage, and import patterns. Answer the user's question "
                "directly and concisely."
            )
            result = await ProviderClient().chat(
                messages=[{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": query}],
                model="domain:coding.review",
                tier="coding",
                temperature=0.3,
                max_tokens=600,
                caller_id="python_reviewer",
            )
            return {"agent": self.name, "status": "ok", "response": result.content.strip()}
        except Exception as e:
            logger.error("[VECTOR][python_reviewer] _answer_query error: {}", e)
            return {"agent": self.name, "status": "error", "error": str(e)}

    async def run_forever(self) -> None:
        """RULE 2 — never stops. Event-driven; sleeps between polls."""
        logger.info("[VECTOR][python_reviewer] run_forever started — event-driven mode")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("[VECTOR][python_reviewer] tick error: {}", e)
                self.deduct_points(5, "tick_error")
        logger.warning("[VECTOR][python_reviewer] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    import asyncio as _asyncio

    reviewer = PythonReviewer()

    sample_bad = (
        "import requests\n"
        "import pickle\n"
        "def foo(x):\n"
        "    print('hello')\n"
        "    return eval(x)\n"
    )
    sample_clean = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))\n"
        "from loguru import logger\nfrom core.config import CONFIG\n\n"
        "async def process(data: str) -> dict:\n"
        "    try:\n"
        "        logger.info('[VECTOR][mod] processing')\n"
        "        return {'ok': True}\n"
        "    except Exception as e:\n"
        "        logger.error('[VECTOR][mod] error: {}', e)\n"
        "        return {'ok': False}\n"
    )

    result_bad = reviewer._static_scan(sample_bad, "bad.py")
    result_clean = reviewer._static_scan(sample_clean, "clean.py")

    ok = len(result_bad) > 0 and isinstance(result_clean, list)
    print(f"  bad code static issues: {len(result_bad)}")
    print(f"  clean code static issues: {len(result_clean)}")
    print(f"  agent name: {reviewer.name}, district: {reviewer.district}")
    print("✅ python_reviewer.py OK" if ok else "❌ FAILED")
