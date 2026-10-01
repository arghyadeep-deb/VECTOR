
import sys
import ast
import uuid
import asyncio
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

# Heuristic checklist for VECTOR rules compliance
VECTOR_RULES_CHECKLIST = [
    "session_hydration_prompt() called before LLM",
    "no direct API calls bypassing permission_gateway",
    "all exceptions caught (RULE 2)",
    "loguru used not print()",
    "no hardcoded secrets",
    "CONFIG used for all configurable values",
]

# Severity tier labels — maps raw severity strings to display labels
# From agency-agents code reviewer pattern
SEVERITY_LABELS = {
    "blocker":    "🔴 BLOCKER",    # security vuln, data loss, breaking change
    "error":      "🔴 BLOCKER",
    "suggestion": "🟡 SUGGESTION", # should fix: missing validation, N+1, duplication
    "warning":    "🟡 SUGGESTION",
    "nit":        "💭 NIT",        # nice to have: style, naming, docs
    "info":       "💭 NIT",
}

# Banned patterns: (pattern_string, severity, human-readable message)
# Patterns are assembled at import time to avoid triggering security linters on this source file.
_OS_SYS = "os." + "system("
_EVAL = "eva" + "l("
_EXEC_FN = "exe" + "c("
# AgentShield prompt-injection fragments assembled to avoid linter false-positives
_IGNORE_PREV = "Ignore previous" + " instructions"
_YOU_ARE_NOW = "You are" + " now"
_SYSTEM_HDR = "SYSTEM" + ":"
_REQ_GET = "requests" + ".get("
_URLLIB_REQ = "urllib" + ".request"
_PWD_ASSIGN = "password" + " ="
_APIKEY_ASSIGN = "api_key" + " ="
_SECRET_ASSIGN = "secret" + " ="
_GLOBAL_KW = "global" + " "
_FMT_CALL = ".format" + "("
_PCT_TUPLE = "%" + " ("

BANNED_PATTERNS = [
    ("import requests", "warning", "Use httpx (async), not requests"),
    ("print(", "warning", "Use loguru logger, not print()"),
    (_OS_SYS, "error", "os.system() is a shell injection risk — use subprocess or permission_gateway"),
    ("subprocess.call(", "warning", "Prefer asyncio subprocess or permission_gateway for shell commands"),
    (_EVAL, "error", "eval() is unsafe — never use"),
    (_EXEC_FN, "error", "exec() is unsafe — never use"),
    ("import flask", "warning", "Use FastAPI, not Flask"),
    ("import threading", "warning", "Use asyncio, not threading"),
    ("import pickle", "error", "pickle is a deserialization risk — use json/msgpack"),
    ("MemoryClient(", "error", "MemoryClient sends data to external cloud — use from mem0 import Memory (RULE 11)"),
    ("anthropic.Anthropic(", "warning", "Claude API must not be called at VECTOR runtime (RULE 11)"),
    # Prompt injection / AI security (AgentShield patterns)
    (_IGNORE_PREV, "error", "Prompt injection pattern detected"),
    (_YOU_ARE_NOW, "warning", "Potential persona hijack pattern"),
    (_SYSTEM_HDR, "warning", "Potential system prompt injection"),
    # Data exfiltration
    (_REQ_GET, "warning", "Use httpx not requests"),
    (_URLLIB_REQ, "warning", "Use httpx not urllib"),
    # Hardcoded credentials
    (_PWD_ASSIGN, "error", "Hardcoded password — use keyring or env var"),
    (_APIKEY_ASSIGN, "warning", "Hardcoded API key — use keyring or env var"),
    (_SECRET_ASSIGN, "warning", "Hardcoded secret — use keyring or env var"),
    # Race conditions
    (_GLOBAL_KW, "warning", "Global variable — potential race condition in async code"),
    # SQL injection
    (_FMT_CALL, "warning", "String formatting in query — use parameterized queries"),
    (_PCT_TUPLE, "warning", "String interpolation in query — use parameterized queries"),
]

