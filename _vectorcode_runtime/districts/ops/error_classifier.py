"""
Error Classifier — intelligent error categorization for VECTOR's infrastructure.

Wraps vectorcode/src/agent/error_classifier.py concept.
Categorizes errors into actionable types: rate_limit, timeout, auth, model_not_found,
context_overflow, network, etc. Enables VECTOR to self-heal by knowing WHY something failed.
"""
import asyncio
import re
import datetime


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

# Error fingerprints: (pattern, error_type, severity, action)
_ERROR_RULES: list[tuple[re.Pattern, str, str, str]] = [
    # Rate limits
    (re.compile(r"429|rate.?limit|too.many.requests|quota.exceed", re.I),
     "rate_limit", "warning", "wait_and_retry"),
    # Authentication
    (re.compile(r"401|403|unauthorized|forbidden|invalid.api.key|authentication", re.I),
     "auth_failure", "critical", "check_credentials"),
    # Model not found
    (re.compile(r"model.not.found|no.such.model|pull.model|not.running", re.I),
     "model_not_found", "error", "pull_or_switch_model"),
    # Context overflow
    (re.compile(r"context.length|too.many.token|max.token|context.window", re.I),
     "context_overflow", "warning", "compress_context"),
    # Timeout
    (re.compile(r"timeout|timed.out|connection.timeout|read.timeout", re.I),
     "timeout", "warning", "retry_with_longer_timeout"),
    # Network
    (re.compile(r"connection.refused|connection.error|network|dns|socket|unreachable", re.I),
     "network_error", "error", "check_connectivity"),
    # Disk/Memory
    (re.compile(r"out.of.memory|oom|disk.full|no.space", re.I),
     "resource_exhausted", "critical", "free_resources"),
    # Ollama daemon
    (re.compile(r"ollama|daemon.not.running|port.11434", re.I),
     "ollama_down", "error", "restart_ollama"),
    # Python/code errors
    (re.compile(r"ImportError|ModuleNotFoundError", re.I),
     "missing_dependency", "error", "pip_install_dependency"),
    (re.compile(r"AttributeError|TypeError|ValueError", re.I),
     "code_bug", "error", "fix_code"),
    # Generic server errors
    (re.compile(r"500|502|503|internal.server.error|service.unavailable", re.I),
     "server_error", "warning", "retry_later"),
]

_SEVERITY_LEVELS = {"critical": 4, "error": 3, "warning": 2, "info": 1}

_RECOVERY_ACTIONS = {
    "wait_and_retry":             "Wait 60s then retry. Use local Ollama as fallback.",
    "check_credentials":          "Check API keys in .env. Run: CredentialManager scan.",
    "pull_or_switch_model":       "Run: ollama pull <model>. Or switch to vector-focus.",
    "compress_context":           "Use ContextCompressor to reduce message history.",
    "retry_with_longer_timeout":  "Increase timeout parameter. Try vector-focus for quick tasks.",
    "check_connectivity":         "Check internet/VPN. Verify Ollama daemon is running.",
    "free_resources":             "Close other apps. Restart VECTOR. Check disk space.",
    "restart_ollama":             "Run: ollama serve. Or restart the Ollama tray app.",
    "pip_install_dependency":     "Run: pip install <missing_package>.",
    "fix_code":                   "Bug in VECTOR code. Check recent changes.",
    "retry_later":                "Provider service issue. Retry in 5 minutes.",
}


