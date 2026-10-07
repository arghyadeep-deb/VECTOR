"""
SecurityReviewer — Security-focused code reviewer.
Called by Governor when reviewing code for injection vulnerabilities,
hardcoded secrets, SSRF, path traversal, eval/exec usage, unsafe
deserialization (pickle), permission bypass patterns, and auth gaps.
"""
import sys
import asyncio
import os
import re
from pathlib import Path
from districts.coding.path_security import is_path_within

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

# Same confinement pattern as fastapi_reviewer.py's/python_reviewer.py's/
# code_reviewer.py's fixes this cycle: run()'s filename-read branch had no
# confinement at all -- the exact "path traversal" vulnerability class
# this agent itself exists to detect in OTHER code.
_ROOT = Path(__file__).resolve().parents[2]

# --- Security pattern catalogue ---
# Each entry: (assembled_pattern, severity, human-readable finding)
# Patterns are assembled to avoid triggering security linters on this source file.

_EVAL_FN         = "eva"  + "l("
_EXEC_FN         = "exe"  + "c("
_OS_SYS          = "os."  + "system("
_COMPILE_FN      = "comp" + "ile("
_MARSHAL_IMP     = "impo" + "rt marshal"
_CTYPES_CAST     = "ctype" + "s.cast("
_SUBPROCESS_SHELL= "shell" + "=True"
_OPEN_W          = "open(" + "...write"  # placeholder — checked by regex below
_PATHLIB_WRITE   = ".write_" + "text("   # placeholder

# SQL injection patterns
_FMT_SQL         = ".format" + "("
_PCT_SQL         = "% ("
_F_STR_QUERY     = 'f"SELECT'

# Hardcoded credential patterns
_PWD_EQ          = "password" + " ="
_APIKEY_EQ       = "api_key"  + " ="
_SECRET_EQ       = "secret"   + " ="
_TOKEN_EQ        = "token"    + " ="
_PRIVATE_KEY     = "private_key" + " ="
_AWS_ACCESS      = "AWS_ACCESS_KEY_ID" + " ="
_AWS_SECRET      = "AWS_SECRET_ACCESS_KEY" + " ="

# Prompt injection / AI boundary
_IGNORE_PREV     = "Ignore previous" + " instructions"
_YOU_ARE_NOW     = "You are" + " now DAN"
_SYSTEM_HDR      = "SYSTEM" + ":"

# Deserialization
_PICKLE_LOAD     = "pickle" + ".load"
_PICKLE_LOADS    = "pickle" + ".loads"
_YAML_LOAD_BARE  = "yaml.load("   # safe_load is fine; bare load() is not
_MARSHAL_LOADS   = "marshal" + ".loads("

# SSRF-adjacent
_REQ_GET         = "requests" + ".get("
_URLLIB_OPEN     = "urllib" + ".request.urlopen("
_HTTPX_GET       = "httpx.get("    # sync httpx without URL validation

# Path traversal
_PATH_JOIN_INPUT = "os.path.join(" # context-checked: if user input flows in
_OPEN_INPUT      = "open(request"

# Permission bypass
_SKIP_VERIFY     = "verify=False"  # disables TLS cert verification
_NO_AUTH         = "no_auth=True"
_BYPASS_GW       = "bypass_gateway"