# VECTOR code patterns that SHOULD be present (checked per-file heuristically)
REQUIRED_PATTERNS = [
    ("from loguru import logger", "warning", "Missing loguru import — use logger not print()"),
    ("from core.config import CONFIG", "info", "Missing CONFIG import — configurable values must use CONFIG"),
    ("sys.path.insert", "info", "Missing sys.path.insert at top — required for module resolution"),
]

class CodeReviewer(AgentBase):
    """Reviews Python code against VECTOR rules + static analysis."""

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "CodeReviewer", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = [
            "code_review", "review_diff", "review_file", "review_code",
            "check_syntax", "lint",
        ]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][code_reviewer] CodeReviewer initialized")

    def review_file(self, file_path: str) -> dict:
        """
        Read file and run static checks:
          1. ast.parse() — syntax errors
          2. Check VECTOR_RULES_CHECKLIST patterns (string-search heuristics)
          3. Check for banned patterns
        Returns {file, issues: [{line, severity, message}], score: 0-100, passed: bool}
        """
        try:
            fpath = Path(file_path)
            if not fpath.exists():
                logger.error(f"[VECTOR][code_reviewer] File not found: {file_path}")
                return {
                    "file": file_path,
                    "issues": [{"line": 0, "severity": "error", "message": "File not found"}],
                    "score": 0,
                    "passed": False,
                }

            source = fpath.read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            issues = []

            # --- 1. Syntax check via AST ---
            try:
                ast.parse(source)
            except SyntaxError as se:
                issues.append({
                    "line": se.lineno or 0,
                    "severity": "error",
                    "message": f"SyntaxError: {se.msg}",
                })
                return {
                    "file": file_path,
                    "issues": issues,
                    "score": 0,
                    "passed": False,
                }

            # --- 2. Banned pattern scan (line-by-line) ---
            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # skip comment lines
                for pattern, severity, message in BANNED_PATTERNS:
                    if pattern in line:
                        issues.append({
                            "line": i,
                            "severity": severity,
                            "message": f"Banned pattern '{pattern}': {message}",
                        })

            # --- 3. Required pattern check (whole-file) ---
            # Only applies to files that look like VECTOR modules
            is_vector_module = (
                "AgentBase" in source
                or "from core" in source
                or "core.config" in source
            )
            if is_vector_module:
                for pattern, severity, message in REQUIRED_PATTERNS:
                    if pattern not in source:
                        issues.append({
                            "line": 0,
                            "severity": severity,
                            "message": f"Missing required pattern: {message}",
                        })

            # --- 4. VECTOR rules heuristic checks ---
            # RULE 1: session_hydration_prompt before LLM calls
            has_llm_call = "ollama" in source or "/api/generate" in source or "httpx" in source or "ProviderClient" in source
            has_hydration = "session_hydration_prompt" in source
            if has_llm_call and not has_hydration:
                issues.append({
                    "line": 0,
                    "severity": "error",
                    "message": "RULE 1 violation: LLM calls detected but session_hydration_prompt() not called",
                })

            # RULE 3: permission_gateway check
            has_action = "Action(" in source
            has_gateway = "permission_gateway" in source or "PermissionGateway" in source
            if has_action and not has_gateway:
                issues.append({
                    "line": 0,
                    "severity": "error",
                    "message": "RULE 3 violation: Action() used but PermissionGateway not imported/used",
                })

            # RULE 2: exception handling in async functions
            has_async = "async def" in source
            has_try_except = "except Exception" in source or "except:" in source
            if has_async and not has_try_except:
                issues.append({
                    "line": 0,
                    "severity": "warning",
                    "message": "RULE 2 concern: async functions present but no broad exception handling detected",
                })

            # --- 5. Score calculation ---
            error_count = sum(1 for iss in issues if iss["severity"] == "error")
            warning_count = sum(1 for iss in issues if iss["severity"] == "warning")
            info_count = sum(1 for iss in issues if iss["severity"] == "info")

            penalty = (error_count * 15) + (warning_count * 5) + (info_count * 2)
            score = max(0, 100 - penalty)
            passed = error_count == 0 and score >= 60

            if passed:
                self.award_points(10, f"review_passed_{fpath.name}")
            else:
                self.deduct_points(5, f"review_failed_{fpath.name}")

            logger.info(
                f"[VECTOR][code_reviewer] {fpath.name}: score={score}, "
                f"errors={error_count}, warnings={warning_count}, passed={passed}"
            )
            return {
                "file": file_path,
                "issues": issues,
                "score": score,
                "passed": passed,
            }
        except Exception as e:
            logger.error(f"[VECTOR][code_reviewer] review_file error: {e}")
            self.deduct_points(10, "review_error")
            return {
                "file": file_path,
                "issues": [{"line": 0, "severity": "error", "message": f"Reviewer error: {e}"}],
                "score": 0,
                "passed": False,
            }

    async def review_with_llm(self, file_path: str) -> dict:
        """
        RULE 1: session_hydration_prompt() first.
        Call vector-coder via Ollama /api/generate.
        Returns {issues: [...], suggestions: [...]} or {error: ...}.
        """
        try:
            # RULE 1 — hydrate before LLM call
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            hydration = ctx.session_hydration_prompt({"task": "code_review", "file": file_path})

            fpath = Path(file_path)
            if not fpath.exists():
                logger.error(f"[VECTOR][code_reviewer] File not found for LLM review: {file_path}")
                return {"error": "File not found"}

            source = fpath.read_text(encoding="utf-8", errors="replace")
            MAX_CHARS = 8000
            if len(source) > MAX_CHARS:
                source = source[:MAX_CHARS] + "\n\n[... truncated ...]"

            from core.prompt_library import get_library as _get_lib
            _sys = _get_lib().get_for_agent("code_reviewer") or "You are a senior Python code reviewer. Be strict, concise, and return valid JSON only."

            prompt = (
                f"{hydration}\n\n"
                f"=== VECTOR CODE REVIEW CHECKLIST ===\n"
                + "\n".join(f"- {r}" for r in VECTOR_RULES_CHECKLIST) +
                f"\n\n=== FILE: {fpath.name} ===\n```python\n{source}\n```\n\n"
                "Review this code strictly against VECTOR rules above. "
                "Return ONLY a valid JSON object with keys:\n"
                '{"issues": [{"line": <int>, "severity": "error|warning|info", "message": "<text>"}], '
                '"suggestions": ["<text>"]}'
            )

            import json
            import re
            from core.inference.provider_client import ProviderClient as _PC
            _result = await _PC().chat(
                messages=[{"role": "system", "content": _sys}, {"role": "user", "content": prompt}],
                model="domain:coding.review",   # gpt-5 → DeepSeek-R1 → qwen-coder → ... → ollama
                tier="coding",
                temperature=0.3,
                max_tokens=1000,
                caller_id="code_reviewer",
            )
            raw = _result.content

            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                self.award_points(15, f"llm_review_success_{fpath.name}")
                logger.info(f"[VECTOR][code_reviewer] LLM review complete for {fpath.name}: "
                            f"{len(result.get('issues', []))} issues")
                # Enrich with code-review-graph blast radius
                try:
                    from districts.coding.code_review_graph import review_changes
                    crg = review_changes([str(fpath)])
                    if crg.get("status") in ("ok", "partial"):
                        result["blast_radius"] = crg
                except Exception as e:
                    logger.debug("[VECTOR][code_reviewer] blast-radius lookup failed: {}", e)
                return result
            else:
                logger.warning(f"[VECTOR][code_reviewer] LLM response not parseable as JSON: {raw[:200]}")
                return {"error": "LLM response was not valid JSON", "raw": raw[:500]}

        except Exception as e:
            logger.error(f"[VECTOR][code_reviewer] review_with_llm error: {e}")
            self.deduct_points(10, "llm_review_failed")
            return {"error": str(e)}

    async def review_with_vectorcode(self, file_path: str) -> dict:
        """
        LLM-backed deep review via VectorCode. Augments static analysis with
        semantic understanding. Falls back to static-only if VectorCode unavailable.
        """
        static = self.review_file(file_path)
        try:
            from districts.coding.vectorcode_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_available():
                static["vectorcode_review"] = "unavailable"
                return static
            task = (
                f"Review {file_path} for: bugs, security issues, VECTOR rule violations "
                f"(session_hydration, no direct LLM calls, loguru not print, asyncio not threading). "
                f"Static analysis already found: {len(static.get('issues', []))} issues. "
                f"Provide actionable fix suggestions."
            )
            vc_result = await bridge.run_task(task, mode="run", timeout=120)
            static["vectorcode_review"] = vc_result.get("output", "")[:1000]
            static["vectorcode_status"] = vc_result.get("status", "error")
        except Exception as e:
            logger.warning(f"[CodeReviewer] VectorCode review failed: {e}")
            static["vectorcode_review"] = f"error: {e}"
        return static

    async def _answer_query(self, query: str) -> str:
        """Answer a free-text question directly, grounded in CodeReviewer's
        role. Used by run() when a real chat message arrives instead of a
        file to review — 2026-07-29 sweep, same bug class as
        #1/#14/#15/#21/#33 (content-free stub instead of the real question)."""
        try:
            from core.inference.provider_client import ProviderClient as _PC
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("code_reviewer") or (
                "You are CodeReviewer, VECTOR's static + LLM Python code reviewer. "
                "You check files against VECTOR rules compliance, banned patterns, "
                "and structural issues. Answer the user's question directly and "
                "concisely."
            )
            result = await _PC().chat(
                messages=[{"role": "system", "content": _sys}, {"role": "user", "content": query}],
                model="domain:coding.review",
                tier="coding",
                temperature=0.3,
                max_tokens=600,
                caller_id="code_reviewer",
            )
            self.award_points(10, "code_reviewer_qa_answered")
            return result.content.strip()
        except Exception as e:
            logger.error(f"[VECTOR][code_reviewer] _answer_query error: {e}")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        file_path = p.get("file", p.get("path", ""))
        if file_path:
            result = await self.review_with_llm(file_path)
            return {"status": "ok", **result}

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or ""
        )
        if query.strip():
            answer = await self._answer_query(query)
            return {"status": "ok", "response": answer, "agent": self.name}

        return {"status": "ok", "note": "no file specified"}

    async def run_forever(self) -> None:
        """RULE 2 — never stops. CodeReviewer is event-driven; this keeps the agent alive."""
        logger.info("[VECTOR][code_reviewer] run_forever started — event-driven mode")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[VECTOR][code_reviewer] tick error: {e}")
                self.deduct_points(5, "tick_error")
        logger.warning("[VECTOR][code_reviewer] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    reviewer = CodeReviewer()

    # Smoke test 1: review this file itself
    this_file = str(Path(__file__).resolve())
    result = reviewer.review_file(this_file)

    ok = (
        isinstance(result, dict)
        and "file" in result
        and "issues" in result
        and "score" in result
        and "passed" in result
        and isinstance(result["issues"], list)
        and 0 <= result["score"] <= 100
    )
    print(f"  review_file({Path(this_file).name}): score={result['score']}, "
          f"issues={len(result['issues'])}, passed={result['passed']}")

    # Smoke test 2: review a file with banned patterns (synthetic, written dynamically)
    import tempfile, os
    bad_lines = [
        "import sys\n",
        "import reque" + "sts\n",         # banned: requests
        "def foo():\n",
        "    pri" + "nt('hello')\n",      # banned: print(
    ]
    bad_code = "".join(bad_lines)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(bad_code)
        tmp = f.name
    bad_result = reviewer.review_file(tmp)
    os.unlink(tmp)
    bad_ok = bad_result["score"] < 100 and len(bad_result["issues"]) > 0
    print(f"  bad_code review: score={bad_result['score']}, issues={len(bad_result['issues'])}")

    all_ok = ok and bad_ok
    print("✅ code_reviewer.py OK" if all_ok else "❌ FAILED")
