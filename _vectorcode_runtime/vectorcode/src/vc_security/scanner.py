# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Concrete security scanners — secrets and PII detection."""

from __future__ import annotations
from loguru import logger

import re
from typing import Dict, Tuple

try:
    from vectorcode.src._rust_bridge import get_rust_module, scan_result_from_json
except ImportError:
    get_rust_module = None  # type: ignore[assignment]
    scan_result_from_json = None  # type: ignore[assignment]
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
from vectorcode.src.vc_security._abc import BaseScanner
from vectorcode.src.vc_security.types import ScanFinding, ScanResult, ThreatLevel


def _get_rust() -> object | None:
    """Resolve the Rust bridge module, treating "unimportable" and
    "available but no extension built" (returns None) the same way."""
    if get_rust_module is None:
        return None
    return get_rust_module()


def _scan_python(patterns: Dict[str, Tuple[str, ThreatLevel, str]], text: str) -> ScanResult:
    """Pure-Python pattern scan -- used when the Rust backend is unavailable."""
    findings = []
    for name, (pattern, level, desc) in patterns.items():
        for match in re.finditer(pattern, text):
            findings.append(
                ScanFinding(
                    pattern_name=name,
                    matched_text=match.group(0),
                    threat_level=level,
                    start=match.start(),
                    end=match.end(),
                    description=desc,
                )
            )
    return ScanResult(findings=findings)


def _redact_python(patterns: Dict[str, Tuple[str, ThreatLevel, str]], text: str) -> str:
    """Pure-Python redaction -- used when the Rust backend is unavailable."""
    for name, (pattern, _level, _desc) in patterns.items():
        text = re.sub(pattern, f"[REDACTED:{name}]", text)
    return text

# ---------------------------------------------------------------------------
# SecretScanner
# ---------------------------------------------------------------------------

class SecretScanner(BaseScanner):
    """Detect API keys, tokens, passwords, and other secrets in text."""

    scanner_id = "secrets"

    def __init__(self) -> None:
        # Previously called get_rust_module().SecretScanner()
        # unconditionally -- when the Rust extension isn't built,
        # get_rust_module() returns None (confirmed on this machine), so
        # this secret-detection scanner could never even be constructed.
        # Neither scan() nor redact() had any Python fallback at all,
        # despite PATTERNS below being a complete, ready-to-use regex set.
        _rust = _get_rust()
        self._rust_impl = _rust.SecretScanner() if _rust is not None else None

    PATTERNS: Dict[str, Tuple[str, ThreatLevel, str]] = {
        "openai_key": (
            r"sk-[A-Za-z0-9_-]{20,}",
            ThreatLevel.CRITICAL,
            "OpenAI API key",
        ),
        "anthropic_key": (
            r"sk-ant-[A-Za-z0-9_-]{20,}",
            ThreatLevel.CRITICAL,
            "Anthropic API key",
        ),
        "aws_access_key": (
            r"AKIA[0-9A-Z]{16}",
            ThreatLevel.CRITICAL,
            "AWS access key",
        ),
        "github_token": (
            r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}",
            ThreatLevel.CRITICAL,
            "GitHub token",
        ),
        "password_assignment": (
            r"""(?:password|passwd|pwd)\s*[=:]\s*['"]([^'"]{4,})['"]""",
            ThreatLevel.HIGH,
            "Password assignment",
        ),
        "db_connection_string": (
            r"(?:postgres|mysql|mongodb|redis)://[^\s]{10,}",
            ThreatLevel.HIGH,
            "Database connection string",
        ),
        "private_key": (
            r"-----BEGIN (?:RSA )?PRIVATE KEY-----",
            ThreatLevel.CRITICAL,
            "Private key",
        ),
        "slack_token": (
            r"xox[bpors]-[A-Za-z0-9\-]{10,}",
            ThreatLevel.HIGH,
            "Slack token",
        ),
        "stripe_key": (
            r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{20,}",
            ThreatLevel.CRITICAL,
            "Stripe key",
        ),
        "generic_api_key": (
            r"""(?:api_key|secret_key|auth_token)\s*[=:]\s*['"]([^'"]{8,})['"]""",
            ThreatLevel.HIGH,
            "Generic API key/secret",
        ),
    }

    def scan(self, text: str) -> ScanResult:
        """Scan *text* for secret patterns."""
        if self._rust_impl is not None:
            return scan_result_from_json(self._rust_impl.scan(text))
        return _scan_python(self.PATTERNS, text)

    def redact(self, text: str) -> str:
        """Replace secret matches with ``[REDACTED:{pattern_name}]``."""
        if self._rust_impl is not None:
            return self._rust_impl.redact(text)
        return _redact_python(self.PATTERNS, text)

# ---------------------------------------------------------------------------
# PIIScanner
# ---------------------------------------------------------------------------

class PIIScanner(BaseScanner):
    """Detect personally identifiable information in text."""

    scanner_id = "pii"

    def __init__(self) -> None:
        _rust = _get_rust()
        self._rust_impl = _rust.PIIScanner() if _rust is not None else None

    PATTERNS: Dict[str, Tuple[str, ThreatLevel, str]] = {
        "email": (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            ThreatLevel.MEDIUM,
            "Email address",
        ),
        "us_ssn": (
            r"\b\d{3}-\d{2}-\d{4}\b",
            ThreatLevel.CRITICAL,
            "US Social Security Number",
        ),
        "credit_card_visa": (
            r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            ThreatLevel.CRITICAL,
            "Visa credit card",
        ),
        "credit_card_mastercard": (
            r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            ThreatLevel.CRITICAL,
            "Mastercard credit card",
        ),
        "credit_card_amex": (
            r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b",
            ThreatLevel.CRITICAL,
            "Amex credit card",
        ),
        "us_phone": (
            r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            ThreatLevel.MEDIUM,
            "US phone number",
        ),
        "ipv4_public": (
            r"\b(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)(?!192\.168\.)(?!127\.)(?!0\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            ThreatLevel.LOW,
            "Public IPv4 address",
        ),
    }

    def scan(self, text: str) -> ScanResult:
        """Scan *text* for PII patterns."""
        if self._rust_impl is not None:
            return scan_result_from_json(self._rust_impl.scan(text))
        return _scan_python(self.PATTERNS, text)

    def redact(self, text: str) -> str:
        """Replace PII matches with ``[REDACTED:{pattern_name}]``."""
        if self._rust_impl is not None:
            return self._rust_impl.redact(text)
        return _redact_python(self.PATTERNS, text)

__all__ = ["PIIScanner", "SecretScanner"]