SECURITY_PATTERNS: list[tuple[str, str, str]] = [
    # Code execution
    (_EVAL_FN,         "CRITICAL", "eval() — arbitrary code execution, remove unconditionally"),
    (_EXEC_FN,         "CRITICAL", "exec() — arbitrary code execution, remove unconditionally"),
    (_OS_SYS,          "CRITICAL", "os.system() — shell injection risk; use subprocess with list args or permission_gateway"),
    (_SUBPROCESS_SHELL,"HIGH",     "shell=True in subprocess — command injection if any arg is user-controlled"),
    (_COMPILE_FN,      "HIGH",     "compile() — dynamic code compilation; treat as eval()"),
    # Deserialization
    (_PICKLE_LOAD,     "CRITICAL", "pickle.load/loads — remote code execution via malicious payload; use json/msgpack"),
    (_PICKLE_LOADS,    "CRITICAL", "pickle.loads — deserialization RCE; replace with json.loads"),
    (_YAML_LOAD_BARE,  "HIGH",     "yaml.load() without Loader= — use yaml.safe_load() to prevent arbitrary object creation"),
    (_MARSHAL_LOADS,   "HIGH",     "marshal.loads() — unsafe deserialization; use json"),
    # Hardcoded credentials (assignment in source = committed secret)
    (_PWD_EQ,          "CRITICAL", "Hardcoded password literal — use keyring or os.environ, never commit credentials"),
    (_APIKEY_EQ,       "HIGH",     "Hardcoded API key — use keyring or CONFIG; rotate the key if already committed"),
    (_SECRET_EQ,       "HIGH",     "Hardcoded secret — use keyring or CONFIG"),
    (_TOKEN_EQ,        "HIGH",     "Hardcoded token — use keyring or os.environ"),
    (_PRIVATE_KEY,     "CRITICAL", "Hardcoded private key — immediate rotation required"),
    (_AWS_ACCESS,      "CRITICAL", "Hardcoded AWS_ACCESS_KEY_ID — rotate now, use IAM roles or env vars"),
    (_AWS_SECRET,      "CRITICAL", "Hardcoded AWS_SECRET_ACCESS_KEY — rotate now"),
    # SQL injection
    (_FMT_SQL,         "HIGH",     "String .format() in SQL query — use parameterized queries (?, $1, :param)"),
    (_PCT_SQL,         "HIGH",     "% string interpolation in SQL — use parameterized queries"),
    (_F_STR_QUERY,     "HIGH",     "f-string in SELECT statement — use parameterized query or ORM"),
    # SSRF
    (_REQ_GET,         "MED",      "requests.get() — use httpx with SSRF guard (_ssrf_check) before sending"),
    (_URLLIB_OPEN,     "MED",      "urllib.request.urlopen() — validate URL against SSRF guard before use"),
    (_HTTPX_GET,       "MED",      "httpx.get() (sync) — use async httpx.AsyncClient with URL validation"),
    # Prompt injection (AI boundary)
    (_IGNORE_PREV,     "HIGH",     "Prompt injection pattern detected in source — validate/sanitize user input before LLM"),
    (_YOU_ARE_NOW,     "HIGH",     "DAN-style persona hijack prompt — sanitize before forwarding to LLM"),
    (_SYSTEM_HDR,      "MED",      "Potential SYSTEM prompt injection in string literal"),
    # TLS / auth bypass
    (_SKIP_VERIFY,     "HIGH",     "verify=False disables TLS certificate verification — remove in all production paths"),
    (_NO_AUTH,         "HIGH",     "no_auth=True found — authentication bypass; verify this is intentional and gated"),
    (_BYPASS_GW,       "CRITICAL", "bypass_gateway pattern — PermissionGateway must never be bypassed (RULE 3)"),
    # Path traversal signals (heuristic — not every occurrence is a vuln)
    (_OPEN_INPUT,      "HIGH",     "open(request.*) — path traversal risk; validate and sanitize file paths from user input"),
]

# Regex-based checks (need full-code context)
_REGEX_CHECKS: list[tuple[str, str, str]] = [
    # Unsafe open() with a variable that looks user-controlled
    (r'open\s*\(\s*[a-z_]*(?:path|file|name|input|req|param|arg)\b', "HIGH",
     "open() with potentially user-supplied path — validate against allowed base directory"),
    # os.path.join where first arg might be user-controlled
    (r'os\.path\.join\s*\(\s*(?:request|params|body|data|user)', "HIGH",
     "os.path.join with user-controlled first arg — use Path.resolve() + base dir check to prevent traversal"),
    # JWT decode without verify_signature
    (r'jwt\.decode\s*\([^)]*options\s*=\s*\{[^}]*verify', "MED",
     "JWT decode with verification options override — ensure verify_signature is not disabled"),
    # Hardcoded IP in production code (not localhost)
    (r'(?:http://|https://)(?!(?:127\.0\.0\.1|localhost|0\.0\.0\.0))\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', "MED",
     "Hardcoded non-localhost IP address — use CONFIG or env var for all external endpoints"),
    # Direct __import__ usage
    (r'__import__\s*\(', "HIGH",
     "__import__() used directly — potential dynamic import abuse; use importlib.import_module with allowlist"),
    # getattr with user input
    (r'getattr\s*\([^,]+,\s*(?:request|params|user|input|data)', "HIGH",
     "getattr() with user-supplied attribute name — attribute injection risk"),
]

