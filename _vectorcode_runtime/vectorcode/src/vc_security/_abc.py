# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""ABC for security scanners."""

from __future__ import annotations

from abc import ABC, abstractmethod

from vectorcode.src.vc_security.types import ScanResult

class BaseScanner(ABC):
    """Base class for all security scanners.

    Subclasses implement pattern-based scanning for secrets, PII, or other
    sensitive content.
    """

    scanner_id: str

    @abstractmethod
    def scan(self, text: str) -> ScanResult:
        """Scan *text* and return findings."""

    @abstractmethod
    def redact(self, text: str) -> str:
        """Return *text* with sensitive matches replaced by redaction markers."""

__all__ = ["BaseScanner"]
