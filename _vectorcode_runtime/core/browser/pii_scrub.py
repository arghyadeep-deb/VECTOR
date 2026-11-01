"""
VECTOR Browser PII Scrubber — absorbed from auto-browser-main (2026-05-27).

Multi-layer PII redaction for browser content:
  1. Text scrubbing    — 17 regex patterns (AWS, JWT, Bearer, PEM, credit cards, SSN, email, phone…)
  2. Screenshot redact — Pillow black-box over OCR-detected PII regions (guarded import)
  3. Network payloads  — text content types only
  4. Console logs      — scrubs text fields

Replaces: none (VECTOR had SSRF/injection guards but no browser-content PII redaction).
Reuses:   core/config.py CONFIG["browser"]["pii_*"] settings.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from core.config import CONFIG
from loguru import logger

# ── Defaults ───────────────────────────────────────────────────────────────

DEFAULT_REPLACEMENT = "[REDACTED]"

# ── Pattern definitions ────────────────────────────────────────────────────

_RAW_PATTERNS: list[tuple[str, str]] = [
    ("aws_access_key", r"(?<![A-Z0-9])(A[KSIARP][IDA][A-Z0-9]{16})(?![A-Z0-9])"),
    ("aws_secret_key", r"(?i)(?:aws_secret(?:_access)?_key|secret_access_key)\s*[=:]\s*([A-Za-z0-9/+=]{40})"),
    ("jwt_token", r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}"),
    ("bearer_token", r"(?i)Bearer\s+([A-Za-z0-9\-._~+/]+=*)\b"),
    ("pem_header", r"-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE|PUBLIC)\s+KEY-----"),
    (
        "api_key_param",
        r'(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|'
        r'client[_-]?secret|app[_-]?secret|secret[_-]?key|private[_-]?key|'
        r'x-api-key|access_key|refresh_token|id_token|session_token|'
        r'auth_secret|webhook_secret|signing_secret|consumer_secret|'
        r'oauth_token|oauth_secret)'
        r'\s*[=:]\s*["\']?([A-Za-z0-9\-._~+/!@#$%^&*()]{8,})["\']?',
    ),
    (
        "password_field",
        r'(?i)"?(?:password|passwd|pwd|pass|new_password|current_password|'
        r'confirm_password)"?\s*[=:]\s*["\']?([^\s"\'&]{4,})["\']?',
    ),
    (
        "credit_card",
        r"\b(?:4[0-9]{12}(?:[0-9]{3,6})?|5[1-5][0-9]{14}|"
        r"3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|"
        r"6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b",
    ),
    ("ssn", r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    ("email", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ("phone_us", r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
    ("phone_intl", r"\+(?:[0-9] ?){6,14}[0-9]\b"),
    ("gcp_sa_key", r'"private_key_id"\s*:\s*"([a-f0-9]{40})"'),
    (
        "azure_secret",
        r'(?i)(?:client_secret|tenant_id|application_id)\s*[=:]\s*'
        r'["\']?([a-f0-9\-]{32,})["\']?',
    ),
    ("generic_hex_token", r"\b[a-f0-9]{32,64}\b"),
    (
        "generic_b64_secret",
        r'(?i)(?:secret|token|key|credential|cred)\s*[=:]\s*'
        r'"?([A-Za-z0-9+/]{30,}={0,2})"?',
    ),
]

_COMPILED: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern) for name, pattern in _RAW_PATTERNS
}

ALL_PATTERN_NAMES: list[str] = [name for name, _ in _RAW_PATTERNS]
_NOISY_PATTERNS: set[str] = {"generic_hex_token"}

_DEFAULT_ENABLED: set[str] = set(ALL_PATTERN_NAMES) - _NOISY_PATTERNS


# ── Luhn check ─────────────────────────────────────────────────────────────

def _luhn_check(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(digits[::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ── Core text scrubber ─────────────────────────────────────────────────────

@dataclass
class ScrubResult:
    text: str
    hits: list[dict[str, Any]] = field(default_factory=list)

    @property
    def scrubbed(self) -> bool:
        return bool(self.hits)


def scrub_text(
    text: str,
    replacement: str = DEFAULT_REPLACEMENT,
    enabled_patterns: set[str] | None = None,
) -> ScrubResult:
    if not text:
        return ScrubResult(text=text)

    hits: list[dict[str, Any]] = []
    result = text

    for name, pattern in _COMPILED.items():
        if enabled_patterns is not None and name not in enabled_patterns:
            continue

        def _replace(m: re.Match, _name: str = name) -> str:
            matched = m.group(0)
            if _name == "credit_card":
                if not _luhn_check(re.sub(r"[\s-]", "", matched)):
                    return matched
            hits.append({
                "pattern": _name,
                "offset": m.start(),
                "length": len(matched),
                "preview": matched[:6] + "…" if len(matched) > 6 else "…",
            })
            return replacement

        result = pattern.sub(_replace, result)

    return ScrubResult(text=result, hits=hits)


# ── Screenshot pixel redaction ─────────────────────────────────────────────

def scrub_screenshot(
    image_bytes: bytes,
    ocr_blocks: list[dict[str, Any]],
    replacement: str = DEFAULT_REPLACEMENT,
    enabled_patterns: set[str] | None = None,
) -> tuple[bytes, list[dict[str, Any]]]:
    if not ocr_blocks:
        return image_bytes, []

    all_hits: list[dict[str, Any]] = []
    boxes_to_redact: list[tuple[int, int, int, int]] = []

    for block in ocr_blocks:
        text = block.get("text", "")
        if not text:
            continue
        result = scrub_text(text, replacement=replacement, enabled_patterns=enabled_patterns)
        if result.scrubbed:
            x, y = int(block.get("x", 0)), int(block.get("y", 0))
            w, h = int(block.get("width", 0)), int(block.get("height", 0))
            boxes_to_redact.append((x, y, x + w, y + h))
            for hit in result.hits:
                hit["bbox"] = {"x": x, "y": y, "width": w, "height": h}
                all_hits.append(hit)

    if not boxes_to_redact:
        return image_bytes, []

    try:
        from PIL import Image, ImageDraw
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        for box in boxes_to_redact:
            draw.rectangle(box, fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), all_hits
    except Exception as exc:
        logger.warning("[VECTOR][pii_scrub] screenshot redaction failed: {}", exc)
        return image_bytes, all_hits


# ── Network payload scrubber ───────────────────────────────────────────────

def scrub_network_body(
    body: str | bytes | None,
    content_type: str = "",
    replacement: str = DEFAULT_REPLACEMENT,
    enabled_patterns: set[str] | None = None,
) -> tuple[str | bytes | None, list[dict[str, Any]]]:
    if body is None:
        return body, []
    ct = content_type.lower()
    if not any(m in ct for m in ("json", "text", "form", "xml", "javascript", "graphql")):
        return body, []
    try:
        text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    except Exception:
        return body, []
    result = scrub_text(text, replacement=replacement, enabled_patterns=enabled_patterns)
    if not result.scrubbed:
        return body, []
    scrubbed = result.text.encode("utf-8") if isinstance(body, bytes) else result.text
    return scrubbed, result.hits


# ── Console log scrubber ───────────────────────────────────────────────────

def scrub_console_messages(
    messages: list[dict[str, Any]],
    replacement: str = DEFAULT_REPLACEMENT,
    enabled_patterns: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_hits: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for msg in messages:
        text = msg.get("text", "")
        result = scrub_text(text, replacement=replacement, enabled_patterns=enabled_patterns)
        entry = dict(msg)
        if result.scrubbed:
            entry["text"] = result.text
            entry["pii_redacted"] = True
            all_hits.extend(result.hits)
        cleaned.append(entry)
    return cleaned, all_hits


# ── Stateful service ───────────────────────────────────────────────────────

class PiiScrubber:
    """
    Stateful PII scrubber configured from CONFIG["browser"].
    Singleton via get_pii_scrubber().
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        screenshot_enabled: bool = True,
        network_enabled: bool = True,
        console_enabled: bool = True,
        replacement: str = DEFAULT_REPLACEMENT,
        enabled_patterns: set[str] | None = None,
        audit_report: bool = True,
    ):
        self.enabled = enabled
        self.screenshot_enabled = screenshot_enabled and enabled
        self.network_enabled = network_enabled and enabled
        self.console_enabled = console_enabled and enabled
        self.replacement = replacement
        self.enabled_patterns = enabled_patterns if enabled_patterns is not None else _DEFAULT_ENABLED
        self.audit_report = audit_report

    @classmethod
    def from_config(cls) -> "PiiScrubber":
        cfg = CONFIG.get("browser", {})
        enabled = cfg.get("pii_scrub_enabled", True)
        patterns_raw: str = cfg.get("pii_scrub_patterns", "")
        if patterns_raw:
            patterns: set[str] | None = {p.strip() for p in patterns_raw.split(",") if p.strip()}
            patterns = (patterns or set()) & set(ALL_PATTERN_NAMES)
        else:
            patterns = _DEFAULT_ENABLED
        return cls(
            enabled=enabled,
            screenshot_enabled=cfg.get("pii_scrub_screenshot", True),
            network_enabled=cfg.get("pii_scrub_network", True),
            console_enabled=cfg.get("pii_scrub_console", True),
            replacement=cfg.get("pii_scrub_replacement", DEFAULT_REPLACEMENT),
            enabled_patterns=patterns,
            audit_report=cfg.get("pii_scrub_audit_report", True),
        )

    def text(self, value: str) -> ScrubResult:
        if not self.enabled:
            return ScrubResult(text=value)
        return scrub_text(value, self.replacement, self.enabled_patterns)

    def screenshot(self, image_bytes: bytes, ocr_blocks: list[dict[str, Any]]) -> tuple[bytes, list[dict[str, Any]]]:
        if not self.screenshot_enabled:
            return image_bytes, []
        return scrub_screenshot(image_bytes, ocr_blocks, self.replacement, self.enabled_patterns)

    def network_body(self, body: str | bytes | None, content_type: str = "") -> tuple[str | bytes | None, list[dict[str, Any]]]:
        if not self.network_enabled:
            return body, []
        return scrub_network_body(body, content_type, self.replacement, self.enabled_patterns)

    def console(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self.console_enabled:
            return messages, []
        return scrub_console_messages(messages, self.replacement, self.enabled_patterns)

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "screenshot": self.screenshot_enabled,
            "network": self.network_enabled,
            "console": self.console_enabled,
            "patterns": list(self.enabled_patterns) if self.enabled_patterns else ALL_PATTERN_NAMES,
            "replacement": self.replacement,
        }


_scrubber_singleton: PiiScrubber | None = None


def get_pii_scrubber() -> PiiScrubber:
    global _scrubber_singleton
    if _scrubber_singleton is None:
        _scrubber_singleton = PiiScrubber.from_config()
    return _scrubber_singleton


if __name__ == "__main__":
    s = get_pii_scrubber()
    cases = [
        ("jwt", "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abc123xyz"),
        ("email", "Contact support@example.com for help"),
        ("aws", "AKIAIOSFODNN7EXAMPLE is the access key"),
        ("clean", "No PII here at all"),
        ("cc", "Card: 4111111111111111"),
    ]
    all_ok = True
    for label, text in cases:
        r = s.text(text)
        status = "SCRUBBED" if r.scrubbed else "CLEAN"
        expected_scrub = label != "clean"
        ok = r.scrubbed == expected_scrub
        all_ok = all_ok and ok
        print(f"  {label}: {status} {'OK' if ok else 'FAIL'}")
    print("OK - pii_scrub.py" if all_ok else "FAIL - pii_scrub.py")