class ErrorClassifier(AgentBase):
    """
    Intelligent error classifier for VECTOR's runtime errors.
    Categorizes failures by type, severity, and provides specific recovery actions.
    Wraps vectorcode's error_classifier pattern.
    """

    def __init__(self):
        super().__init__(agent_id="error_classifier_001",
                         name="ErrorClassifier", district="ops")
        self.capabilities = ["batch", "classify", "critical", "retry_check"]
        self._memory: EpisodicMemory | None = None
        self._error_history: list[dict] = []
        logger.info("[VECTOR][error_clf] initialized with {} rules", len(_ERROR_RULES))

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def classify(self, error: str | Exception, context: str = "") -> dict:
        """Classify an error into actionable type + recovery action."""
        error_text = str(error)
        full_text = f"{error_text} {context}"

        matched = []
        for pattern, error_type, severity, action in _ERROR_RULES:
            if pattern.search(full_text):
                matched.append({
                    "type": error_type,
                    "severity": severity,
                    "action": action,
                    "recovery": _RECOVERY_ACTIONS.get(action, "Investigate manually"),
                })

        if not matched:
            best = {
                "type": "unknown_error",
                "severity": "error",
                "action": "investigate",
                "recovery": "Examine logs. Check if this is a new error type.",
            }
        else:
            # Return highest severity match
            best = max(matched, key=lambda x: _SEVERITY_LEVELS.get(x["severity"], 0))

        result = {
            "error_text": error_text[:200],
            "context": context[:100] if context else "",
            "classified_as": best["type"],
            "severity": best["severity"],
            "recovery_action": best["action"],
            "recovery_instructions": best["recovery"],
            "all_matches": [m["type"] for m in matched],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Track in history
        self._error_history.append(result)
        if len(self._error_history) > 100:
            self._error_history.pop(0)

        return result

    def classify_batch(self, errors: list[str]) -> list[dict]:
        """Classify multiple errors at once."""
        return [self.classify(e) for e in errors]

    def error_summary(self) -> dict:
        """Aggregate stats on classified errors this session."""
        if not self._error_history:
            return {"total": 0, "by_type": {}, "most_common": "none", "critical_count": 0}

        by_type: dict[str, int] = {}
        for e in self._error_history:
            t = e["classified_as"]
            by_type[t] = by_type.get(t, 0) + 1

        most_common = max(by_type, key=lambda k: by_type[k])
        critical = sum(1 for e in self._error_history if e["severity"] == "critical")
        return {
            "total": len(self._error_history),
            "by_type": by_type,
            "most_common": most_common,
            "critical_count": critical,
            "recommendation": (
                f"Critical errors detected: {critical} — investigate immediately"
                if critical > 0
                else f"Most common error: {most_common} ({by_type[most_common]} times)"
            ),
        }

    def should_retry(self, error: str | Exception) -> dict:
        """Determine if a failed operation should be retried and after how long."""
        classification = self.classify(error)
        retry_map = {
            "rate_limit":    {"should_retry": True, "after_seconds": 60,  "max_retries": 3},
            "timeout":       {"should_retry": True, "after_seconds": 5,   "max_retries": 3},
            "server_error":  {"should_retry": True, "after_seconds": 30,  "max_retries": 2},
            "network_error": {"should_retry": True, "after_seconds": 10,  "max_retries": 3},
            "ollama_down":   {"should_retry": True, "after_seconds": 5,   "max_retries": 5},
            "auth_failure":  {"should_retry": False, "after_seconds": 0,  "max_retries": 0},
            "code_bug":      {"should_retry": False, "after_seconds": 0,  "max_retries": 0},
            "context_overflow": {"should_retry": True, "after_seconds": 0, "max_retries": 1},
        }
        retry_info = retry_map.get(
            classification["classified_as"],
            {"should_retry": False, "after_seconds": 0, "max_retries": 0},
        )
        return {**classification, **retry_info}

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
        task_type = task.get("type", "classify")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "classify":
                error = task.get("error", "")
                context = task.get("context", "")
                result = self.classify(error, context)
                if result["severity"] in ("critical", "error"):
                    self._get_memory().store(
                        event_type="error_classified",
                        content=f"Error: {result['classified_as']} — {result['error_text'][:80]}",
                        tags=["ops", "error", result["classified_as"]],
                        source="error_classifier",
                    )
                self.award_points(10, "error_classified")
                return {"status": "ok", "classification": result}

            elif task_type == "batch":
                results = self.classify_batch(task.get("errors", []))
                self.award_points(15, "batch_classified")
                return {"status": "ok", "classifications": results, "count": len(results)}

            elif task_type == "retry_check":
                result = self.should_retry(task.get("error", ""))
                self.award_points(5, "retry_checked")
                return {"status": "ok", "retry_decision": result}

            else:  # summary
                summary = self.error_summary()
                self.award_points(10, "error_summary_generated")
                return {"status": "ok", "summary": summary}

        except Exception as e:
            logger.error("[VECTOR][error_clf] {}", e)
            self.deduct_points(20, "classification_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ErrorClassifier()
        c1 = agent.classify("HTTPStatusError: 429 Too Many Requests", "gemini API call")
        print(f"[OK] classify rate_limit: type={c1['classified_as']} action={c1['recovery_action']}")
        c2 = agent.classify("Connection refused localhost:11434", "ollama chat")
        print(f"[OK] classify ollama_down: type={c2['classified_as']} severity={c2['severity']}")
        c3 = agent.classify("AttributeError: 'NoneType' has no attribute 'run'")
        print(f"[OK] classify code_bug: type={c3['classified_as']}")
        retry = agent.should_retry("timeout after 30s")
        print(f"[OK] retry: should={retry['should_retry']} after={retry['after_seconds']}s")
        summary = agent.error_summary()
        print(f"[OK] summary: total={summary['total']} most_common={summary['most_common']}")
        result = await agent.run({"type": "summary"})
        print(f"[OK] run: status={result['status']}")
        print("error_classifier.py OK")

    asyncio.run(_smoke())
