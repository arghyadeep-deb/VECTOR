"""
Data Redactor — PII and sensitive data removal before LLM calls.

Wraps vectorcode/src/agent/redact.py capability.
Strips API keys, passwords, emails, phone numbers, credit cards, and
other sensitive patterns from any text before it leaves the device.
Enforces VECTOR's local-first privacy (Rule 11) by preventing accidental
PII leakage to cloud providers.
"""
import asyncio
import re


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

# Sensitive patterns with replacement tokens
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API keys
    (re.compile(r"sk-ant-api[0-9A-Za-z\-_]{20,}", re.IGNORECASE), "[ANTHROPIC_KEY_REDACTED]"),
    (re.compile(r"sk-or-[0-9A-Za-z\-_]{20,}", re.IGNORECASE),     "[OPENROUTER_KEY_REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),               "[AWS_KEY_REDACTED]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE),         "[GOOGLE_KEY_REDACTED]"),
    (re.compile(r"ghp_[0-9A-Za-z]{36}", re.IGNORECASE),            "[GITHUB_TOKEN_REDACTED]"),
    (re.compile(r"(Bearer|Authorization:)\s+[A-Za-z0-9\-._~+/]{20,}",
                re.IGNORECASE),                                      "[AUTH_TOKEN_REDACTED]"),
    # Credentials
    (re.compile(r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*\S+'), "[PASSWORD_REDACTED]"),
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+'),         "[API_KEY_REDACTED]"),
    # Personal data
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), "[EMAIL_REDACTED]"),
    (re.compile(r'\b(?:\+91|0)?[789]\d{9}\b'),                      "[PHONE_REDACTED]"),
    (re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'), "[CARD_REDACTED]"),
    # Private paths
    (re.compile(r'C:\\Users\\[A-Za-z0-9_\-]+\\'),                   "C:\\Users\\[USER]\\"),
    (re.compile(r'/home/[a-z0-9_\-]+/'),                            "/home/[USER]/"),
]

# These patterns are only checked in messages going to cloud providers
_CLOUD_ONLY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Full file paths that might reveal project structure
    (re.compile(r'[A-Za-z]:\\(?:[^\\\n"\']{1,50}\\){2,}'),          "[FILEPATH_REDACTED]"),
    (re.compile(r'(?:/[a-z0-9_\-]{1,30}){4,}'),                     "[FILEPATH_REDACTED]"),
]


