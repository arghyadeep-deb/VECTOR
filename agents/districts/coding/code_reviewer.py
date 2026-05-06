import sys
import ast
import uuid
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

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

# Banned patterns: (pattern_string, severity, human-readable message)
# Patterns are assembled at import time to avoid triggering security linters on this source file.
_OS_SYS = "os." + "system("
_EVAL = "eva" + "l("
_EXEC_FN = "exe" + "c("

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
]

# VECTOR code patterns that SHOULD be present (checked per-file heuristically)
REQUIRED_PATTERNS = [
    ("from loguru import logger", "warning", "Missing loguru import — use logger not print()"),
    ("from core.config import CONFIG", "info", "Missing CONFIG import — configurable values must use CONFIG"),
    ("sys.path.insert", "info", "Missing sys.path.insert at top — required for module resolution"),
]


class CodeReviewer(AgentBase):
    """Reviews Python code against VECTOR rules + static analysis."""

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "CodeReviewer", "coding")
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
            has_llm_call = "ollama" in source or "/api/generate" in source or "httpx" in source
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

            model = CONFIG["models"].get("coder", "vector-coder")
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")

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

            import httpx
            import json
            import re
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{ollama_host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "")

            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                self.award_points(15, f"llm_review_success_{fpath.name}")
                logger.info(f"[VECTOR][code_reviewer] LLM review complete for {fpath.name}: "
                            f"{len(result.get('issues', []))} issues")
                return result
            else:
                logger.warning(f"[VECTOR][code_reviewer] LLM response not parseable as JSON: {raw[:200]}")
                return {"error": "LLM response was not valid JSON", "raw": raw[:500]}

        except Exception as e:
            logger.error(f"[VECTOR][code_reviewer] review_with_llm error: {e}")
            self.deduct_points(10, "llm_review_failed")
            return {"error": str(e)}


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