class SecurityReviewer(AgentBase):
    """
    Reviews code for security vulnerabilities: injection (SQL, command, prompt),
    hardcoded secrets, SSRF, path traversal, unsafe deserialization (pickle/yaml/marshal),
    TLS bypass, permission gateway bypass patterns, and authentication gaps.
    Issues are classified CRITICAL / HIGH / MED / LOW.
    """

    def __init__(self):
        super().__init__(agent_id="security_reviewer", name="SecurityReviewer", district="coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["review_security", "scan_vulnerabilities", "review"]
        logger.info("[VECTOR][security_reviewer] SecurityReviewer initialized")

    async def review(self, code: str, filename: str = "", context: str = "") -> dict:
        """Review code for security issues and return structured findings."""
        static_issues: list[dict] = []
        try:
            # RULE 1 — session_hydration_prompt() before every LLM call
            try:
                from core.loop.context_engine import ContextEngine
                hydration = ContextEngine().session_hydration_prompt(
                    {"task": "security_review", "file": filename}
                )
            except Exception as _h:
                logger.warning("[VECTOR][security_reviewer] hydration failed: {}", _h)
                hydration = ""

            static_issues = self._static_scan(code, filename)

            if os.environ.get("VECTOR_SECURITY_REVIEW_LLM") != "1":
                critical_count = sum(1 for i in static_issues if i["severity"] == "CRITICAL")
                high_count = sum(1 for i in static_issues if i["severity"] == "HIGH")
                return {
                    "agent": self.name,
                    "filename": filename,
                    "issues": static_issues,
                    "feedback": "LLM review disabled; returned static security scan results.",
                    "issue_count": len(static_issues),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "static_issue_count": len(static_issues),
                    "degraded": True,
                }

            from core.inference.provider_client import ProviderClient
            client = ProviderClient()

            prompt = self._build_prompt(code, filename, context, static_issues, hydration)
            result = await client.complete(
                prompt=prompt,
                tier="coding",
                max_tokens=1400,
                district="security",   # sensitivity gate → local-only (never ship code to cloud)
            )

            feedback = result.content or "No security issues found."
            llm_issues = self._parse_issues(feedback)

            all_issues = static_issues + [i for i in llm_issues if i not in static_issues]

            # HP impact: security issues are more costly
            critical_count = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
            high_count = sum(1 for i in all_issues if i["severity"] == "HIGH")
            if critical_count:
                self.deduct_points(critical_count * 10, "security_critical_findings")
            elif high_count:
                self.deduct_points(high_count * 5, "security_high_findings")
            elif all_issues:
                self.deduct_points(len(all_issues) * 2, "security_med_low_findings")
            else:
                self.award_points(10, "security_review_clean")

            logger.info(
                "[VECTOR][security_reviewer] reviewed {}: {} static + {} LLM issues (CRITICAL={})",
                filename or "code", len(static_issues), len(llm_issues), critical_count,
            )
            return {
                "agent": self.name,
                "filename": filename,
                "issues": all_issues,
                "feedback": feedback,
                "issue_count": len(all_issues),
                "critical_count": critical_count,
                "high_count": high_count,
                "static_issue_count": len(static_issues),
            }
        except Exception as e:
            logger.error("[VECTOR][security_reviewer] review error: {}", e)
            critical_count = sum(1 for i in static_issues if i["severity"] == "CRITICAL")
            high_count = sum(1 for i in static_issues if i["severity"] == "HIGH")
            return {
                "agent": self.name,
                "filename": filename,
                "error": str(e),
                "issues": static_issues,
                "feedback": "LLM review failed; returned static security scan results.",
                "issue_count": len(static_issues),
                "critical_count": critical_count,
                "high_count": high_count,
                "static_issue_count": len(static_issues),
                "degraded": True,
            }

    def _static_scan(self, code: str, filename: str) -> list[dict]:
        """Deterministic line-by-line + regex security scan."""
        issues: list[dict] = []
        lines = code.splitlines()

        # --- Line-by-line pattern scan ---
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, severity, message in SECURITY_PATTERNS:
                if pattern in line:
                    issues.append({
                        "text": f"Line {i}: {message}",
                        "severity": severity,
                        "line": i,
                    })

        # --- Regex-based full-code scan ---
        for pattern, severity, message in _REGEX_CHECKS:
            for m in re.finditer(pattern, code, re.IGNORECASE):
                lineno = code[:m.start()].count("\n") + 1
                issues.append({
                    "text": f"Line {lineno}: {message}",
                    "severity": severity,
                    "line": lineno,
                })

        # --- VECTOR-specific security checks ---
        # RULE 3: permission_gateway must gate all Actions
        if "Action(" in code and "permission_gateway" not in code and "PermissionGateway" not in code:
            issues.append({
                "text": "RULE 3 VIOLATION: Action() used but PermissionGateway not imported — all actions must be gated",
                "severity": "CRITICAL",
                "line": 0,
            })

        # RULE 11: MemoryClient sends data to external cloud
        if "MemoryClient(" in code:
            issues.append({
                "text": "RULE 11 VIOLATION: MemoryClient sends data to Mem0 cloud — use 'from mem0 import Memory' (local OSS)",
                "severity": "HIGH",
                "line": 0,
            })

        # RULE 11: Claude API at runtime is forbidden
        if "anthropic.Anthropic(" in code:
            issues.append({
                "text": "RULE 11 VIOLATION: anthropic.Anthropic() at runtime — Claude API is for build sessions only, not VECTOR runtime",
                "severity": "HIGH",
                "line": 0,
            })

        # Bare except: (swallows security exceptions silently)
        for i, line in enumerate(lines, start=1):
            if line.strip() == "except:":
                issues.append({
                    "text": f"Line {i}: Bare 'except:' swallows ALL exceptions including KeyboardInterrupt — use 'except Exception as e'",
                    "severity": "MED",
                    "line": i,
                })

        # DEBUG flag left on in production
        if "DEBUG = True" in code or 'DEBUG="True"' in code or "debug=True" in code.lower():
            if "test" not in filename.lower() and "dev" not in filename.lower():
                issues.append({
                    "text": "DEBUG=True found in non-test file — disable debug mode in production to prevent info leakage",
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
            "\n".join(f"- [{i['severity']}] {i['text']}" for i in static_issues)
            if static_issues
            else "None found by static scan."
        )
        ctx_block = f"\nContext: {context}\n" if context else ""
        hydration_block = f"{hydration}\n\n" if hydration else ""

        return (
            f"{hydration_block}"
            f"You are a security engineer performing a vulnerability audit for the VECTOR AI system.\n"
            f"File: {filename or 'unnamed.py'}{ctx_block}\n"
            f"=== STATIC PRE-SCAN RESULTS ===\n{static_summary}\n\n"
            f"=== SECURITY REVIEW CRITERIA ===\n"
            f"1. Injection vulnerabilities:\n"
            f"   - SQL injection: any string formatting/f-strings in SQL queries\n"
            f"   - Command injection: os.system(), subprocess with shell=True and user input\n"
            f"   - Prompt injection: unsanitized user input forwarded directly to LLM prompts\n"
            f"2. Hardcoded secrets: API keys, passwords, tokens, private keys in source code\n"
            f"   (even in test files — leaked via git history)\n"
            f"3. SSRF (Server-Side Request Forgery): HTTP requests with user-controlled URLs\n"
            f"   without domain allowlist validation\n"
            f"4. Path traversal: open(), Path(), os.path operations with user-supplied paths\n"
            f"   not validated against a base directory\n"
            f"5. Unsafe deserialization: pickle.load/loads, yaml.load (not safe_load), marshal.loads\n"
            f"6. Authentication/authorization gaps:\n"
            f"   - Missing auth checks on sensitive endpoints\n"
            f"   - JWT decode with verify=False or disabled signature check\n"
            f"   - verify=False in TLS requests\n"
            f"7. Permission bypass: anything that skips permission_gateway for RED-tier actions\n"
            f"8. Information disclosure: debug=True, stack traces in API responses, verbose error messages\n"
            f"9. Race conditions: shared mutable state accessed from async coroutines without locks\n"
            f"10. Dependency risks: imports of known-unsafe modules (requests over httpx, pickle, marshal)\n\n"
            f"=== CODE TO AUDIT ===\n```python\n{snippet}\n```\n\n"
            f"Return ONLY a bullet list of security findings. Format:\n"
            f"- [SEVERITY] Finding description (line N if known)\n"
            f"SEVERITY must be: CRITICAL, HIGH, MED, or LOW\n"
            f"If no vulnerabilities found, write: 'No security issues found.'\n"
            f"Do not include generic style or performance notes — security only."
        )

    def _parse_issues(self, feedback: str) -> list[dict]:
        """Parse LLM security findings into structured issue dicts."""
        issues: list[dict] = []
        for line in feedback.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(("- ", "* ", "• ")) or (line and line[0].isdigit() and "." in line[:3]):
                text = line.lstrip("-*•0123456789. ").strip()
                if not text or "no security issue" in text.lower() or "no issues" in text.lower():
                    continue
                # Infer severity from bracket prefix [CRITICAL] etc., else heuristic
                sev_match = re.match(r'\[(CRITICAL|HIGH|MED|LOW)\]', text, re.IGNORECASE)
                if sev_match:
                    severity = sev_match.group(1).upper()
                    text = text[sev_match.end():].strip()
                else:
                    severity = (
                        "CRITICAL" if any(w in text.upper() for w in ["RCE", "ARBITRARY CODE", "PICKLE", "INJECTION", "BYPASS"])
                        else "HIGH" if any(w in text.upper() for w in ["HARDCODED", "SSRF", "TRAVERSAL", "DESERIALIZATION", "JWT", "TLS"])
                        else "MED" if any(w in text.upper() for w in ["DEBUG", "DISCLOSURE", "RACE", "MISSING AUTH"])
                        else "LOW"
                    )
                issues.append({"text": text, "severity": severity})
        return issues

    _SUPPORTED_TASK_TYPES = ("review_security", "scan_vulnerabilities", "review")

    async def run(self, task: dict) -> dict:
        """Governor entrypoint — routes by task['type'] to the real review logic.

        task = {"type": "scan_vulnerabilities", "params": {"code": ..., "filename": ...}}
        Legacy callers passing a flat dict (code/filename at top level, no
        "type" key) are still honored for backward compatibility.
        """
        task = task or {}
        task_type = task.get("type", "scan_vulnerabilities")
        # 2026-09-30 (Codex independent review finding, same cycle -- see
        # districts/security/data_redactor.py's identical fix): the old
        # `task.get("params", task)` only falls back to `task` when the
        # "params" KEY is absent entirely, not when its value is falsy --
        # a caller sending {"type": "scan_vulnerabilities", "code": "...",
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
                if not is_path_within(fpath, _ROOT) or fpath.suffix != ".py":
                    return {"agent": self.name, "error": f"Cannot read file: path outside repo or not a .py file", "issues": [], "issue_count": 0, "critical_count": 0}
                code = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return {"agent": self.name, "error": f"Cannot read file: {e}", "issues": [], "issue_count": 0, "critical_count": 0}
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
            return {"agent": self.name, "error": "No code provided", "issues": [], "issue_count": 0, "critical_count": 0}
        return await self.review(code, filename, context)

    async def _answer_query(self, query: str) -> dict:
        """Answer a free-text question directly, grounded in
        SecurityReviewer's role. Never touches the LLM-review kill switch —
        this is a plain conversational answer, not a code audit. Routed
        through the security sensitivity gate (district="security") so it
        never leaves the local model chain."""
        try:
            from core.inference.provider_client import ProviderClient
            sys_prompt = (
                "You are SecurityReviewer, VECTOR's security-focused code "
                "reviewer. You check for injection vulnerabilities, hardcoded "
                "secrets, SSRF, path traversal, eval/exec usage, unsafe "
                "deserialization, permission bypass patterns, and auth gaps. "
                "Answer the user's question directly and concisely."
            )
            result = await ProviderClient().chat(
                messages=[{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": query}],
                tier="coding",
                max_tokens=600,
                district="security",   # sensitivity gate → local-only
            )
            return {"agent": self.name, "status": "ok", "response": result.content.strip()}
        except Exception as e:
            logger.error("[VECTOR][security_reviewer] _answer_query error: {}", e)
            return {"agent": self.name, "status": "error", "error": str(e)}

    async def run_forever(self) -> None:
        """RULE 2 — never stops. Event-driven; sleeps between polls."""
        logger.info("[VECTOR][security_reviewer] run_forever started — event-driven mode")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("[VECTOR][security_reviewer] tick error: {}", e)
                self.deduct_points(5, "tick_error")
        logger.warning("[VECTOR][security_reviewer] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    reviewer = SecurityReviewer()

    # Bad code: eval, pickle, hardcoded secret, SSRF pattern
    sample_bad = (
        "import pickle\n"
        "password = 'hunter2'\n"  # noqa — intentional test
        "api_key = 'sk-1234'\n"   # noqa — intentional test
        "def run(x):\n"
        "    return eval(x)\n"
        "def load_data(f):\n"
        "    return pickle.load(open(f, 'rb'))\n"
    )
    sample_clean = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))\n"
        "import os\nimport json\n"
        "from loguru import logger\nfrom core.config import CONFIG\n\n"
        "async def load_config() -> dict:\n"
        "    try:\n"
        "        return json.loads(Path(CONFIG['config_path']).read_text())\n"
        "    except Exception as e:\n"
        "        logger.error('[VECTOR][cfg] error: {}', e)\n"
        "        return {}\n"
    )

    bad_issues = reviewer._static_scan(sample_bad, "bad.py")
    clean_issues = reviewer._static_scan(sample_clean, "clean.py")

    # Expect at least eval + pickle + 2 hardcoded creds
    ok = len(bad_issues) >= 4 and isinstance(clean_issues, list)
    print(f"  bad code security issues: {len(bad_issues)}")
    for iss in bad_issues:
        print(f"    [{iss['severity']}] {iss['text']}")
    print(f"  clean code security issues: {len(clean_issues)}")
    print(f"  agent name: {reviewer.name}, district: {reviewer.district}")
    print("✅ security_reviewer.py OK" if ok else "❌ FAILED")