class DataRedactor(AgentBase):
    """
    PII and secrets redactor for VECTOR's LLM pipeline.
    Strips sensitive data before any text reaches a cloud provider.
    Wraps vectorcode's redact.py capability.
    """

    def __init__(self):
        super().__init__(agent_id="data_redactor_001", name="DataRedactor", district="security")
        self.capabilities = ["cloud_safety", "data_redact", "privacy", "redact_messages", "redact_text", "security"]
        self._memory: EpisodicMemory | None = None
        logger.info("[VECTOR][redactor] initialized with {} patterns", len(_PATTERNS))

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def redact(self, text: str, cloud_mode: bool = False) -> tuple[str, list[str]]:
        """
        Redact sensitive data from text.
        Returns (redacted_text, list_of_what_was_redacted).
        cloud_mode=True applies stricter patterns for cloud-bound text.
        """
        findings = []
        result = text
        patterns = _PATTERNS + (_CLOUD_ONLY_PATTERNS if cloud_mode else [])
        for pattern, replacement in patterns:
            matches = pattern.findall(result)
            if matches:
                category = replacement.strip("[]").replace("_REDACTED", "").lower()
                findings.append(f"{category} ({len(matches)} occurrence{'s' if len(matches) > 1 else ''})")
                result = pattern.sub(replacement, result)
        return result, findings

    def redact_messages(self, messages: list[dict],
                        cloud_mode: bool = False) -> tuple[list[dict], list[str]]:
        """Redact all messages in a list. Returns (clean_messages, all_findings)."""
        all_findings = []
        clean = []
        for msg in messages:
            content = msg.get("content", "")
            if content:
                redacted, findings = self.redact(content, cloud_mode=cloud_mode)
                all_findings.extend(findings)
                clean.append({**msg, "content": redacted})
            else:
                clean.append(msg)
        return clean, all_findings

    def scan_for_secrets(self, text: str) -> dict:
        """Scan text for secrets without modifying it — report what was found."""
        findings = []
        for pattern, replacement in _PATTERNS:
            matches = pattern.findall(text)
            if matches:
                category = replacement.strip("[]").replace("_REDACTED", "").lower()
                for m in matches[:3]:  # limit to 3 examples per category
                    preview = str(m)[:20] + "..." if len(str(m)) > 20 else str(m)
                    findings.append({"type": category, "preview": preview})
        return {
            "has_secrets": bool(findings),
            "findings": findings,
            "count": len(findings),
            "risk_level": "high" if findings else "none",
        }

    def safe_for_cloud(self, messages: list[dict]) -> dict:
        """Check if messages are safe to send to cloud providers."""
        all_text = " ".join(m.get("content", "") for m in messages)
        scan = self.scan_for_secrets(all_text)
        return {
            "safe": not scan["has_secrets"],
            "risk_level": scan["risk_level"],
            "findings_count": scan["count"],
            "action": "ok_to_send" if not scan["has_secrets"] else "redact_first",
            "findings": scan["findings"][:5],
        }

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "scan")
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- this method
        # was reading text/messages/cloud_mode straight off `task` instead
        # of `task["params"]`, so any real dispatch always redacted/scanned
        # an empty string and reported "status: ok" with zero findings,
        # even when the caller supplied a real secret. Verified live before
        # fixing: agent.run({"type": "redact_text", "params": {"text":
        # "<real API key>"}}) returned {"redacted": "", "findings": []}.
        # `task.get("params", task)` keeps flat/legacy direct callers (if
        # any exist) working exactly as before, matching the same
        # backward-compat pattern already used in
        # districts/coding/{fastapi,python,security}_reviewer.py.
        params = task.get("params", task)
        try:
            if task_type == "redact_text":
                text = params.get("text", "")
                cloud = params.get("cloud_mode", False)
                redacted, findings = self.redact(text, cloud_mode=cloud)
                self.award_points(10, "text_redacted")
                return {"status": "ok", "redacted": redacted, "findings": findings,
                        "changed": redacted != text}

            elif task_type == "redact_messages":
                msgs = params.get("messages", [])
                cloud = params.get("cloud_mode", False)
                clean, findings = self.redact_messages(msgs, cloud_mode=cloud)
                if findings:
                    self._get_memory().store(
                        event_type="data_redacted",
                        content=f"Redacted: {', '.join(set(findings))}",
                        tags=["security", "privacy", "redaction"],
                        source="data_redactor",
                    )
                    logger.warning("[VECTOR][redactor] redacted from messages: {}", findings)
                self.award_points(15, "messages_redacted")
                return {"status": "ok", "messages": clean, "findings": findings,
                        "redacted_count": len(findings)}

            elif task_type == "cloud_safety":
                msgs = params.get("messages", [])
                result = self.safe_for_cloud(msgs)
                self.award_points(10, "cloud_safety_checked")
                return {"status": "ok", "safety": result}

            else:  # scan
                text = params.get("text", "")
                result = self.scan_for_secrets(text)
                self.award_points(5, "secrets_scanned")
                return {"status": "ok", "scan": result}

        except Exception as e:
            logger.error("[VECTOR][redactor] {}", e)
            self.deduct_points(20, "redaction_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = DataRedactor()
        test = "My API key is sk-ant-api03-abcdef1234567890 and email is test@example.com"
        redacted, findings = agent.redact(test)
        print(f"[OK] redact: found={findings}")
        print(f"[OK] result: {redacted}")
        scan = agent.scan_for_secrets("AKIA1234567890ABCD github token: ghp_" + "a" * 36)
        print(f"[OK] scan: has_secrets={scan['has_secrets']} count={scan['count']}")
        msgs = [{"role": "user", "content": "My password=supersecret123 and phone +919876543210"}]
        clean, found = agent.redact_messages(msgs)
        print(f"[OK] redact_messages: found={found}")
        result = await agent.run({"type": "scan", "text": "normal text with no secrets"})
        print(f"[OK] run: status={result['status']} has_secrets={result['scan']['has_secrets']}")
        print("data_redactor.py OK")

    asyncio.run(_smoke())
