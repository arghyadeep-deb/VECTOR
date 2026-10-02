"""
FastAPIReviewer — FastAPI-specific code quality reviewer.
Called by Governor when reviewing FastAPI endpoints for async/await
correctness, Pydantic v2 schemas, dependency injection, OpenAPI docs,
rate limiting (slowapi), CORS config, response model types, error handling.
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

# Same confinement pattern as code_reviewer.py's/architect_bot.py's/
# bug_hunter.py's/code_explorer.py's/minimal_change_engineer.py's fixes
# this cycle: run()'s filename-read branch had no confinement at all.
_ROOT = Path(__file__).resolve().parents[2]

# FastAPI-specific static pattern checks: (pattern, severity, message)
_FASTAPI_BANNED = [
    # Sync route handlers in FastAPI are a blocking anti-pattern for I/O-bound routes
    ("def get_", "Route handler looks synchronous — use 'async def' for I/O-bound endpoints"),
    ("def post_", "Route handler looks synchronous — use 'async def' for I/O-bound endpoints"),
    # Pydantic v1 patterns
    ("from pydantic import validator", "pydantic v1 validator — use @field_validator (Pydantic v2)"),
    ("class Config:", "Pydantic v1 Config class — use model_config = ConfigDict(...) in Pydantic v2"),
    (".dict()", "Pydantic v1 .dict() — use .model_dump() in Pydantic v2"),
    (".json()", "Pydantic v1 .json() — use .model_dump_json() in Pydantic v2"),
    # Missing response_model is a common OpenAPI doc gap
    # Unsafe CORS
    ('allow_origins=["*"]', "Wildcard CORS allow_origins — restrict to known origins in production"),
    ("allow_credentials=True", "allow_credentials=True with wildcard origins is a CORS vulnerability"),
    # Raw Exception raises without HTTPException
    ("raise Exception(", "Raise HTTPException instead of bare Exception in FastAPI routes"),
    ("raise ValueError(", "Raise HTTPException instead of ValueError in FastAPI routes — clients get 500 not 4xx"),
    # Missing rate limiting signal
    # (checked holistically in static_scan, not line-by-line)
]

# Patterns that should be present in a FastAPI module
_FASTAPI_REQUIRED = [
    ("from fastapi import", "Missing FastAPI import"),
    ("from pydantic import BaseModel", "No Pydantic BaseModel import — request/response bodies must be validated"),
]

class FastAPIReviewer(AgentBase):
    """
    Reviews FastAPI route modules for async correctness, Pydantic v2 schema
    usage, dependency injection patterns, OpenAPI documentation quality,
    rate limiting (slowapi), CORS configuration, response model types, and
    structured error handling via HTTPException.
    """

    def __init__(self):
        super().__init__(agent_id="fastapi_reviewer", name="FastAPIReviewer", district="coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["review_fastapi", "review"]
        logger.info("[VECTOR][fastapi_reviewer] FastAPIReviewer initialized")

    async def review(self, code: str, filename: str = "", context: str = "") -> dict:
        """Review FastAPI code and return structured feedback."""
        try:
            # RULE 1 — session_hydration_prompt() before every LLM call
            try:
                from core.loop.context_engine import ContextEngine
                hydration = ContextEngine().session_hydration_prompt(
                    {"task": "fastapi_review", "file": filename}
                )
            except Exception as _h:
                logger.warning("[VECTOR][fastapi_reviewer] hydration failed: {}", _h)
                hydration = ""

            static_issues = self._static_scan(code, filename)

            if os.environ.get("VECTOR_FASTAPI_REVIEW_LLM") != "1":
                feedback = "LLM review disabled; returned static FastAPI scan results."
                return {
                    "agent": self.name,
                    "filename": filename,
                    "issues": static_issues,
                    "feedback": feedback,
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

            all_issues = static_issues + [i for i in llm_issues if i not in static_issues]

            if all_issues:
                self.deduct_points(len(all_issues) * 2, "fastapi_review_issues")
            else:
                self.award_points(5, "fastapi_review_clean")

            logger.info(
                "[VECTOR][fastapi_reviewer] reviewed {}: {} static + {} LLM issues",
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
            logger.error("[VECTOR][fastapi_reviewer] review error: {}", e)
            static_issues = self._static_scan(code, filename)
            return {
                "agent": self.name,
                "filename": filename,
                "issues": static_issues,
                "feedback": "Provider review unavailable; returned static FastAPI scan results.",
                "issue_count": len(static_issues),
                "static_issue_count": len(static_issues),
                "degraded": True,
                "warning": str(e),
            }

    def _static_scan(self, code: str, filename: str) -> list[dict]:
        """Static checks for FastAPI-specific anti-patterns."""
        issues: list[dict] = []
        lines = code.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, message in _FASTAPI_BANNED:
                if pattern in line:
                    severity = (
                        "HIGH" if any(w in message.upper() for w in ["CORS", "VULNERABILITY", "CREDENTIALS"])
                        else "MED"
                    )
                    issues.append({"text": f"Line {i}: {message}", "severity": severity, "line": i})

        # Holistic checks that require full-file context
        is_fastapi_module = "from fastapi" in code or "APIRouter" in code or "FastAPI()" in code

        if is_fastapi_module:
            # Required patterns
            for pattern, message in _FASTAPI_REQUIRED:
                if pattern not in code:
                    issues.append({"text": message, "severity": "MED", "line": 0})

            # response_model check: @app.get/post without response_model= suggests undocumented API
            import re
            decorator_lines = [
                (i + 1, l) for i, l in enumerate(lines)
                if re.search(r'@(app|router)\.(get|post|put|delete|patch)\(', l)
                and "response_model" not in l
            ]
            if decorator_lines:
                for lineno, _ in decorator_lines[:3]:  # cap at 3 to avoid noise
                    issues.append({
                        "text": f"Line {lineno}: Route decorator missing response_model= — OpenAPI schema incomplete",
                        "severity": "LOW",
                        "line": lineno,
                    })

            # slowapi / rate limiting check
            if "Limiter" not in code and "slowapi" not in code and "@limiter" not in code:
                issues.append({
                    "text": "No rate limiting detected (slowapi) — public endpoints vulnerable to abuse",
                    "severity": "MED",
                    "line": 0,
                })

            # Dependency injection — look for raw DB/session instantiation inside route handlers
            if "SessionLocal()" in code or "get_db" not in code and "Session(" in code:
                issues.append({
                    "text": "DB session created directly in route — use Depends(get_db) for proper lifecycle management",
                    "severity": "MED",
                    "line": 0,
                })

            # RULE 2 — async exception handling
            if "async def" in code and "HTTPException" not in code and "except Exception" not in code:
                issues.append({
                    "text": "RULE 2: async route handlers present but no HTTPException or broad except found",
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
            f"You are a FastAPI expert reviewing code for the VECTOR AI system.\n"
            f"File: {filename or 'unnamed.py'}{ctx_block}\n"
            f"=== STATIC PRE-SCAN RESULTS ===\n{static_summary}\n\n"
            f"=== FASTAPI-SPECIFIC REVIEW CRITERIA ===\n"
            f"1. async/await: All I/O-bound route handlers must use 'async def'. Sync handlers block the event loop.\n"
            f"2. Pydantic v2: Use BaseModel subclasses for all request/response bodies. Use @field_validator not @validator.\n"
            f"   Use model_config = ConfigDict(...) not inner Config class. Use .model_dump() not .dict().\n"
            f"3. Dependency injection: Use Depends() for DB sessions, auth, rate limiting — never instantiate in route body.\n"
            f"4. OpenAPI documentation: Every route must have response_model=, summary=, and meaningful description.\n"
            f"   Use status_code= explicitly. Tag routes with tags=[...] for logical grouping.\n"
            f"5. Rate limiting: slowapi Limiter must be applied to all public endpoints. @limiter.limit('X/minute').\n"
            f"6. CORS: Never use allow_origins=['*'] in production. allow_credentials=True requires explicit origins.\n"
            f"7. Response model types: Use typed response models (not dict). Never return raw dicts from routes.\n"
            f"8. Error handling: Raise HTTPException(status_code=..., detail=...) — not bare Exception/ValueError.\n"
            f"   Use exception handlers (@app.exception_handler) for global error shapes.\n"
            f"9. Security headers: Use middleware for X-Content-Type-Options, X-Frame-Options, HSTS.\n"
            f"10. Lifespan: Use @asynccontextmanager lifespan (not deprecated @app.on_event).\n\n"
            f"=== CODE TO REVIEW ===\n```python\n{snippet}\n```\n\n"
            f"Return findings as a bullet list. For each issue:\n"
            f"- [SEVERITY] Description (line N if known)\n"
            f"SEVERITY: CRITICAL, HIGH, MED, or LOW. If clean, write 'No issues found.'"
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
                    "HIGH" if any(w in text.upper() for w in ["CRITICAL", "CORS", "SECURITY", "INJECTION", "CREDENTIAL"])
                    else "MED" if any(w in text.upper() for w in ["WARNING", "MISSING", "ASYNC", "PYDANTIC", "RATE", "RESPONSE"])
                    else "LOW"
                )
                issues.append({"text": text, "severity": severity})
        return issues

    _SUPPORTED_TASK_TYPES = ("review_fastapi", "review")

    async def run(self, task: dict) -> dict:
        """Governor entrypoint — routes by task['type'] to the real review logic.

        task = {"type": "review_fastapi", "params": {"code": ..., "filename": ...}}
        Legacy callers passing a flat dict (code/filename at top level, no
        "type" key) are still honored for backward compatibility.
        """
        task = task or {}
        task_type = task.get("type", "review_fastapi")
        # 2026-09-30 (Codex independent review finding, same cycle -- see
        # districts/security/data_redactor.py's identical fix): the old
        # `task.get("params", task)` only falls back to `task` when the
        # "params" KEY is absent entirely, not when its value is falsy --
        # a caller sending {"type": "review_fastapi", "code": "...",
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
        """Answer a free-text question directly, grounded in FastAPIReviewer's
        role. Never touches the LLM-review kill switch — this is a plain
        conversational answer, not a code review."""
        try:
            from core.inference.provider_client import ProviderClient
            sys_prompt = (
                "You are FastAPIReviewer, VECTOR's FastAPI-specific code quality "
                "reviewer. You check async/await correctness, Pydantic v2 schemas, "
                "dependency injection, OpenAPI docs, rate limiting (slowapi), CORS "
                "config, response model types, and error handling. Answer the "
                "user's question directly and concisely."
            )
            result = await ProviderClient().chat(
                messages=[{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": query}],
                model="domain:coding.review",
                tier="coding",
                temperature=0.3,
                max_tokens=600,
                caller_id="fastapi_reviewer",
            )
            return {"agent": self.name, "status": "ok", "response": result.content.strip()}
        except Exception as e:
            logger.error("[VECTOR][fastapi_reviewer] _answer_query error: {}", e)
            return {"agent": self.name, "status": "error", "error": str(e)}

    async def run_forever(self) -> None:
        """RULE 2 — never stops. Event-driven; sleeps between polls."""
        logger.info("[VECTOR][fastapi_reviewer] run_forever started — event-driven mode")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("[VECTOR][fastapi_reviewer] tick error: {}", e)
                self.deduct_points(5, "tick_error")
        logger.warning("[VECTOR][fastapi_reviewer] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    reviewer = FastAPIReviewer()

    sample_bad = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        'add_middleware("CORSMiddleware", allow_origins=["*"], allow_credentials=True)\n'
        "@app.get('/items')\n"
        "def get_items():\n"
        "    raise Exception('oops')\n"
        "    return {}\n"
    )
    sample_clean = (
        "from fastapi import FastAPI, Depends, HTTPException\n"
        "from pydantic import BaseModel\n"
        "from slowapi import Limiter\n"
        "from loguru import logger\n"
        "from core.config import CONFIG\n\n"
        "class ItemResponse(BaseModel):\n"
        "    id: int\n"
        "    name: str\n\n"
        "limiter = Limiter(key_func=lambda r: r.client.host)\n"
        "app = FastAPI()\n\n"
        "@app.get('/items', response_model=ItemResponse, summary='Get item')\n"
        "@limiter.limit('60/minute')\n"
        "async def get_items(item_id: int) -> ItemResponse:\n"
        "    try:\n"
        "        logger.info('[VECTOR][items] fetching {}'.format(item_id))\n"
        "        return ItemResponse(id=item_id, name='test')\n"
        "    except Exception as e:\n"
        "        logger.error('[VECTOR][items] error: {}', e)\n"
        "        raise HTTPException(status_code=500, detail=str(e))\n"
    )

    bad_issues = reviewer._static_scan(sample_bad, "bad_router.py")
    clean_issues = reviewer._static_scan(sample_clean, "clean_router.py")

    ok = len(bad_issues) > 0 and isinstance(clean_issues, list)
    print(f"  bad router static issues: {len(bad_issues)}")
    print(f"  clean router static issues: {len(clean_issues)}")
    print(f"  agent name: {reviewer.name}, district: {reviewer.district}")
    print("✅ fastapi_reviewer.py OK" if ok else "❌ FAILED")
