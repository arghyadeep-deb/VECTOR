# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Prompt injection scanner — detect malicious patterns in text."""

from __future__ import annotations
from loguru import logger

import re
from dataclasses import dataclass
from typing import List

from vectorcode.src.vc_security.types import ScanFinding, ThreatLevel

# Threat level ordering for comparison
_THREAT_ORDER = [
    ThreatLevel.LOW,
    ThreatLevel.MEDIUM,
    ThreatLevel.HIGH,
    ThreatLevel.CRITICAL,
]

# Injection patterns: (regex, name, threat_level, description)
_INJECTION_PATTERNS = [
    # System prompt override attempts
    (
        r"(?i)ignore\s+(all\s+)?(previous|prior|above)"
        r"\s+(instructions?|prompts?|rules?)",
        "prompt_override",
        ThreatLevel.HIGH,
        "Attempt to override system instructions",
    ),
    (
        r"(?i)you\s+are\s+now\s+(?:a\s+)?(?:different|new|my)",
        "identity_override",
        ThreatLevel.HIGH,
        "Attempt to change AI identity",
    ),
    (
        r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|your)"
        r"\s+(?:instructions?|programming|rules?)",
        "prompt_override",
        ThreatLevel.HIGH,
        "Attempt to disregard instructions",
    ),
    # Shell/code injection via prompt
    (
        r"(?i)(?:execute|run|eval)\s*\(\s*['\"]",
        "code_injection",
        ThreatLevel.HIGH,
        "Code execution attempt in prompt",
    ),
    (
        r"(?:;|\||&&)\s*(?:rm|curl|wget|nc|ncat"
        r"|bash|sh|python|perl)\s",
        "shell_injection",
        ThreatLevel.HIGH,
        "Shell command injection",
    ),
    # Data exfiltration
    (
        r"(?i)(?:send|post|upload|exfiltrate|transmit)"
        r"\s+(?:(?:to|data|all|everything)\s+)*"
        r"(?:to\s+)?(?:https?://|my\s+server)",
        "exfiltration",
        ThreatLevel.HIGH,
        "Data exfiltration attempt",
    ),
    (
        r"(?i)base64\s+encode\s+(?:and\s+)?"
        r"(?:send|include|append)",
        "exfiltration",
        ThreatLevel.MEDIUM,
        "Encoded exfiltration attempt",
    ),
    # Jailbreak patterns
    (
        r"(?i)(?:DAN|do\s+anything\s+now)"
        r"\s+(?:mode|prompt|jailbreak)",
        "jailbreak",
        ThreatLevel.HIGH,
        "DAN jailbreak attempt",
    ),
    (
        r"(?i)pretend\s+(?:you\s+)?(?:have\s+)?no"
        r"\s+(?:restrictions?|limitations?|rules?|filters?)",
        "jailbreak",
        ThreatLevel.MEDIUM,
        "Restriction bypass attempt",
    ),
    # Delimiter injection
    (
        r"```(?:system|assistant)\b",
        "delimiter_injection",
        ThreatLevel.MEDIUM,
        "Role delimiter injection",
    ),
    (
        r"<\|(?:im_start|im_end|system|assistant)\|>",
        "delimiter_injection",
        ThreatLevel.HIGH,
        "Chat template injection",
    ),
]

@dataclass(slots=True)
class InjectionScanResult:
    """Result of an injection scan."""

    is_clean: bool
    findings: List[ScanFinding]
    threat_level: ThreatLevel  # highest threat found

class InjectionScanner:
    """Scan text for prompt injection patterns.

    Implements pattern-based detection for common injection techniques:
    - System prompt overrides
    - Shell/code injection
    - Data exfiltration attempts
    - Jailbreak patterns
    - Delimiter injection
    """

    def __init__(self) -> None:
        self._patterns = [
            (re.compile(pat), name, level, desc)
            for pat, name, level, desc in _INJECTION_PATTERNS
        ]
        # Previously called get_rust_module().InjectionScanner()
        # unconditionally -- when the Rust extension isn't built,
        # get_rust_module() returns None (confirmed on this machine), so
        # every InjectionScanner() call raised AttributeError and the class
        # could never even be constructed. The carefully-defined
        # _INJECTION_PATTERNS above (prompt override, jailbreak,
        # exfiltration, shell/code injection, delimiter injection) existed
        # but were compiled into self._patterns and then never used by
        # scan(), which only ever called the Rust implementation.
        try:
            from vectorcode.src._rust_bridge import get_rust_module

            _rust = get_rust_module()
        except ImportError:
            _rust = None
        self._rust_impl = _rust.InjectionScanner() if _rust is not None else None

    def scan(self, text: str) -> InjectionScanResult:
        """Scan text for injection patterns.

        Prefers the Rust backend when available; falls back to the
        pure-Python pattern scan built from _INJECTION_PATTERNS otherwise.
        """
        if self._rust_impl is not None:
            from vectorcode.src._rust_bridge import injection_result_from_json

            return injection_result_from_json(self._rust_impl.scan(text))
        return self._scan_python(text)

    def _scan_python(self, text: str) -> InjectionScanResult:
        findings: List[ScanFinding] = []
        highest = ThreatLevel.LOW
        for compiled, name, level, desc in self._patterns:
            for match in compiled.finditer(text):
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
                if _THREAT_ORDER.index(level) > _THREAT_ORDER.index(highest):
                    highest = level
        return InjectionScanResult(
            is_clean=not findings, findings=findings, threat_level=highest
        )

__all__ = ["InjectionScanner", "InjectionScanResult"]
