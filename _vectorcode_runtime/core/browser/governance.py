"""Browser action governance for VECTOR.

Small, deterministic safety layer inspired by Auto Browser. It does not drive a
browser by itself; it classifies and audits browser actions before automation
layers execute them.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from core.browser.pii_scrub import scrub_text
from loguru import logger


STATE_CHANGING_ACTIONS = {
    "click",
    "double_click",
    "left_click",
    "left_single",
    "left_double",
    "type",
    "input_text",
    "hotkey",
    "upload",
    "download",
    "submit",
    "save_auth_profile",
    "load_auth_profile",
}

HIGH_RISK_TERMS = re.compile(
    r"\b("
    r"buy|purchase|checkout|pay|payment|place\s+order|order\s+now|"
    r"delete|remove|destroy|unsubscribe|cancel|close\s+account|"
    r"send|submit|publish|post|upload|transfer|withdraw|trade|swap|"
    r"password|otp|2fa|verification\s+code|credit\s+card|cvv"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BrowserActionDecision:
    action_type: str
    level: str
    allowed: bool
    requires_owner: bool
    reason: str
    permission_action: str


@dataclass
class BrowserActionReceipt:
    action_type: str
    url: str = ""
    level: str = "GREEN"
    allowed: bool = True
    operator_id: str = "vector"
    session_id: str = ""
    reason: str = ""
    screenshot_hash: str | None = None
    redactions: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrowserGovernance:
    """Classify and audit browser actions before execution."""

    def classify(
        self,
        action_type: str,
        *,
        url: str = "",
        inputs: dict[str, Any] | None = None,
        instruction: str = "",
    ) -> BrowserActionDecision:
        action = (action_type or "").lower().strip()
        payload = json.dumps(inputs or {}, default=str)
        text = " ".join([action, url, payload, instruction])

        if action in {"finished", "wait", "observe", "screenshot"}:
            return BrowserActionDecision(action, "GREEN", True, False, "read-only browser action", "search_web")

        if action == "navigate":
            parsed = urlparse(str((inputs or {}).get("url") or url))
            if parsed.scheme not in {"http", "https", ""}:
                return BrowserActionDecision(action, "RED", False, True, "blocked non-http browser navigation", "hand_browser")
            return BrowserActionDecision(action, "GREEN", True, False, "navigation only", "search_web")

        if HIGH_RISK_TERMS.search(text):
            return BrowserActionDecision(action, "RED", False, True, "high-risk browser action requires owner approval", "hand_browser")

        if action in STATE_CHANGING_ACTIONS:
            return BrowserActionDecision(action, "YELLOW", True, True, "state-changing browser action requires task-level approval", "browser_task")

        return BrowserActionDecision(action, "UNKNOWN", False, True, "unknown browser action", "hand_browser")

    def make_receipt(
        self,
        decision: BrowserActionDecision,
        *,
        url: str = "",
        operator_id: str = "vector",
        session_id: str = "",
        screenshot_bytes: bytes | None = None,
        visible_text: str = "",
    ) -> BrowserActionReceipt:
        scrubbed = scrub_text(visible_text) if visible_text else None
        screenshot_hash = (
            hashlib.sha256(screenshot_bytes).hexdigest()
            if screenshot_bytes
            else None
        )
        receipt = BrowserActionReceipt(
            action_type=decision.action_type,
            url=url,
            level=decision.level,
            allowed=decision.allowed,
            operator_id=operator_id,
            session_id=session_id,
            reason=decision.reason,
            screenshot_hash=screenshot_hash,
            redactions=(scrubbed.hits if scrubbed else []),
        )
        logger.debug("[VECTOR][browser_governance] receipt {}", receipt.to_dict())
        return receipt


_governance: BrowserGovernance | None = None


def get_browser_governance() -> BrowserGovernance:
    global _governance
    if _governance is None:
        _governance = BrowserGovernance()
    return _governance
